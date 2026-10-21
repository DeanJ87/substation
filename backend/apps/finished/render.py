"""The render data for a finished project (020-FR-007..010), schema version 1.

Built from what SubStation already knows about the linked projects' subs. Anything unknown is left out, never zero-
filled (020-FR-008). Totals use the same denormalised dataset counts the app shows (020-FR-009), and site
coordinates never leave this module: only a region name, Bortle class and latitude rounded to whole degrees
(020-FR-010)."""

from __future__ import annotations

import re
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
    if f.role == FileRole.STEP and f.role_order:
        return f"step/{f.role_order}"
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


def _fingerprint(proj: FinishedProject) -> str:
    """Everything the render data is built from (020-DR-11), cheaply: the folder's files and settings, the linked
    projects (kind, panels), their collections, the datasets in them with their counts, and aggregates over their
    subs (count, newest catalogued, graded, verdict, measured and solved, and site sums so a corrected location
    shows), plus the site descriptions. Any change here can change the render data, so it moves updated_at."""
    import hashlib
    import json

    from django.db.models import Count, Max, Sum

    from apps.catalogue.models import UserVerdict

    linked = list(proj.linked_projects.select_related("collection").order_by("pk"))
    dss = list(
        Dataset.objects.filter(project__in=linked)
        .order_by("pk")
        .values_list(
            "pk",
            "project_id",
            "panel",
            "filter_norm",
            "target",
            "telescope",
            "camera",
            "rig_id",
            "accepted_count",
            "down_count",
            "rejected_count",
            "accepted_integration_s",
        )
    )
    frames = Frame.objects.filter(dataset__project__in=linked, frame_type=FrameType.LIGHT)
    agg = frames.aggregate(
        n=Count("pk"),
        cat=Max("catalogued_at"),
        lat=Sum("site_lat"),
        lon=Sum("site_lon"),
    )
    parts = {
        "proj": [proj.name, proj.kind, proj.subject, proj.missing, proj.distance_ly, proj.distance_source],
        "files": list(
            proj.files.order_by("rel_path").values_list(
                "rel_path",
                "size_bytes",
                "mtime",
                "missing",
                "role",
                "role_filter",
                "role_order",
                "role_label",
            )
        ),
        "linked": [(p.pk, p.kind, p.planned_panels, p.collection_id) for p in linked],
        "collections": sorted(
            {
                (p.collection.pk, p.collection.name, p.collection.objects_text, p.collection.constellation)
                for p in linked
            }
        ),
        "datasets": dss,
        "frames": agg,
        "graded": MachineGrade.objects.filter(frame__in=frames).aggregate(t=Max("graded_at"), n=Count("pk")),
        "verdicts": UserVerdict.objects.filter(frame__in=frames).aggregate(
            t=Max("created_at"), n=Count("pk")
        ),
        "measured": SubMeasurement.objects.filter(frame__in=frames).aggregate(t=Max("measured_at")),
        "solved": PlateSolve.objects.filter(frame__in=frames).aggregate(t=Max("solved_at"), n=Count("pk")),
        "sites": list(
            Library.objects.order_by("pk").values_list(
                "pk", "site_lat", "site_lon", "site_region", "site_bortle"
            )
        ),
        "install": [
            (s.site_lat, s.site_lon, s.site_region, s.site_bortle) for s in [InstallationSettings.load()]
        ],
    }
    return hashlib.sha256(json.dumps(parts, default=str, sort_keys=True).encode()).hexdigest()


def changed_at(proj: FinishedProject):  # noqa: ANN201
    """When the render data last changed (020-DR-11): the moment its fingerprint last differed. Moving a dataset
    into a linked project, changing a project's kind, a regrade, a new sub, a relink, a role or a replaced file all
    move it, so `since` polling never misses a change. Never in the future."""
    from django.utils import timezone

    now = timezone.now()
    fp = _fingerprint(proj)
    if fp != proj.data_fingerprint or proj.data_changed_at is None:
        FinishedProject.objects.filter(pk=proj.pk).update(data_fingerprint=fp, data_changed_at=now)
        proj.data_fingerprint, proj.data_changed_at = fp, now
    return min(proj.data_changed_at, now)


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


_CATALOGUE = re.compile(r"^(NGC|IC|M|Sh ?2|SH2|Sh2|vdB|LDN|LBN|B|C|Abell|Arp|Mel|Cr|Caldwell)[ -]?\d+", re.I)


