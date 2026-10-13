"""Combined masters for a collection (004-DR-05, T022): each dataset's current master is registered to the reference
framing (the master of the dataset with the most accepted integration), and masters sharing a filter are averaged,
weighted by the subs in each. The results line up pixel for pixel, ready for colour combination (SHO, LRGB)."""

from __future__ import annotations

import logging
import os
import shutil
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import Collection
from substation.tasks import PRIORITY_BULK, enqueue, report_progress, station_task

from .models import CombinedMaster, Master, MasterState

log = logging.getLogger(__name__)


def in_project(project_id: int | None) -> dict:
    """Filter for combined masters of one project, or of the whole collection when there is none."""
    return {"project_id": project_id} if project_id else {"project__isnull": True}


def current_masters(col: Collection, project_id: int | None = None) -> list[Master]:
    # a stale master (newer subs since) is still a good image: use it until it's re-stacked
    qs = Master.objects.filter(
        dataset__collection=col, state__in=[MasterState.CURRENT, MasterState.STALE]
    ).exclude(output_path="")
    if project_id:
        qs = qs.filter(dataset__project_id=project_id)
    return list(qs.select_related("dataset", "dataset__rig").order_by("-integration_s"))


def _scale(m: Master) -> float | None:
    from .solving import framing

    f = framing(m.dataset)
    return float(f["scale"]) if f and f.get("scale") else None


def plan(col: Collection, project_id: int | None = None) -> dict:
    """What a combine would do for a project (owner 2026-10-10: combine within a project, never across rigs):
    the reference and, per filter, the masters it would use. Masters at another pixel scale (more than 10% off the
    reference's) are left out and listed, as they belong to another project."""
    from apps.catalogue.api_library import label

    ms = [m for m in current_masters(col, project_id) if Path(m.output_path).exists()]
    if not ms:
        return {"reference": None, "filters": {}, "left_out": []}
    ref = max(ms, key=lambda m: m.dataset.accepted_integration_s or m.integration_s or 0)
    rs = _scale(ref)
    left_out = []
    keep = []
    for m in ms:
        sc = _scale(m)
        if rs and sc and abs(sc / rs - 1) > 0.10:
            left_out.append(f"{label(m.dataset)} ({sc:.2f}″/px, not {rs:.2f}″/px)")
        else:
            keep.append(m)
    filters: dict[str, list[dict]] = defaultdict(list)
    for m in keep:
        filters[m.dataset.filter_norm or "?"].append(
            {
                "master": m.pk,
                "dataset": m.dataset_id,
                "label": label(m.dataset),
                "version": m.version,
                "integration_s": m.integration_s,
                "subs": m.sub_count,
            }
        )
    return {
        "reference": ref.pk,
        "reference_label": label(ref.dataset),
        "filters": dict(filters),
        "left_out": left_out,
    }


def start(col: Collection, project_id: int | None = None) -> list[CombinedMaster]:
    from apps.catalogue.models import Project

    # owner 2026-10-10: combine within a project, never across rigs or panels
    if project_id is None and Project.objects.filter(collection=col).exists():
        raise ValueError("Pick a project to combine.")
    p = plan(col, project_id)
    if p["reference"] is None:
        raise ValueError("No current masters yet. Stack each dataset first.")
    out = []
    with transaction.atomic():
        for filt, inputs in p["filters"].items():
            version = (
                CombinedMaster.objects.filter(collection=col, filter_norm=filt, **in_project(project_id))
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            ) + 1
            out.append(
                CombinedMaster.objects.create(
                    collection=col,
                    project_id=project_id,
                    filter_norm=filt,
                    version=version,
                    reference_id=p["reference"],
                    inputs=inputs,
                    integration_s=sum(i["integration_s"] or 0 for i in inputs),
                )
            )
    job = enqueue(combine, col.pk, [c.pk for c in out], priority=PRIORITY_BULK + 5)
    CombinedMaster.objects.filter(pk__in=[c.pk for c in out]).update(task_id=job.id)
    return out


def _layers(path: Path) -> int:
    from astropy.io import fits

    h = fits.getheader(path)
    return int(h.get("NAXIS3", 1)) if int(h.get("NAXIS", 2)) == 3 else 1


