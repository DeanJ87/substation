"""C2: matching lights to master darks and flats (spec 002 US1)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Frame, FrameStatus, FrameType, Night
from apps.processing.matching import match

pytestmark = pytest.mark.django_db

T = datetime(2026, 9, 28, 21, 0, tzinfo=UTC)


def frame(sha: str, kind: str, night: date | None = None, **kw) -> Frame:
    n = Night.objects.get_or_create(site_key="x", date=night)[0] if night else None
    fields = {"camera": "ATR2600M", "xbin": 1, "ybin": 1, "gain": 120, "offset": 80, **kw}
    return Frame.objects.create(
        sha256=sha.ljust(64, "0"),
        size_bytes=1,
        format="xisf",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=kind,
        night=n,
        **fields,
    )


def light(**kw) -> Frame:
    base = {"exptime_s": 600.0, "ccd_temp_c": -19.9, "filter_norm": "Hα"}
    return frame("l", FrameType.LIGHT, date(2026, 9, 28), **(base | kw))


def test_dark_within_tolerance_and_latest_flat_before():
    frame("d20", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    frame("d10", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-10.0)
    frame("fold", FrameType.MASTER_FLAT, date(2026, 8, 15), filter_norm="Hα")
    frame("fnew", FrameType.MASTER_FLAT, date(2026, 9, 20), filter_norm="Hα")
    frame("fafter", FrameType.MASTER_FLAT, date(2026, 10, 1), filter_norm="Hα")
    frame("foiii", FrameType.MASTER_FLAT, date(2026, 9, 27), filter_norm="OIII")
    m = match(light())
    assert m.ok
    assert m.dark.sha256.startswith("d20") and m.dark_note == "Exact match"
    assert m.flat.sha256.startswith("fnew") and m.flat_note == "8 days before" and not m.weak


def test_an_old_flat_is_not_weak_by_default():
    """Owner: old flats are fine if the optical train hasn't changed; age is information, not evidence."""
    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    frame("f", FrameType.MASTER_FLAT, date(2026, 8, 15), filter_norm="hα")  # case differs: still matches
    m = match(light())
    assert m.ok and not m.weak and m.flat_note == "44 days before"


def test_weak_flat_rule_is_opt_in(settings):
    from apps.libraries.models import InstallationSettings

    s = InstallationSettings.load()
    s.processing = {"calibration": {"weak_flat_days": 21}}
    s.save()
    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    frame("f", FrameType.MASTER_FLAT, date(2026, 8, 15), filter_norm="Hα")
    m = match(light())
    assert m.weak and m.flat_note == "Weak: 44 days before"


def test_waits_with_reasons():
    frame("d", FrameType.MASTER_DARK, exptime_s=300.0, set_temp_c=-20.0)
    frame("f", FrameType.MASTER_FLAT, date(2026, 10, 1), filter_norm="Hα")
    m = match(light())
    assert not m.ok
    assert m.reason == "Awaiting calibration: no 600 s dark; no Hα flat on or before 28 Sep."


def test_master_missing_metadata_waits_for_reconcile():
    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=None, gain=None, offset=None)
    frame("f", FrameType.MASTER_FLAT, date(2026, 9, 1), filter_norm="Hα")
    m = match(light())
    assert "the 600 s dark has no gain or offset or temperature: confirm it in Reconcile" in m.reason


def test_temperature_out_of_tolerance():
    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-10.0)
    frame("f", FrameType.MASTER_FLAT, date(2026, 9, 1), filter_norm="Hα")
    m = match(light())
    assert "no 600 s dark within 2 °C of −19.9 °C (have −10 °C)" in m.reason


def test_a_flat_from_another_lens_is_not_used():
    """Same camera, different optical train (A7 III on the Askar and on the TTArtisan): the flats don't mix."""
    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    frame("ftta", FrameType.MASTER_FLAT, date(2026, 9, 20), filter_norm="Hα", telescope="TTArtisan ED 500")
    sub = light(telescope="Askar 71F")
    m = match(sub)
    assert not m.ok and "no Hα flat for Askar 71F" in m.reason
    frame("faskar", FrameType.MASTER_FLAT, date(2026, 8, 1), filter_norm="Hα", telescope="Askar 71F")
    m = match(sub)
    assert m.ok and m.flat.sha256.startswith("faskar")