def _target(proj: FinishedProject, dss: list[Dataset], solves: list[PlateSolve]) -> dict[str, Any]:
    cols = [c for c in {d.collection for d in dss} if c is not None]
    col = cols[0] if cols else None
    names = [n.strip() for n in (col.objects_text if col else "").split("·") if n.strip()]
    names += [t for t, _ in Counter(d.target for d in dss).most_common()]
    catalogued = [n for n in names if _CATALOGUE.match(n)]  # IC 434 rather than "FlameNebula"
    name = catalogued[0] if catalogued else (names[0] if names else proj.subject)
    common = col.name if col and col.name != name else (proj.subject if proj.subject != name else None)
    t: dict[str, Any] = {
        "name": name,
        "common_name": common,
        "constellation": (col.constellation if col else None) or None,
        "distance_ly": _r(proj.distance_ly, 0) if proj.distance_ly else None,  # 020-DR-13
        "distance_source": (proj.distance_source or None) if proj.distance_ly else None,
    }
    ok = [s for s in solves if s.ra_deg is not None and s.dec_deg is not None]
    if ok:
        from apps.processing.sky import median_pointing

        ra, dec = median_pointing(ok)
        t["ra_deg"], t["dec_deg"] = _r(ra, 4), _r(dec, 4)
    return t


SiteKey = tuple[int, int]  # latitude and longitude rounded to whole degrees: the finest a site is ever shown


def _site_key(f: Frame) -> SiteKey | None:
    if f.site_lat is None or f.site_lon is None:
        return None
    return round(f.site_lat), round(f.site_lon)


def _site_totals(graded: list[Frame], used: list[Frame]) -> tuple[Counter[SiteKey], dict[SiteKey, float]]:
    """Used subs and their integration per site. Every graded sub's site is listed, so a site whose subs were all
    rejected still has an id (with 0 used) and every quality entry can name its site."""
    counts: Counter[SiteKey] = Counter({k: 0 for f in graded if (k := _site_key(f))})
    time: dict[SiteKey, float] = defaultdict(float)
    for f in used:
        k = _site_key(f)
        if k:
            counts[k] += 1
            time[k] += f.exptime_s or 0
    return counts, time


def _site_sources(used: list[Frame]) -> dict[SiteKey, list[Library]]:
    """Where each site's region and Bortle may come from: its subs' libraries, most subs first."""
    from apps.catalogue.models import Copy

    by_frame = {f.pk: _site_key(f) for f in used}
    libs_by_site: dict[SiteKey, Counter[int]] = defaultdict(Counter)
    pairs = Copy.objects.filter(frame__in=list(by_frame)).values_list("frame_id", "library_id")
    for frame_id, lib_id in pairs:
        k = by_frame.get(frame_id)
        if k:
            libs_by_site[k][lib_id] += 1
    libs = {
        lib.pk: lib for lib in Library.objects.filter(pk__in={i for c in libs_by_site.values() for i in c})
    }
    return {k: [libs[i] for i, _ in c.most_common() if i in libs] for k, c in libs_by_site.items()}


def _describe(k: SiteKey, sources: list[Library | InstallationSettings]) -> tuple[str | None, int | None]:
    """A region and Bortle only from a source whose own site is this place (020-DR-07)."""
    for src in sources:
        if src.site_lat is None or src.site_lon is None:
            continue
        if (round(src.site_lat), round(src.site_lon)) == k and (src.site_region or src.site_bortle):
            return src.site_region or None, src.site_bortle
    return None, None


def _sites(graded: list[Frame], used: list[Frame]) -> tuple[list[dict[str, Any]], dict[SiteKey, str]]:
    """Every place the subs were shot (020-DR-07): one entry per whole-degree site, ids s1, s2 … by integration.
    A master made from home and remote data is several truths, not one average."""
    counts, time = _site_totals(graded, used)
    if not counts:
        return [], {}
    sources = _site_sources(graded)
    inst = InstallationSettings.load()
    ids: dict[SiteKey, str] = {}
    out = []
    for n, (k, subs) in enumerate(sorted(counts.items(), key=lambda kv: (-time[kv[0]], -kv[1])), start=1):
        ids[k] = f"s{n}"
        region, bortle = _describe(k, [*sources.get(k, []), inst])
        out.append(
            {
                "id": ids[k],
                "region": region,
                "bortle": bortle,
                "lat_1deg": k[0],
                "subs": subs,
                "integration_s": _r(time[k], 1),
            }
        )
    return out, ids


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


