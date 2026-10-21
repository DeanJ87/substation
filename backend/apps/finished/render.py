"""The render data for a finished project (020-FR-007..010), schema version 1.

Built from what SubStation already knows about the linked projects' subs. Anything unknown is left out, never zero-
filled (020-FR-008). Totals use the same denormalised dataset counts the app shows (020-FR-009), and site
coordinates never leave this module: only a region name, Bortle class and latitude rounded to whole degrees
(020-FR-010)."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import quote

from apps.catalogue.models import Dataset, DatasetNight, Frame, FrameStatus, FrameType
from apps.libraries.models import InstallationSettings, Library
from apps.processing.effective import effective
from apps.processing.models import MachineGrade, PlateSolve, SubMeasurement

from .models import FileRole, FinishedProject
from .scan import IMAGE_EXTS

SCHEMA_VERSION = 1
TRACK_POINTS = 48  # samples per night track; plenty for a curve, small enough to ship


def _r(x: float | None, n: int = 3) -> float | None:
    return None if x is None else round(float(x), n)


def _clean(d: Any) -> Any:
    """Drop None, empty lists and empty dicts, recursively (020-FR-008)."""
    if isinstance(d, dict):
        out = {k: _clean(v) for k, v in d.items()}
        return {k: v for k, v in out.items() if v is not None and v != [] and v != {}}
    if isinstance(d, list):
        return [x for x in (_clean(v) for v in d) if x != {}]
    return d


def file_key(f) -> str | None:  # noqa: ANN001
    if f.role == FileRole.PER_FILTER and f.role_filter:
        return f"per_filter/{f.role_filter}"
    if f.role == FileRole.PROGRESSIVE and f.role_order:
        return f"progressive/{f.role_order}"
    return f.role or None


def role_files(proj: FinishedProject) -> dict[str, Any]:
    """Served files by key (020-FR-013): display-ready images with a role, outputs only."""
    out: dict[str, Any] = {}
    for f in proj.files.filter(missing=False).exclude(role="").exclude(section="project"):
        if f.ext not in IMAGE_EXTS:
            continue
        key = file_key(f)
        if key and key not in out:
            out[key] = f
    return out


def changed_at(proj: FinishedProject):  # noqa: ANN201
    """When anything in the render data last changed: the folder's files, links, roles and processing, and the
    linked projects' subs, grades and verdicts (so `since` polling sees regrades too). Never in the future."""
    from django.db.models import Max
    from django.utils import timezone

    from apps.catalogue.models import UserVerdict

    linked = proj.linked_projects.all()
    times = [proj.changed_at]
    times.append(Frame.objects.filter(dataset__project__in=linked).aggregate(t=Max("catalogued_at"))["t"])
    times.append(
        MachineGrade.objects.filter(frame__dataset__project__in=linked).aggregate(t=Max("graded_at"))["t"]
    )
    times.append(
        UserVerdict.objects.filter(frame__dataset__project__in=linked).aggregate(t=Max("created_at"))["t"]
    )
    return min(max(t for t in times if t is not None), timezone.now())


def offered(proj: FinishedProject) -> tuple[bool, str]:
    """Whether the render API offers the project, and why not."""
    if proj.missing:
        return False, "its folder is missing"
    if not proj.linked_projects.exists():
        return False, "not linked to a SubStation project"
    if "final" not in role_files(proj):
        return False, "needs a final image"
    return True, ""


def _datasets(proj: FinishedProject) -> list[Dataset]:
    return list(
        Dataset.objects.filter(project__in=proj.linked_projects.all()).select_related("rig", "collection")
    )


def _lights(dss: list[Dataset]) -> list[Frame]:
    return list(
        Frame.objects.filter(dataset__in=dss, frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED)
        .select_related("night")
        .prefetch_related("verdicts")
        .order_by("date_obs_utc")
    )


def _target(proj: FinishedProject, dss: list[Dataset], solves: list[PlateSolve]) -> dict[str, Any]:
    cols = [c for c in {d.collection for d in dss} if c is not None]
    col = cols[0] if cols else None
    names = [n.strip() for n in (col.objects_text if col else "").split("·") if n.strip()]
    name = (
        names[0] if names else (Counter(d.target for d in dss).most_common(1)[0][0] if dss else proj.subject)
    )
    common = col.name if col and col.name != name else (proj.subject if proj.subject != name else None)
    t: dict[str, Any] = {
        "name": name,
        "common_name": common,
        "constellation": (col.constellation if col else None) or None,
    }
    ok = [s for s in solves if s.ra_deg is not None and s.dec_deg is not None]
    if ok:
        from apps.processing.sky import median_pointing

        ra, dec = median_pointing(ok)
        t["ra_deg"], t["dec_deg"] = _r(ra, 4), _r(dec, 4)
    return t


