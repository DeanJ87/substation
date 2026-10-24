"""Masters made from a project's dataset masters, one per filter (004-DR-05, T022; the model keeps its old name,
CombinedMaster). Two operations (004-DR-32): "Stack together" registers each dataset's current master to the
reference framing (the master of the dataset with the most accepted integration) and averages masters sharing a
filter, weighted by the subs in each; "Stitch mosaic" places every panel on one canvas by its plate solution
(004-DR-31). Either way the filters line up pixel for pixel, ready for colour composition (HOO, SHO), which is a
separate step."""

from __future__ import annotations

import logging
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

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


STITCH, STACK = CombinedMaster.Method.STITCH.value, CombinedMaster.Method.STACK.value


def plan(col: Collection, project_id: int | None = None, method: str | None = None) -> dict:
    """What a stitch or a stack would do for a project (owner 2026-10-10: within a project, never across rigs):
    the reference and, per filter, the masters it would use. Masters at another pixel scale (more than 10% off the
    reference's) are left out and listed, as they belong to another project.

    Two operations (004-DR-32), the project's kind choosing the default: "Stitch mosaic" places every panel of a
    filter on one canvas; "Stack together" stacks masters of the same field (two rigs, two seasons) into a deeper
    one, so masters of another panel than the reference's are left out (a season's project can hold a mosaic's
    panels and a single field). A stale master (newer subs since) is used as it is, and said so."""
    from apps.catalogue.api_library import label
    from apps.catalogue.models import Project
    from apps.catalogue.services.projects import effective_kind

    project = Project.objects.filter(pk=project_id).first() if project_id else None
    mosaic = project is not None and effective_kind(project) == "mosaic"
    default = STITCH if mosaic else STACK
    ms = [m for m in current_masters(col, project_id) if Path(m.output_path).exists()]
    several_panels = len({m.dataset.panel for m in ms}) > 1  # no panel is a field of its own
    methods = [STITCH, STACK] if mosaic or several_panels else [STACK]
    method = method if method in methods else default
    out: dict = {"method": method, "default_method": default, "methods": methods, "notes": []}
    if not ms:
        return out | {"reference": None, "filters": {}, "left_out": []}
    ref = max(ms, key=lambda m: m.dataset.accepted_integration_s or m.integration_s or 0)
    rs = _scale(ref)
    left_out = []
    keep = []
    for m in ms:
        sc = _scale(m)
        if rs and sc and abs(sc / rs - 1) > 0.10:
            left_out.append(f"{label(m.dataset)} ({sc:.2f}″/px, not {rs:.2f}″/px)")
        elif method == STACK and m.dataset.panel != ref.dataset.panel:
            left_out.append(
                f"{label(m.dataset)} (panel {m.dataset.panel or 'none'}, not {ref.dataset.panel or 'none'})"
            )
        else:
            keep.append(m)
    filters: dict[str, list[dict]] = defaultdict(list)
    same_field: dict[tuple, int] = defaultdict(int)
    for m in keep:
        filters[m.dataset.filter_norm or "?"].append(
            {
                "master": m.pk,
                "dataset": m.dataset_id,
                "label": label(m.dataset),
                "version": m.version,
                "integration_s": m.integration_s,
                "subs": m.sub_count,
                "stale": m.state == MasterState.STALE,
            }
        )
        same_field[(m.dataset.panel, m.dataset.filter_norm or "?")] += 1
    if method == STITCH:
        for (panel, filt), n in sorted(same_field.items(), key=lambda x: (x[0][0] or 0, x[0][1])):
            if n > 1:
                out["notes"].append(
                    f"Panel {panel or 'none'} · {filt} has {n} masters: each is placed on the canvas and they're "
                    "averaged where they overlap, not weighted by their subs."
                )
    return out | {
        "reference": ref.pk,
        "reference_label": label(ref.dataset),
        "filters": dict(filters),
        "left_out": left_out,
    }


def start(col: Collection, project_id: int | None = None, method: str | None = None) -> list[CombinedMaster]:
    from apps.catalogue.models import Project

    # owner 2026-10-10: within a project, never across rigs or panels
    if project_id is None and Project.objects.filter(collection=col).exists():
        raise ValueError("Pick a project to stitch or stack.")
    p = plan(col, project_id, method)
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
                    method=p["method"],
                    reference_id=p["reference"],
                    inputs=inputs,
                    integration_s=sum(i["integration_s"] or 0 for i in inputs),
                )
            )
    task = stitch_mosaic if p["method"] == STITCH else stack_together
    job = enqueue(task, col.pk, [c.pk for c in out], priority=PRIORITY_BULK + 5)
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