def _is_mosaic(proj: FinishedProject) -> bool:
    """The owner's project kind decides (020-DR-10): subs can carry panel numbers from capture software (a
    mosaic template, a reframe) on what is really one field."""
    return any(lp.kind == "mosaic" for lp in proj.linked_projects.all())


def _timeline(
    used: list[Frame], target: dict[str, Any], site_ids: dict[SiteKey, str], mosaic: bool = True
) -> list[dict[str, Any]]:
    """Per observing night, filter, panel and site: the subs used and the target's track that night, worked out
    from that site rounded to whole degrees, never from stored positions (020-FR-007, 020-DR-01, 020-DR-07)."""
    rows: dict[tuple[Any, str, int | None, SiteKey | None], list[Frame]] = defaultdict(list)
    for f in used:
        if f.night is not None:
            rows[(f.night.date, f.filter_norm or "", f.panel if mosaic else None, _site_key(f))].append(f)
    ra, dec = target.get("ra_deg"), target.get("dec_deg")
    out = []
    order = sorted(
        rows.items(),
        key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or 0, site_ids.get(kv[0][3], "") if kv[0][3] else ""),
    )
    for (night, flt, panel, site), fs in order:
        times = _decimate([f.date_obs_utc for f in fs if f.date_obs_utc], TRACK_POINTS)
        track = None
        if site and ra is not None and dec is not None and times:
            from apps.processing.sky import alt_az

            alts, azs, _ = alt_az(
                [ra] * len(times), [dec] * len(times), times, float(site[0]), float(site[1])
            )
            track = [[_r(az, 1), _r(alt, 1)] for az, alt in zip(azs, alts, strict=True)]
        out.append(
            {
                "night": night.isoformat(),
                "filter": flt or None,
                "panel": panel,
                "site": site_ids.get(site) if site else None,
                "subs": len(fs),
                "integration_s": _r(sum(f.exptime_s or 0 for f in fs), 1),
                "track": track,
            }
        )
    return out


def _quality(
    lights: list[Frame], eff: dict[str, Any], meas: dict[str, SubMeasurement], site_ids: dict[SiteKey, str]
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
                "site": site_ids.get(k) if (k := _site_key(f)) else None,
                "fwhm_arcsec": _r(m.fwhm_arcsec, 2) if m else None,
                "fwhm_px": _r(m.fwhm_px, 2) if m else None,
                "stars": m.stars if m else None,
                "snr": _r(m.snr, 2) if m else None,
                "verdict": e.verdict,
            }
        )
    return out


def files_url(proj: FinishedProject) -> str:
    """Root-relative, so the renderer joins them with the SubStation address it already uses."""
    return f"/api/v1/render/projects/{proj.pk}/files"


def _frames(proj: FinishedProject) -> dict[str, Any]:
    url = files_url(proj)
    frames: dict[str, Any] = {"per_filter": {}, "progressive": [], "steps": []}
    files = role_files(proj)
    for key in sorted(files, key=lambda k: (k.count("/"), k.split("/")[-1].zfill(6))):
        if key.startswith("per_filter/"):
            frames["per_filter"][key.split("/", 1)[1]] = f"{url}/{quote(key, safe='/')}"
        elif key.startswith("progressive/"):
            frames["progressive"].append(f"{url}/{key}")
        elif key.startswith("step/"):
            f = files[key]
            frames["steps"].append(
                {"order": f.role_order, "label": f.role_label or None, "url": f"{url}/{key}"}
            )
        else:
            frames[key] = f"{url}/{key}"
    frames["thumb"] = f"{url}/thumb"
    return frames


def _capture(
    proj: FinishedProject,
    dss: list[Dataset],
    used: list[Frame],
    solves,
    sites: list[dict[str, Any]],  # noqa: ANN001
) -> dict:
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
    planned = [
        p.planned_panels for p in proj.linked_projects.all() if p.kind == "mosaic" and p.planned_panels
    ]
    mosaic = {"panels": max([len(panels), *planned])} if _is_mosaic(proj) else None
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
        "sites": sites,
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
    graded = [f for f in lights if eff[f.pk].verdict is not None]
    sites, site_ids = _sites(graded, used)
    frames = _frames(proj)
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
        "capture": _capture(proj, dss, used, solves, sites),
        "timeline": _timeline(used, target, site_ids, _is_mosaic(proj)),
        "quality": _quality(lights, eff, meas, site_ids),
        "frames": frames,
        "processing": [s["label"] for s in frames["steps"] if s.get("label")],
    }
    return _clean(data)