def _site(lights: list[Frame]) -> dict[str, Any] | None:
    from apps.catalogue.models import Copy

    lib_ids = Counter(
        Copy.objects.filter(frame__in=[f.pk for f in lights[:500]]).values_list("library_id", flat=True)
    )
    lib = Library.objects.filter(pk=lib_ids.most_common(1)[0][0]).first() if lib_ids else None
    inst = InstallationSettings.load()
    region = (lib.site_region if lib else "") or inst.site_region or None
    bortle = (lib.site_bortle if lib else None) or inst.site_bortle
    lats = [f.site_lat for f in lights if f.site_lat is not None]
    lat = (
        statistics.median(lats)
        if lats
        else (lib.site_lat if lib and lib.site_lat is not None else inst.site_lat)
    )
    site = {"region": region, "bortle": bortle, "lat_1deg": round(lat) if lat is not None else None}
    return site if any(v is not None for v in site.values()) else None


def _decimate(points: list[Any], n: int) -> list[Any]:
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


def _filters(dss: list[Dataset], used: list[Frame]) -> list[dict[str, Any]]:
    by_filter: dict[str, list[Dataset]] = defaultdict(list)
    for d in dss:
        by_filter[d.filter_norm].append(d)
    out = []
    for name, group in sorted(
        by_filter.items(), key=lambda kv: -sum(d.accepted_integration_s for d in kv[1])
    ):
        exps = Counter(f.exptime_s for f in used if f.filter_norm == name and f.exptime_s)
        out.append(
            {
                "name": name or None,  # data with no filter keeps its totals but has no name (020-FR-009)
                "subs": sum(d.accepted_count + d.down_count for d in group),
                "exptime_s": exps.most_common(1)[0][0] if exps else None,
                "integration_s": _r(sum(d.accepted_integration_s for d in group), 1),
            }
        )
    return out


def _median(xs: list[float], n: int = 3) -> float | None:
    return _r(statistics.median(xs), n) if xs else None


def _rigs(dss: list[Dataset], solves: list[PlateSolve]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], set[int]] = defaultdict(set)
    for d in dss:
        groups[(d.rig.telescope if d.rig else d.telescope, d.rig.camera if d.rig else d.camera)].add(d.pk)
    out = []
    for (tel, cam), gids in groups.items():
        rs = [s for s in solves if s.frame.dataset_id in gids]
        fovw = _median([s.fov_w_deg for s in rs if s.fov_w_deg])
        fovh = _median([s.fov_h_deg for s in rs if s.fov_h_deg])
        out.append(
            {
                "telescope": tel or None,
                "camera": cam or None,
                "pixel_scale_arcsec": _median([s.scale_arcsec for s in rs if s.scale_arcsec]),
                "fov_deg": [fovw, fovh] if fovw and fovh else None,
            }
        )
    return out


def _coarse_site(lights: list[Frame]) -> tuple[float, float] | None:
    """The site rounded to whole degrees, for drawing tracks only. Real alt/az at real times would give the site
    away to about a kilometre (020-FR-010), so tracks are worked out again from here."""
    lats = [f.site_lat for f in lights if f.site_lat is not None]
    lons = [f.site_lon for f in lights if f.site_lon is not None]
    if not lats or not lons:
        return None
    return float(round(statistics.median(lats))), float(round(statistics.median(lons)))


def _timeline(
    used: list[Frame], target: dict[str, Any], site: tuple[float, float] | None
) -> list[dict[str, Any]]:
    """Per observing night, filter and panel: the subs used and the target's track that night (020-FR-007)."""
    rows: dict[tuple[Any, str, int | None], list[Frame]] = defaultdict(list)
    for f in used:
        if f.night is not None:
            rows[(f.night.date, f.filter_norm or "", f.panel)].append(f)
    ra, dec = target.get("ra_deg"), target.get("dec_deg")
    out = []
    for (night, flt, panel), fs in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or 0)):
        times = _decimate([f.date_obs_utc for f in fs if f.date_obs_utc], TRACK_POINTS)
        track = None
        if site and ra is not None and dec is not None and times:
            from apps.processing.sky import alt_az

            alts, azs, _ = alt_az([ra] * len(times), [dec] * len(times), times, site[0], site[1])
            track = [[_r(az, 1), _r(alt, 1)] for az, alt in zip(azs, alts, strict=True)]
        out.append(
            {
                "night": night.isoformat(),
                "filter": flt or None,
                "panel": panel,
                "subs": len(fs),
                "integration_s": _r(sum(f.exptime_s or 0 for f in fs), 1),
                "track": track,
            }
        )
    return out