def _align(eng, ref: Path, src: Path, work: Path, factor: float = 1.0) -> Path | None:  # noqa: ANN001
    """`src` registered onto `ref`'s framing, or None when its stars can't be matched. Siril registers a sequence
    of like images, so the pair is the reference made to match the source's layers (a colour copy of a mono
    reference, or the green channel of a colour one) and the source. `convert` takes every file in its folder,
    so the reference is prepared in one folder and the pair converted in another."""
    prep, pair = work / "prep", work / "pair"
    prep.mkdir(parents=True)
    pair.mkdir()
    rl, sl = _layers(ref), _layers(src)
    if rl == sl:
        first = ref
    else:
        os.symlink(ref, prep / "refin.fit")
        eng.run(f"cd {prep}")
        if rl == 1:
            eng.run("rgbcomp refin refin refin -out=ref_matched")
            first = prep / "ref_matched.fit"
        else:
            eng.run("load refin")
            eng.run("split r g b")
            first = prep / "g.fit"
    if abs(factor - 1) > 0.05:
        # star matching can't bridge very different pixel scales (a Seestar beside a 490 mm refractor): bring the
        # source to the reference's scale first, from the plate solves
        os.symlink(src, prep / "srcin.fit")
        eng.run(f"cd {prep}")
        eng.run("load srcin")
        eng.run(f"resample {factor:.4f}")
        eng.run("save src_scaled")
        src = prep / "src_scaled.fit"
    os.symlink(first, pair / "a1.fit")
    os.symlink(src, pair / "a2.fit")
    eng.run(f"cd {pair}")
    eng.run("convert p -out=.", timeout=600)
    eng.run("setref p_ 1")
    r = eng.run("register p_ -transf=homography", timeout=3600, check=False)
    out = pair / "r_p_00002.fit"
    if not r.ok or not out.exists():
        return None
    return out


def _mosaic(eng, sources: list[Path], work: Path) -> Path | None:  # noqa: ANN001
    """One filter's panels stitched into a mosaic (owner 2026-10-10): registered to each other, placed on a canvas
    covering every panel (framing max), and stacked with brightness matched on the overlaps and feathered edges.
    None when the panels' stars can't be matched (too little overlap)."""
    work.mkdir(parents=True)
    for i, src in enumerate(sources, start=1):
        os.symlink(src, work / f"a{i}.fit")
    eng.run(f"cd {work}")
    eng.run("convert m -out=.", timeout=600)
    eng.run("setref m_ 1")
    if not eng.run("register m_ -2pass", timeout=3600, check=False).ok:
        return None
    if not eng.run("seqapplyreg m_ -framing=max", timeout=3600, check=False).ok:
        return None
    r = eng.run(
        "stack r_m_ rej n -norm=addscale -overlap_norm -maximize -feather=300 -out=mosaic",
        timeout=7200,
        check=False,
    )
    out = work / "mosaic.fit"
    return out if r.ok and out.exists() else None


def _placements(seq: Path) -> dict[int, tuple[int, int, int, int]]:
    """Image number → (x, y, width, height) on the reference's grid, from a registered `.seq` file: its `I` lines
    give each image's size and its `R0 … H` lines a translation (framing max applies registration as shifts)."""
    sizes: dict[int, tuple[int, int]] = {}
    shifts: list[tuple[int, int]] = []
    for line in seq.read_text().splitlines():
        p = line.split()
        if line.startswith("I ") and len(p) >= 4 and "," in p[3]:
            w, h = p[3].split(",")
            sizes[int(p[1])] = (int(w), int(h))
        elif line.startswith("R0 ") and "H" in p:
            hm = [float(x) for x in p[p.index("H") + 1 : p.index("H") + 10]]
            shifts.append((round(hm[2]), round(hm[5])))
    return {
        n: (shifts[i][0], shifts[i][1], *sizes[n]) for i, n in enumerate(sorted(sizes)) if i < len(shifts)
    }


