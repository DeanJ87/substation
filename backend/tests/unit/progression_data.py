"""Shared fixtures for the cumulative progressive stack tests (020-DR-15): a finished project linked to one
single-field project whose datasets hold graded, measured subs over a few nights."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import count
from pathlib import Path

import numpy as np

from apps.catalogue.models import Collection, Copy, Dataset, Frame, Night, Project
from apps.finished.models import FinishedProject
from apps.libraries.models import Library, LibraryRole
from apps.processing.models import MachineGrade, PlateSolve, SubMeasurement

_ids = count(1)
H, W = 60, 80


def finished(tmp_path: Path) -> tuple[FinishedProject, Project]:
    col = Collection.objects.create(name="Heart Nebula", objects_text="IC 1805")
    project = Project.objects.create(collection=col)
    root = tmp_path / "completed"
    (root / "Astro" / "IC 1805" / "2026 Heart").mkdir(parents=True, exist_ok=True)
    lib = Library.objects.create(
        name=f"completed{next(_ids)}", mount_path=str(root), role=LibraryRole.COMPLETED
    )
    fp = FinishedProject.objects.create(
        library=lib, rel_path="Astro/IC 1805/2026 Heart", kind="astro", subject="IC 1805", name="2026 Heart"
    )
    fp.linked_projects.set([project])
    return fp, project


def night(d: date) -> Night:
    return Night.objects.get_or_create(site_key="48,9", date=d)[0]


def subs(
    project: Project,
    flt: str,
    nights: list[tuple[date, int]],
    *,
    panel: int | None = None,
    scale: float | None = 1.5,
    cal_dir: Path | None = None,
    stars: int = 500,
    name: str = "Light_{i}.fit",
    noise: float = 30.0,
) -> list[Frame]:
    """`n` accepted subs of `flt` on each night, 300 s each; with `cal_dir`, each has a calibrated file there: a
    flat sky with a brighter plateau in the middle, and noise."""
    ds = Dataset.objects.filter(
        project=project, filter_norm=flt, panel=panel
    ).first() or Dataset.objects.create(
        group_key=f"g-{flt}-{panel}-{project.pk}",
        target="IC 1805",
        panel=panel,
        filter_norm=flt,
        display_name=f"IC 1805 {flt}",
        collection=project.collection,
        project=project,
    )
    lib = Library.objects.get_or_create(name="capture", defaults={"mount_path": "/nowhere"})[0]
    rng = np.random.default_rng(len(flt) * 1000 + Frame.objects.count())
    out = []
    for d, n in nights:
        nt = night(d)
        for k in range(n):
            i = next(_ids)
            when = datetime(d.year, d.month, d.day, 22, tzinfo=UTC) + timedelta(minutes=5 * k)
            f = Frame.objects.create(
                sha256=f"{i:064x}",
                size_bytes=1,
                format="fits",
                status="catalogued",
                frame_type="light",
                first_seen_at=when,
                target="IC 1805",
                filter_norm=flt,
                panel=panel,
                exptime_s=300,
                date_obs_utc=when,
                night=nt,
                dataset=ds,
            )
            Copy.objects.create(
                frame=f,
                library=lib,
                rel_path=f"s/{name.format(i=i)}",
                st_dev=1,
                st_ino=i,
                st_size=1,
                st_mtime_ns=1,
                first_seen_at=when,
                last_seen_at=when,
            )
            MachineGrade.objects.create(frame=f, verdict="accept", weight=1.0, reason="test")
            cal = ""
            if cal_dir is not None:
                cal_dir.mkdir(parents=True, exist_ok=True)
                cal = str(cal_dir / f"{f.pk[-16:]}.fit")
                write_sub(Path(cal), rng, noise)
            SubMeasurement.objects.create(
                frame=f, state="done", stars=stars + k, fwhm_arcsec=2.0, calibrated_path=cal
            )
            if scale:
                PlateSolve.objects.create(
                    frame=f,
                    state="solved",
                    ra_deg=38.2,
                    dec_deg=61.45,
                    scale_arcsec=scale,
                    fov_w_deg=2,
                    fov_h_deg=1.5,
                )
            out.append(f)
    return out


def write_sub(path: Path, rng: np.random.Generator, noise: float = 30.0) -> None:
    from astropy.io import fits

    data = np.full((H, W), 100.0, dtype=np.float32)
    data[15:45, 20:60] = 400.0
    data += rng.normal(0, noise, data.shape).astype(np.float32)
    fits.PrimaryHDU(data.astype(np.float32)).writeto(path, overwrite=True)