def _quality(
    lights: list[Frame], eff: dict[str, Any], meas: dict[str, SubMeasurement]
) -> list[dict[str, Any]]:
    out = []
    for f in lights:
        e = eff[f.pk]
        if e.verdict is None or f.date_obs_utc is None:
            continue
        m = meas.get(f.pk)
        out.append(
            {
                "t": f.date_obs_utc.isoformat().replace("+00:00", "Z"),
                "filter": f.filter_norm or None,
                "fwhm_arcsec": _r(m.fwhm_arcsec, 2) if m else None,
                "fwhm_px": _r(m.fwhm_px, 2) if m else None,
                "stars": m.stars if m else None,
                "snr": _r(m.snr, 2) if m else None,
                "verdict": e.verdict,
            }
        )
    return out


def files_url(proj: FinishedProject) -> str:
    """Root-relative, so the renderer joins them with the SubStation address it already uses (and project.json
    carries the same links as the API)."""
    return f"/api/v1/render/projects/{proj.pk}/files"


def _frames(proj: FinishedProject) -> dict[str, Any]:
    url = files_url(proj)
    frames: dict[str, Any] = {"per_filter": {}, "progressive": []}
    for key in sorted(role_files(proj), key=lambda k: (k.count("/"), k.split("/")[-1].zfill(6))):
        if key.startswith("per_filter/"):
            frames["per_filter"][key.split("/", 1)[1]] = f"{url}/{quote(key, safe='/')}"
        elif key.startswith("progressive/"):
            frames["progressive"].append(f"{url}/{key}")
        else:
            frames[key] = f"{url}/{key}"
    frames["thumb"] = f"{url}/thumb"
    return frames


def _capture(
    proj: FinishedProject, dss: list[Dataset], lights: list[Frame], used: list[Frame], solves
) -> dict:  # noqa: ANN001
    """Totals from the datasets' own counts, as on screen (020-FR-009)."""
    if not dss:
        return {}
    acc = sum(d.accepted_count for d in dss)
    down = sum(d.down_count for d in dss)
    rej = sum(d.rejected_count for d in dss)
    nights = sorted(
        {x.night.date for x in DatasetNight.objects.filter(dataset__in=dss).select_related("night")}
    )
    panels = {d.panel for d in dss if d.panel is not None}
    planned = [p.planned_panels for p in proj.linked_projects.all() if p.planned_panels]
    mosaic = (
        {"panels": max([len(panels), *planned])} if len(panels) > 1 or any(n > 1 for n in planned) else None
    )
    return {
        "total_integration_s": _r(sum(d.accepted_integration_s for d in dss), 1),
        "subs_total": acc + down + rej,
        "subs_accepted": acc,
        "subs_down_weighted": down,
        "subs_rejected": rej,
        "nights": len(nights) or None,
        "first_night": nights[0].isoformat() if nights else None,
        "last_night": nights[-1].isoformat() if nights else None,
        "mosaic": mosaic,
        "filters": _filters(dss, used),
        "rigs": _rigs(dss, solves),
        "site": _site(lights),
    }


def build(proj: FinishedProject) -> dict[str, Any]:
    dss = _datasets(proj)
    lights = _lights(dss)
    ids = [f.pk for f in lights]
    grades = {g.frame_id: g for g in MachineGrade.objects.filter(frame_id__in=ids)}
    meas = {m.frame_id: m for m in SubMeasurement.objects.filter(frame_id__in=ids)}
    solves = list(PlateSolve.objects.filter(frame_id__in=ids, state="solved").select_related("frame"))
    eff = {f.pk: effective(f, list(f.verdicts.all()), grades.get(f.pk)) for f in lights}
    used = [f for f in lights if eff[f.pk].verdict in ("accept", "down")]
    target = _target(proj, dss, solves)
    data = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "id": str(proj.pk),
            "name": proj.name,
            "kind": proj.kind,
            "subject": proj.subject,
            "updated_at": changed_at(proj).isoformat(),
        },
        "target": target,
        "capture": _capture(proj, dss, lights, used, solves),
        "timeline": _timeline(used, target, _coarse_site(lights)),
        "quality": _quality(lights, eff, meas),
        "frames": _frames(proj),
        "processing": list(proj.processing or []),
    }
    return _clean(data)