def _place(src: Path, canvas: tuple[int, int], at: tuple[int, int], out: Path) -> None:
    """Put an image at `at` (x, y in FITS pixels) on an empty canvas of `canvas` (width, height): pixels are moved,
    never resampled, so every filter's mosaic lines up pixel for pixel."""
    import numpy as np
    from astropy.io import fits

    with fits.open(src) as hl:
        data = np.asarray(hl[0].data, dtype=np.float32)
        header = hl[0].header.copy()
    planes = data if data.ndim == 3 else data[None]
    w, h = canvas
    full = np.zeros((planes.shape[0], h, w), dtype=np.float32)
    x, y = at
    ph, pw = planes.shape[1], planes.shape[2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + pw), min(h, y + ph)
    full[:, y0:y1, x0:x1] = planes[:, y0 - y : y1 - y, x0 - x : x1 - x]
    for k in ("NAXIS1", "NAXIS2", "NAXIS3", "CRPIX1", "CRPIX2"):
        header.pop(k, None)
    fits.PrimaryHDU(full if data.ndim == 3 else full[0], header=header).writeto(out, overwrite=True)


def _mosaic_all(eng, groups: dict[int, list[Path]], ref: Path, work: Path) -> dict[int, Path | None]:  # noqa: ANN001
    """Every master of a mosaic project, all filters and panels, registered together to one reference (2026-10-11,
    owner: HOO and SHO across the whole mosaic). Each filter's panels are then stacked from that registered sequence
    (Siril: framing max, brightness matched on the overlaps, feathered edges) and placed on the one canvas that
    covers every panel, so all filters come out the same size, pixel for pixel. `groups` maps a combined master to
    its masters' files."""
    work.mkdir(parents=True)
    order: list[tuple[int, Path]] = [(-1, ref)] + [(k, p) for k, ps in groups.items() for p in ps if p != ref]
    for i, (_k, src) in enumerate(order, start=1):
        os.symlink(src, work / f"a{i:05d}.fit")
    eng.run(f"cd {work}")
    eng.run("convert m -out=.", timeout=600)
    eng.run("setref m_ 1")
    for cmd in ("register m_ -2pass", "seqapplyreg m_ -framing=max"):
        r = eng.run(cmd, timeout=3600, check=False)
        if not r.ok:
            log.warning("Mosaic: %s failed: %s", cmd.split()[0], " | ".join(r.log[-12:]))
            return dict.fromkeys(groups)
    place = _placements(work / "r_m_.seq")
    if not place:
        return dict.fromkeys(groups)
    gx0 = min(x for x, _y, _w, _h in place.values())
    gy0 = min(y for _x, y, _w, _h in place.values())
    canvas = (
        max(x + w for x, _y, w, _h in place.values()) - gx0,
        max(y + h for _x, y, _w, h in place.values()) - gy0,
    )
    index = {src: i for i, (_k, src) in enumerate(order, start=1)}
    out: dict[int, Path | None] = {}
    for k, ps in groups.items():
        mine = [index[p] for p in ps if p in index and index[p] in place]
        if not mine:
            out[k] = None
            continue
        target = work / f"filter_{k}.fit"
        if len(mine) == 1:
            n = mine[0]
            _place(work / f"r_m_{n:05d}.fit", canvas, (place[n][0] - gx0, place[n][1] - gy0), target)
        else:
            eng.run(f"unselect r_m_ 1 {len(order)}", check=False)
            for n in mine:
                eng.run(f"select r_m_ {n} {n}", check=False)
            r = eng.run(
                f"stack r_m_ rej n -norm=addscale -overlap_norm -maximize -feather=300 -filter-incl -out=stk_{k}",
                timeout=7200,
                check=False,
            )
            if not r.ok or not (work / f"stk_{k}.fit").exists():
                out[k] = None
                continue
            x0 = min(place[n][0] for n in mine) - gx0
            y0 = min(place[n][1] for n in mine) - gy0
            _place(work / f"stk_{k}.fit", canvas, (x0, y0), target)
        out[k] = target
    return out