class Panel(NamedTuple):
    """One master going into a mosaic: its file, its name for messages ("Askar 71F · Hα · Panel 3") and the plate
    solve stored with it (Master.solve: ra/dec and, usually, the whole WCS)."""

    master: int
    label: str
    path: Path
    solve: dict


@dataclass
class Stitched:
    """One filter's mosaic on the shared canvas, or why there is none; `left_out` are the masters (with the reason
    in plain words) that couldn't be placed, `notes` what the owner should know about the ones that were."""

    path: Path | None = None
    why: str = ""
    left_out: dict[int, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _has_wcs(path: Path) -> bool:
    from astropy.io import fits

    try:
        h = fits.getheader(path)
    except (OSError, ValueError):
        return False
    return "CRVAL1" in h and "CTYPE1" in h and ("CD1_1" in h or "CDELT1" in h)


def _solved_copy(eng, panel: Panel, dest: Path) -> str:  # noqa: ANN001
    """The mosaic's own copy of a panel at `dest`, with a plate solution in its header; '' when it has one, else
    why not. The master's stored solution is written into the copy (the master's file is never written to); a copy
    whose file already carries a solution keeps it; only a panel with neither is solved here, near where its own
    solve put it."""
    from apps.engine.siril import EngineError

    from .masters import _write_wcs

    wcs = (panel.solve or {}).get("wcs") or {}
    if wcs:
        os.symlink(panel.path, dest)
        if _write_wcs(dest, wcs):
            return ""
        dest.unlink(missing_ok=True)
    shutil.copyfile(panel.path, dest)
    if _has_wcs(dest):
        return ""
    sol = panel.solve or {}
    start = f"{sol['ra_deg']:.5f},{sol['dec_deg']:.5f} " if "ra_deg" in sol else ""
    try:
        eng.run(f"cd {dest.parent}")
        eng.run(f"load {dest.stem}", timeout=600)
        if eng.run(f"platesolve {start}-force -downscale -order=3", timeout=600, check=False).ok:
            dest.unlink(missing_ok=True)
            eng.run(f"save {dest.stem}", timeout=600)
            if _has_wcs(dest):
                return ""
    except EngineError as exc:  # Siril crashed on this panel: it costs only itself
        log.warning("Plate solving mosaic panel %s failed: %s", panel.label, exc)
    if sol.get("failed"):
        return "its master couldn't be plate solved, so there is nothing to place it by"
    return "it has no plate solution and Siril couldn't solve it"


def _touching(rects: dict[int, tuple[int, int, int, int]]) -> list[set[int]]:
    """Groups of panels joined by overlaps (x, y, width, height on one grid): one group when the mosaic is whole."""
    groups: list[set[int]] = []
    for n, (x, y, w, h) in rects.items():
        joined = [
            g
            for g in groups
            if any(
                x < ox + ow and ox < x + w and y < oy + oh and oy < y + h
                for ox, oy, ow, oh in (rects[k] for k in g)
            )
        ]
        merged = {n}.union(*joined)
        groups = [g for g in groups if g not in joined] + [merged]
    return groups


def _staged(
    eng, groups: dict[int, list[Panel]], ref: Panel, work: Path
) -> tuple[list[Panel], dict[Path, str]]:  # noqa: ANN001
    """Each panel made ready on its own (a solved copy, 004-DR-31); only the ones with a solution join the sequence
    m_, numbered in order (the reference first, when it has one). Returns the sequence and, per file, why not."""
    order: list[Panel] = []
    for p in [ref] + [p for ps in groups.values() for p in ps]:
        if all(p.path != q.path for q in order):
            order.append(p)
    why: dict[Path, str] = {}
    seq: list[Panel] = []
    for i, p in enumerate(order, start=1):
        staged = work / f"panel_{i:05d}.fit"
        why[p.path] = _solved_copy(eng, p, staged)
        if why[p.path]:
            staged.unlink(missing_ok=True)
        else:
            seq.append(p)
            staged.rename(work / f"m_{len(seq):05d}.fit")
    return seq, why


def _layout(eng, n: int, work: Path) -> tuple[dict[int, tuple[int, int, int, int]], str, str]:  # noqa: ANN001
    """Where each of the `n` solved copies sits (x, y, width, height on one grid), the registered sequence's file
    prefix, and why there is no layout ('' when there is one)."""
    if n == 1:
        from astropy.io import fits

        h = fits.getheader(work / "m_00001.fit")
        return {1: (0, 0, int(h["NAXIS1"]), int(h["NAXIS2"]))}, "m_", ""
    eng.run(f"cd {work}")
    eng.run("setref m_ 1")
    # the copies are already solved, so seqplatesolve doesn't solve them again: it turns their solutions into
    # registration data, which framing max applies onto a canvas covering every panel
    for cmd in ("seqplatesolve m_", "seqapplyreg m_ -framing=max"):
        r = eng.run(cmd, timeout=3600, check=False)
        if not r.ok:
            tail = "; ".join(line for line in r.log[-3:] if line.strip()) or "no details"
            log.warning("Mosaic: %s failed: %s", cmd.split()[0], " | ".join(r.log[-12:]))
            return {}, "", f"Siril couldn't lay out the canvas from the panels' plate solutions ({tail})"
    place = _placements(work / "r_m_.seq")
    return place, "r_m_", "" if place else "Siril laid out no panels from their plate solutions"


def _apart(mine: dict[int, Panel], place: dict[int, tuple[int, int, int, int]]) -> str:
    """A note naming the panels that don't overlap the rest of the filter's mosaic, or ''."""
    parts = _touching({n: place[n] for n in mine})
    if len(parts) < 2:
        return ""
    names = ", ".join(mine[n].label for g in sorted(parts, key=len)[:-1] for n in sorted(g))
    return (
        f"{names} doesn't overlap the rest of the mosaic: placed by its plate solution with a gap between, "
        "so its brightness isn't matched to the others."
    )


def _filter_mosaic(
    eng,  # noqa: ANN001
    k: int,
    mine: dict[int, Panel],
    place: dict[int, tuple[int, int, int, int]],
    grid: tuple[int, int, int, int],
    registered: str,
    total: int,
    work: Path,
) -> tuple[Path | None, str]:
    """One filter's placed panels stacked and put on the shared canvas (`grid`: its origin and size on the
    registration grid); the file, or why not."""
    gx0, gy0, w, h = grid
    target = work / f"filter_{k}.fit"
    if len(mine) == 1:
        (n,) = mine
        _place(work / f"{registered}{n:05d}.fit", (w, h), (place[n][0] - gx0, place[n][1] - gy0), target)
        return target, ""
    eng.run(f"unselect r_m_ 1 {total}", check=False)
    for n in mine:
        eng.run(f"select r_m_ {n} {n}", check=False)
    r = eng.run(
        f"stack r_m_ rej n -norm=addscale -overlap_norm -maximize -feather=300 -filter-incl -out=stk_{k}",
        timeout=7200,
        quiet=True,
        check=False,
    )
    if not r.ok or not (work / f"stk_{k}.fit").exists():
        tail = "; ".join(line for line in r.log[-3:] if line.strip()) or "no details"
        return None, f"Siril couldn't stack its {len(mine)} placed panels ({tail})"
    x0 = min(place[n][0] for n in mine) - gx0
    y0 = min(place[n][1] for n in mine) - gy0
    _place(work / f"stk_{k}.fit", (w, h), (x0, y0), target)
    return target, ""


def _mosaic_all(eng, groups: dict[int, list[Panel]], ref: Panel, work: Path) -> dict[int, Stitched]:  # noqa: ANN001
    """Every master of a mosaic project, all filters and panels, laid out on one canvas by its plate solution
    (004-DR-31): star matching against one reference panel can't place an outer panel that shares no stars with it.
    Each panel's copy carries its master's stored solution (solved here only when it has none), seqplatesolve turns
    the solutions into registration, and framing max lays out the canvas that covers every panel. Each filter's
    panels are then stacked (brightness matched on the overlaps, feathered edges) and placed on that one canvas, so
    all filters come out the same size, pixel for pixel (HOO and SHO across the whole mosaic). `groups` maps a
    combined master to its panels."""
    work.mkdir(parents=True)
    seq, why = _staged(eng, groups, ref, work)
    out = {
        k: Stitched(left_out={p.master: why[p.path] for p in ps if why.get(p.path)})
        for k, ps in groups.items()
    }
    if not seq:
        for st in out.values():
            st.why = "none of its panels has a plate solution to place it by"
        return out
    place, registered, failed = _layout(eng, len(seq), work)
    if failed:
        for st in out.values():
            st.why = failed
        return out
    gx0 = min(x for x, _y, _w, _h in place.values())
    gy0 = min(y for _x, y, _w, _h in place.values())
    canvas = (
        max(x + w for x, _y, w, _h in place.values()) - gx0,
        max(y + h for _x, y, _w, h in place.values()) - gy0,
    )
    index = {p.path: n for n, p in enumerate(seq, start=1)}
    for k, ps in groups.items():
        st = out[k]
        mine = {index[p.path]: p for p in ps if index.get(p.path) in place}
        for p in ps:
            if p.path in index and index[p.path] not in place:
                st.left_out[p.master] = "Siril didn't place it on the canvas"
        if not mine:
            st.why = "none of its panels could be placed"
            continue
        if note := _apart(mine, place):
            st.notes.append(note)
        st.path, st.why = _filter_mosaic(eng, k, mine, place, (gx0, gy0, *canvas), registered, len(seq), work)
    return out


def _factor(m: Master, ref: Master) -> float:
    """How much to enlarge `m` to match the reference's pixel scale, from the plate solves (1 when unknown)."""
    from .solving import framing

    a, b = framing(m.dataset), framing(ref.dataset)
    if not a or not b or not a["scale"] or not b["scale"]:
        return 1.0
    return float(a["scale"]) / float(b["scale"])


def _stitch(eng, rows: list[CombinedMaster], work: Path) -> dict[int, Stitched]:  # noqa: ANN001
    """Each filter of a mosaic project placed on the one canvas, from its masters' files and stored solves."""
    from apps.catalogue.api_library import label

    def panel(m: Master) -> Panel:
        return Panel(m.pk, label(m.dataset), Path(m.output_path), m.solve or {})

    ref = rows[0].reference
    assert ref is not None
    groups = {
        cm.pk: [
            panel(m)
            for m in Master.objects.filter(pk__in=[i["master"] for i in cm.inputs]).select_related(
                "dataset", "dataset__rig"
            )
            if m.output_path and Path(m.output_path).exists()
        ]
        for cm in rows
    }
    report_progress(0.0, f"Placing {sum(len(v) for v in groups.values())} masters on the mosaic")
    return _mosaic_all(eng, groups, panel(ref), work)


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def stitch_mosaic(collection_id: int, combined_ids: list[int]) -> dict:
    """Stitch mosaic (004-DR-32): each filter's panels placed on one canvas by their plate solutions."""
    return _combine(collection_id, combined_ids)


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def stack_together(collection_id: int, combined_ids: list[int]) -> dict:
    """Stack together (004-DR-32): masters of one field and filter stacked into a deeper master."""
    return _combine(collection_id, combined_ids)


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def combine(collection_id: int, combined_ids: list[int]) -> dict:
    """Jobs queued before the two operations had their own names; each row says which it is."""
    return _combine(collection_id, combined_ids)


def _combine(collection_id: int, combined_ids: list[int]) -> dict:
    from apps.engine.siril import engine

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
    # Stitch mosaic: every filter's panels are placed on one canvas by their plate solutions, so HOO and SHO line
    # up across the whole mosaic (004-DR-31); Stack together: each filter's masters registered and stacked
    stitch = rows[0].method == STITCH
    try:
        mosaics: dict[int, Stitched] = {}
        if stitch:
            mosaics = _stitch(eng, rows, root / "mosaic")
        for n, cm in enumerate(rows):
            what = (
                f"Stitching the {cm.filter_norm} mosaic"
                if stitch
                else f"Stacking {len(cm.inputs)} {cm.filter_norm} masters together"
            )
            report_progress(n / len(rows), what)
            try:
                if stitch:
                    _place_mosaic(cm, mosaics, out_dir, collection_id)
                else:
                    _register_and_stack(eng, cm, ref, rows[0].reference, root, out_dir, collection_id)
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("Combining %s failed", cm.filter_norm)
                CombinedMaster.objects.filter(pk=cm.pk).update(
                    state=MasterState.FAILED, error=str(exc), finished_at=timezone.now()
                )
    except Exception as exc:
        # the canvas itself couldn't be made (Siril stopped, a file unreadable): every filter says so
        what = "Couldn't stitch the mosaic" if stitch else "Couldn't stack together"
        CombinedMaster.objects.filter(pk__in=combined_ids, state=MasterState.RUNNING).update(
            state=MasterState.FAILED, error=f"{what}: {exc}", finished_at=timezone.now()
        )
        raise
    finally:
        shutil.rmtree(root, ignore_errors=True)
        _heavy.__exit__(None, None, None)
    _after_combine(rows, collection_id)
    return {"combined": done, "of": len(rows)}


def _combined_target(out_dir: Path, cm: CombinedMaster) -> Path:
    tag = f"p{cm.project_id}_" if cm.project_id else ""
    return out_dir / f"combined_{tag}{cm.filter_norm}_v{cm.version}.fit".replace(" ", "_")


def _make_current(
    cm: CombinedMaster, target: Path, inputs: list[dict], reason: str, collection_id: int
) -> None:
    """Preview the combined master, make it current, and supersede the filter's earlier one."""
    from .previews import render

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
        state_reason=reason,
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


def older_masters(inputs: list[dict]) -> list[str]:
    """A stale master (newer subs since) never blocks a stitch or a stack: it is used as it is, and said so."""
    return [f"{i['label']} uses an older master (new subs since)." for i in inputs if i.get("stale")]


def _place_mosaic(
    cm: CombinedMaster, mosaics: dict[int, Stitched], out_dir: Path, collection_id: int
) -> None:
    """A filter's mosaic, already on the shared canvas, made current; the panels left out are named, with why."""
    st = mosaics.get(cm.pk) or Stitched(why="none of its panels' files could be found")
    inputs = [i | {"registered": i["master"] not in st.left_out} for i in cm.inputs]
    missing = "; ".join(
        f"{i['label']}: {st.left_out[i['master']]}" for i in cm.inputs if i["master"] in st.left_out
    )
    if st.path is None:
        CombinedMaster.objects.filter(pk=cm.pk).update(inputs=inputs)
        raise RuntimeError(
            f"Couldn't stitch the {cm.filter_norm} mosaic: {st.why}." + (f" {missing}." if missing else "")
        )
    target = _combined_target(out_dir, cm)
    shutil.copyfile(st.path, target)
    placed = sum(1 for i in inputs if i["registered"])
    reason = [
        f"Stitched from {placed} panel master{'s' if placed != 1 else ''}, placed by their plate solutions."
    ]
    if missing:
        reason.append(f"Left out: {missing}.")
    reason += st.notes + older_masters(inputs)
    _make_current(cm, target, inputs, " ".join(reason), collection_id)


def _register_and_stack(
    eng,  # noqa: ANN001
    cm: CombinedMaster,
    ref: Path,
    reference: Master,
    root: Path,
    out_dir: Path,
    collection_id: int,
) -> None:
    """Align each of the filter's masters to the reference, then stack them weighted by their subs."""
    aligned: list[tuple[Path, int]] = []
    inputs = []
    for i, inp in enumerate(cm.inputs):
        m = Master.objects.filter(pk=inp["master"]).first()
        src = Path(m.output_path) if m else None
        got = (
            _align(eng, ref, src, root / f"{cm.filter_norm}_{i}", _factor(m, reference))
            if m and src and src.exists()
            else None
        )
        inputs.append(inp | {"registered": got is not None})
        if got is not None:
            aligned.append((got, inp.get("subs") or 1))
    if not aligned:
        CombinedMaster.objects.filter(pk=cm.pk).update(inputs=inputs)
        raise RuntimeError(
            "Couldn't stack together: stars didn't match the reference. Field or pixel scale too different; "
            "stack it with its own rig."
        )
    target = _combined_target(out_dir, cm)
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
        eng.run(f"stack c_ rej n -norm=addscale -weight=nbstack -out={target.with_suffix('')}", timeout=3600)
    left_out = [i["label"] for i in inputs if not i["registered"]]
    reason = [f"Left out (stars didn't match the reference): {', '.join(left_out)}."] if left_out else []
    _make_current(cm, target, inputs, " ".join(reason + older_masters(inputs)), collection_id)


def _after_combine(rows: list[CombinedMaster], collection_id: int) -> None:
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
    what = f"{cm.filter_norm} mosaic" if cm.method == STITCH else f"{cm.filter_norm} stacked master"
    if new_subs > 0:
        return f"{what} is stale: {new_subs} new subs since {when}."
    return f"{what} is stale: its datasets have newer masters since {when}."