def test_an_8_bit_colour_sub_is_used_uncalibrated():
    """A DSLR left in JPEG mode saves processed 8-bit RGB: raw masters can't apply, so it isn't held waiting."""
    from apps.catalogue.models import HeaderSnapshot

    sub = light(camera="Sony A7 III", filter_norm="OSC")
    HeaderSnapshot.objects.create(frame=sub, geometry="6000:4000:3", sample_format="BITPIX=8")
    m = match(sub)
    assert m.no_calibration and "8-bit colour" in m.dark_note
    raw = frame(
        "raw", FrameType.LIGHT, date(2026, 9, 28), exptime_s=600.0, filter_norm="OSC", camera="Sony A7 III"
    )
    HeaderSnapshot.objects.create(frame=raw, geometry="6000:4000", sample_format="BITPIX=16")
    assert not match(raw).no_calibration


def test_an_8_bit_colour_sub_takes_a_colour_flat_and_raw_subs_never_do():
    """Owner: 8-bit colour sessions came with 8-bit colour flats; dividing by them corrects vignetting, roughly."""
    from apps.catalogue.models import HeaderSnapshot

    sub = light(camera="Sony A7 III", filter_norm="OSC", gain=1600, offset=None)
    HeaderSnapshot.objects.create(frame=sub, geometry="6000:4000:3", sample_format="BITPIX=8")
    rgb_flat = frame(
        "frgb",
        FrameType.MASTER_FLAT,
        date(2026, 9, 28),
        filter_norm="OSC",
        camera="Sony A7 III",
        gain=1600,
        offset=None,
    )
    HeaderSnapshot.objects.create(frame=rgb_flat, geometry="6000:4000:3", sample_format="Float32")
    m = match(sub)
    assert m.ok and not m.no_calibration and m.dark is None and m.flat.pk == rgb_flat.pk
    assert "colour flat" in m.flat_note
    raw = frame(
        "raw",
        FrameType.LIGHT,
        date(2026, 9, 28),
        exptime_s=600.0,
        filter_norm="OSC",
        camera="Sony A7 III",
        gain=1600,
        offset=None,
    )
    HeaderSnapshot.objects.create(frame=raw, geometry="6000:4000", sample_format="BITPIX=16")
    assert match(raw).flat is None


def test_a_rig_without_darks_uses_a_master_bias():
    """Uncooled cameras are often calibrated with flats and bias only: the rig says so, and lights don't wait."""
    from apps.catalogue.models import Dataset, Rig

    rig = Rig.objects.create(key="k", name="A7 III", calibration="flats")
    ds = Dataset.objects.create(group_key="g", target="M 31", filter_norm="OSC", display_name="M 31", rig=rig)
    sub = light(camera="Sony A7 III", filter_norm="OSC", gain=1600, offset=None, ccd_temp_c=None, dataset=ds)
    frame("f", FrameType.MASTER_FLAT, date(2026, 9, 20), filter_norm="OSC", camera="Sony A7 III")
    m = match(sub)
    assert not m.ok and "no master bias for Sony A7 III at gain 1600" in m.reason
    frame("b800", FrameType.MASTER_BIAS, date(2026, 9, 27), camera="Sony A7 III", gain=800)
    frame("b1600", FrameType.MASTER_BIAS, date(2026, 5, 1), camera="Sony A7 III", gain=1600)
    m = match(sub)
    assert m.ok and m.dark.sha256.startswith("b1600") and "Master bias" in m.dark_note
    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, camera="Sony A7 III", gain=1600, offset=None)
    assert match(sub).dark.sha256.startswith("d")  # a matching dark still wins
    rig.calibration = "masters"
    rig.save()
    Frame.objects.filter(sha256__startswith="d").delete()
    # uncooled, no dark: waits for a real dark (the bias fallback is off by default, owner 2026-10-13)
    assert not match(Frame.objects.get(pk=sub.pk)).ok