def _factor(m: Master, ref: Master) -> float:
    """How much to enlarge `m` to match the reference's pixel scale, from the plate solves (1 when unknown)."""
    from .solving import framing

    a, b = framing(m.dataset), framing(ref.dataset)
    if not a or not b or not a["scale"] or not b["scale"]:
        return 1.0
    return float(a["scale"]) / float(b["scale"])


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def combine(collection_id: int, combined_ids: list[int]) -> dict:
    from apps.engine.siril import engine

    from .previews import render

    rows = list(CombinedMaster.objects.filter(pk__in=combined_ids).select_related("reference", "project"))
    if not rows or rows[0].reference is None:
        return {"result": "nothing to do"}
    ref = Path(rows[0].reference.output_path)
    CombinedMaster.objects.filter(pk__in=combined_ids).update(state=MasterState.RUNNING, error=None)
    root = Path(settings.WORK_DIR) / "combine" / f"col{collection_id}"
    shutil.rmtree(root, ignore_errors=True)
    out_dir = Path(settings.STACKS_DIR) / "collections" / f"col{collection_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    from apps.engine.siril import heavy_memory

    eng = engine()
    _heavy = heavy_memory()
    _heavy.__enter__()
    done = 0
    # a mosaic project: each filter's panels are stitched first, and every filter's mosaic is then aligned to the
    # reference filter's, so HOO and SHO line up across the whole mosaic
    project = rows[0].project
    mosaics: dict[int, Path | None] = {}
    if project is not None and project.kind == "mosaic":
        groups = {
            cm.pk: [
                Path(m.output_path)
                for m in Master.objects.filter(pk__in=[i["master"] for i in cm.inputs])
                if m.output_path and Path(m.output_path).exists()
            ]
            for cm in rows
        }
        report_progress(0.0, f"Stitching {sum(len(v) for v in groups.values())} masters into a mosaic")
        mosaics = _mosaic_all(eng, groups, ref, root / "mosaic")
    try:
        for n, cm in enumerate(rows):
            if mosaics:
                report_progress(n / len(rows), f"Combined {cm.filter_norm}: aligning the mosaic")
                try:
                    src = mosaics.get(cm.pk)
                    if src is None:
                        raise RuntimeError(
                            "Couldn't place panels on the mosaic: too few stars matched in the overlap."
                        )
                    tag = f"p{cm.project_id}_" if cm.project_id else ""
                    target = out_dir / f"combined_{tag}{cm.filter_norm}_v{cm.version}.fit".replace(" ", "_")
                    shutil.copyfile(src, target)  # already on the shared canvas
                    prev = target.with_suffix(".jpg")
                    try:
                        render(target, prev, target.with_name(target.stem + "_t.jpg"))
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Combined preview failed: %s", exc)
                    CombinedMaster.objects.filter(pk=cm.pk).update(
                        state=MasterState.CURRENT,
                        error=None,
                        inputs=[i | {"registered": True} for i in cm.inputs],
                        output_path=str(target),
                        preview_path=str(prev) if prev.exists() else "",
                        finished_at=timezone.now(),
                        state_reason=f"Mosaic of {len(cm.inputs)} panel(s).",
                    )
                    (
                        CombinedMaster.objects.filter(
                            collection_id=collection_id,
                            filter_norm=cm.filter_norm,
                            state=MasterState.CURRENT,
                            **in_project(cm.project_id),
                        )
                        .exclude(pk=cm.pk)
                        .update(state=MasterState.SUPERSEDED, state_reason=f"Replaced by v{cm.version}.")
                    )
                    done += 1
                except Exception as exc:  # noqa: BLE001
                    log.exception("Combining %s failed", cm.filter_norm)
                    CombinedMaster.objects.filter(pk=cm.pk).update(
                        state=MasterState.FAILED, error=str(exc), finished_at=timezone.now()
                    )
                continue
            report_progress(
                n / len(rows), f"Combined {cm.filter_norm}: registering {len(cm.inputs)} master(s)"
            )
            try:
                aligned: list[tuple[Path, int]] = []
                inputs = []
                for i, inp in enumerate(cm.inputs):
                    m = Master.objects.filter(pk=inp["master"]).first()
                    src = Path(m.output_path) if m else None
                    got = (
                        _align(eng, ref, src, root / f"{cm.filter_norm}_{i}", _factor(m, rows[0].reference))
                        if m and src and src.exists()
                        else None
                    )
                    inputs.append(inp | {"registered": got is not None})
                    if got is not None:
                        aligned.append((got, inp.get("subs") or 1))
                if not aligned:
                    CombinedMaster.objects.filter(pk=cm.pk).update(inputs=inputs)
                    raise RuntimeError(
                        "Stars didn't match the reference. Field or pixel scale too "
                        "different; stack it with its own rig."
                    )
                tag = f"p{cm.project_id}_" if cm.project_id else ""
                target = out_dir / f"combined_{tag}{cm.filter_norm}_v{cm.version}.fit".replace(" ", "_")
                if len(aligned) == 1:
                    shutil.copyfile(aligned[0][0], target)
                else:
                    seq = root / f"{cm.filter_norm}_stack"
                    seq.mkdir(parents=True)
                    # copied under their own names: convert writes c_00001.fit…, and symlinks on the mounted
                    # library aren't reliable (2026-10-11, "failed to find or open c_00001.fit")
                    for k, (pth, _subs) in enumerate(aligned, start=1):
                        shutil.copyfile(pth, seq / f"in_{k:05d}.fit")
                    eng.run(f"cd {seq}")
                    eng.run("convert c -out=.", timeout=600)
                    # weighted by the number of subs in each master (Siril reads it from STACKCNT)
                    eng.run(
                        f"stack c_ rej n -norm=addscale -weight=nbstack -out={target.with_suffix('')}",
                        timeout=3600,
                    )
                prev = target.with_suffix(".jpg")
                try:
                    render(target, prev, target.with_name(target.stem + "_t.jpg"))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Combined preview failed: %s", exc)
                CombinedMaster.objects.filter(pk=cm.pk).update(
                    state=MasterState.CURRENT,
                    error=None,
                    inputs=inputs,
                    output_path=str(target),
                    preview_path=str(prev) if prev.exists() else "",
                    finished_at=timezone.now(),
                    state_reason=""
                    if all(i["registered"] for i in inputs)
                    else "Left out (stars didn't match the reference): "
                    + ", ".join(i["label"] for i in inputs if not i["registered"])
                    + ".",
                )
                (
                    CombinedMaster.objects.filter(
                        collection_id=collection_id,
                        filter_norm=cm.filter_norm,
                        state=MasterState.CURRENT,
                        **in_project(cm.project_id),
                    )
                    .exclude(pk=cm.pk)
                    .update(state=MasterState.SUPERSEDED, state_reason=f"Replaced by v{cm.version}.")
                )
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("Combining %s failed", cm.filter_norm)
                CombinedMaster.objects.filter(pk=cm.pk).update(
                    state=MasterState.FAILED, error=str(exc), finished_at=timezone.now()
                )
    finally:
        shutil.rmtree(root, ignore_errors=True)
        _heavy.__exit__(None, None, None)
    # palettes made from these combined masters are redrawn now, so the 100% HOO/SHO views are ready
    from .tasks import PALETTES, combined_view, palette_inputs, palette_view

    for cm in CombinedMaster.objects.filter(pk__in=[r.pk for r in rows], state=MasterState.CURRENT):
        enqueue(combined_view, cm.pk, dedupe_key=f"combined-view:{cm.pk}")
    project_id = rows[0].project_id
    for name in PALETTES:
        if palette_inputs(collection_id, project_id, name) is not None:
            enqueue(
                palette_view,
                collection_id,
                project_id,
                name,
                dedupe_key=f"palette:{collection_id}:{project_id}:{name}",
            )
    return {"combined": done, "of": len(rows)}


def staleness(cm: CombinedMaster) -> str:
    """Why a current combined master is out of date ("Hα: 41 new subs since 2 October"), or ''."""
    if cm.state != MasterState.CURRENT:
        return ""
    now = {
        m.pk: m
        for m in current_masters(cm.collection, cm.project_id)
        if (m.dataset.filter_norm or "?") == cm.filter_norm
    }
    used = {i["master"] for i in cm.inputs}
    if set(now) == used:
        return ""
    new_subs = sum(m.sub_count for k, m in now.items() if k not in used) - sum(
        i.get("subs") or 0 for i in cm.inputs if i["master"] not in now
    )
    when = f"{cm.finished_at:%-d %B}" if cm.finished_at else "it was made"
    if new_subs > 0:
        return f"{cm.filter_norm} combined master is stale: {new_subs} new subs since {when}."
    return f"{cm.filter_norm} combined master is stale: its datasets have newer masters since {when}."