def test_a_master_of_another_size_is_not_used():
    """An A7 III writes 6024×4024 in some sessions and 6000×4000 in others: masters must be the light's size."""
    from apps.catalogue.models import HeaderSnapshot

    sub = light()
    HeaderSnapshot.objects.create(frame=sub, geometry="6024:4024")
    d = frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    f = frame("f", FrameType.MASTER_FLAT, date(2026, 9, 20), filter_norm="Hα")
    HeaderSnapshot.objects.create(frame=d, geometry="6000:4000")
    HeaderSnapshot.objects.create(frame=f, geometry="6000:4000")
    m = match(sub)
    assert not m.ok and "no 600 s dark at 6024×4024" in m.reason and "flat for" not in m.reason
    assert "no Hα flat at 6024×4024" in m.reason
    HeaderSnapshot.objects.filter(frame__in=[d, f]).update(geometry="6024:4024")
    assert match(Frame.objects.get(pk=sub.pk)).ok


def test_an_undated_flat_is_used_and_not_weak():
    """002 C19: an unknown age isn't evidence of a mismatch."""
    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    frame("f", FrameType.MASTER_FLAT, None, filter_norm="Hα")
    m = match(light())
    assert m.ok and not m.weak and "age is unknown" in m.flat_note


def test_a_master_outside_its_validity_window_is_not_used(admin_client):
    """002 C13: a window limits the nights a master calibrates; clearing it brings it back."""
    from apps.processing.models import MasterWindow

    frame("d", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    early = frame("fearly", FrameType.MASTER_FLAT, date(2026, 9, 1), filter_norm="Hα")
    late = frame("flate", FrameType.MASTER_FLAT, date(2026, 9, 20), filter_norm="Hα")
    sub = light()
    assert match(sub).flat.pk == late.pk
    r = admin_client.put(
        f"/api/v1/masters/{late.pk}/window", {"valid_to": "2026-09-25"}, content_type="application/json"
    )
    assert r.status_code == 200
    r = admin_client.put(
        f"/api/v1/masters/{late.pk}/window", {"valid_from": "2026-10-01"}, content_type="application/json"
    )
    assert MasterWindow.objects.get(frame=late).valid_from == date(2026, 10, 1)
    m = match(sub)
    assert m.flat.pk == early.pk  # the later flat is only valid from October
    admin_client.put(f"/api/v1/masters/{late.pk}/window", {}, content_type="application/json")
    assert not MasterWindow.objects.exists() and match(sub).flat.pk == late.pk
    bad = admin_client.put(
        f"/api/v1/masters/{late.pk}/window",
        {"valid_from": "2026-10-02", "valid_to": "2026-10-01"},
        content_type="application/json",
    )
    assert bad.status_code == 422


def _pending_flat_set(night: date, filt: str = "Hα"):
    from apps.catalogue.models import CalibrationSet
    from apps.processing.models import BuiltMaster

    start = datetime.combine(night, datetime.min.time(), tzinfo=UTC)
    cs = CalibrationSet.objects.create(
        type=FrameType.FLAT,
        camera="ATR2600M",
        filter_norm=filt,
        exptime_s=1.0,
        session_start_utc=start,
        session_end_utc=start,
        night=Night.objects.get_or_create(site_key="x", date=night)[0],
        frame_count=20,
    )
    return BuiltMaster.objects.create(calibration_set=cs, state="queued")


def test_waits_for_its_own_nights_flats_still_being_built():
    """Owner 2026-10-11: a light took the first flat master built while its own night's flats were queued."""
    frame("d20", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    frame("fold", FrameType.MASTER_FLAT, date(2026, 9, 20), filter_norm="Hα")
    b = _pending_flat_set(date(2026, 9, 28))
    sub = light()
    m = match(sub)
    assert not m.ok and m.flat is None and "waiting for the 28 Sep Hα flats" in m.reason
    b.state = "done"
    b.save()
    m = match(sub)
    assert m.ok and m.flat.sha256.startswith("fold")  # nothing pending any more: the older flat is fine


def test_an_older_pending_flat_does_not_hold_a_light_back():
    frame("d20", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-20.0)
    frame("fnew", FrameType.MASTER_FLAT, date(2026, 9, 25), filter_norm="Hα")
    _pending_flat_set(date(2026, 9, 1))  # further from the light than the one already built
    _pending_flat_set(date(2026, 9, 28), filt="OIII")  # another filter
    m = match(light())
    assert m.ok and m.flat.sha256.startswith("fnew")


def test_a_flat_sets_bias_must_match_its_offset_and_have_a_file():
    # owner 2026-10-12: ATR2600M flats at gain 100, offset 50 and offset 60 each need their own bias; a master
    # whose every copy has gone can't calibrate anything (the 15 Aug RGB flats)
    from apps.catalogue.models import CalibrationSet, Copy
    from apps.libraries.models import Library
    from apps.processing.calibration import flat_calibrator

    lib = Library.objects.create(name="l", mount_path="/x")
    b50 = frame("b50", FrameType.MASTER_BIAS, gain=100, offset=50)
    b60 = frame("b60", FrameType.MASTER_BIAS, gain=100, offset=60)
    gone = frame("b60gone", FrameType.MASTER_BIAS, gain=100, offset=60, date_obs_utc=T)
    for i, f in enumerate((b50, b60)):
        Copy.objects.create(
            frame=f,
            library=lib,
            rel_path=f"b{i}.fit",
            st_dev=1,
            st_ino=i,
            st_size=1,
            st_mtime_ns=1,
            present=True,
            first_seen_at=T,
            last_seen_at=T,
        )
    cs = CalibrationSet.objects.create(
        type=FrameType.FLAT,
        camera="ATR2600M",
        gain=100,
        offset=60,
        filter_norm="Hα",
        exptime_s=7.0,
        session_start_utc=T,
        session_end_utc=T,
        frame_count=20,
    )
    assert flat_calibrator(cs) == b60 and gone.pk != b60.pk
    cs.offset = 50
    assert flat_calibrator(cs) == b50


def test_a_much_softer_night_is_named_before_stacking():
    from apps.processing.masters import sharpness_note
    from apps.processing.models import MeasureState, SubMeasurement

    subs = []
    for i, (d, f) in enumerate([(date(2026, 4, 13), 2.7)] * 4 + [(date(2026, 4, 18), 4.3)] * 4):
        fr = frame(f"s{i}", FrameType.LIGHT, d)
        SubMeasurement.objects.create(frame=fr, state=MeasureState.DONE, fwhm_px=f)
        subs.append(fr)
    note = sharpness_note(subs)
    assert "18 Apr" in note and "13 Apr" in note and "4.3 px against 2.7 px" in note
    assert sharpness_note(subs[:4]) == ""


def test_a_pinned_match_without_a_dark_still_gets_one_or_says_why():
    # a flat chosen for a session pinned the match with no dark: the sub waited forever with no reason (2026-10-13)
    from apps.processing.matching import update_match
    from apps.processing.models import CalibrationMatch, MatchState

    flat = frame("fpin", FrameType.MASTER_FLAT, date(2026, 9, 20), filter_norm="Hα")
    lt = light(ccd_temp_c=-17.0)
    CalibrationMatch.objects.create(frame=lt, flat=flat, pinned=True, state=MatchState.AWAITING, reason="")
    cm = update_match(lt)
    assert cm.state == MatchState.AWAITING and "dark" in cm.reason and cm.flat_id == flat.pk
    frame("d17", FrameType.MASTER_DARK, exptime_s=600.0, set_temp_c=-17.0)
    cm = update_match(lt)
    assert cm.state == MatchState.MATCHED and cm.dark_id and cm.flat_id == flat.pk and cm.pinned


def test_an_uncooled_camera_uses_bias_when_no_dark_matches():
    # off by default (owner: take real darks); when switched on, the matching-ISO bias stands in
    from apps.libraries.models import InstallationSettings

    st = InstallationSettings.load()
    st.processing = {"calibration": {"bias_for_uncooled": True}}
    st.save()
    bias = frame("b1600", FrameType.MASTER_BIAS, camera="A7III", gain=1600, offset=None)
    frame(
        "f",
        FrameType.MASTER_FLAT,
        date(2026, 9, 20),
        camera="A7III",
        gain=1600,
        offset=None,
        filter_norm="OSC",
    )
    lt = light(camera="A7III", gain=1600, offset=None, ccd_temp_c=None, exptime_s=180.0, filter_norm="OSC")
    m = match(lt)
    assert m.dark == bias and "uncooled" in m.dark_note
    cooled = frame(
        "l2", FrameType.LIGHT, date(2026, 9, 28), exptime_s=180.0, ccd_temp_c=-20.0, filter_norm="Hα"
    )
    assert match(cooled).dark is None  # a cooled camera still waits for a real dark
