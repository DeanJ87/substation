"""Plate solving (spec 009): Siril's solve output, as Siril 1.4.2 prints it, becomes centre, rotation, scale and
field; failures say why in plain English."""

from __future__ import annotations

from apps.processing.solving import _reason, parse_solution

M31 = """Up is +266.14 deg CounterclockWise wrt. N
Resolution:      2.449 arcsec/px
Focal length:  497.83 mm
Pixel size:      5.91 µm
Field of view:    04d 04m 52.01s x 02d 43m 14.67s
Image center: alpha: 00 42 35.930, delta: +41 26 34.279
Siril solve succeeded.""".splitlines()


def test_a_solve_is_read_from_siril_output():
    s = parse_solution(M31)
    assert abs(s["ra_deg"] - 10.6497) < 1e-3 and abs(s["dec_deg"] - 41.4429) < 1e-3
    assert s["rotation_deg"] == 266.14 and s["scale_arcsec"] == 2.449
    assert abs(s["fov_w_deg"] - 4.0811) < 1e-3 and abs(s["fov_h_deg"] - 2.7207) < 1e-3


def test_a_field_under_a_degree_is_minutes_not_degrees():
    # Siril drops the degrees under 1°: "26m 55.59s" is 0.449°, not 26.9° (IC 434, 2026-10-12)
    s = parse_solution(["Field of view:    26m 55.59s x 21m 32.30s"])
    assert abs(s["fov_w_deg"] - 0.44877) < 1e-4 and abs(s["fov_h_deg"] - 0.35897) < 1e-4


def test_southern_and_failed_solves():
    s = parse_solution(["Image center: alpha: 05 35 17.3, delta: -05 23 28.0"])
    assert abs(s["dec_deg"] + 5.3911) < 1e-3 and abs(s["ra_deg"] - 83.822) < 1e-2
    assert "catalogue" in _reason(["Offline: cannot download catalog"])
    assert "No catalogue match" in _reason(
        ["Plate solving failed: The image could not be aligned with the reference stars"]
    )


def test_framing_overlap_and_offsets():
    from apps.processing.solving import corners, overlap

    ref = {"ra": 314.0, "dec": 44.0, "rotation": 0.0, "fov_w": 2.7, "fov_h": 1.8}
    same = dict(ref)
    half = dict(ref, ra=314.0 + 1.35 / 0.7193)  # moved east by half the field width
    far = dict(ref, ra=320.0)
    assert overlap(same, ref) == 1.0
    assert 0.45 < overlap(half, ref) < 0.55
    assert overlap(far, ref) == 0.0
    c = corners(ref, ref)
    # top-left of an unmirrored, north-up image is north-east (east is left on the sky)
    assert abs(c[0][0] - 1.35) < 1e-9 and abs(c[0][1] - 0.9) < 1e-9
    assert abs(c[2][0] + 1.35) < 1e-9 and abs(c[2][1] + 0.9) < 1e-9
    m = corners(dict(ref, flipped=True), ref)  # mirrored: top-left is north-west
    assert abs(m[0][0] + 1.35) < 1e-9 and abs(m[0][1] - 0.9) < 1e-9
    # a mirrored solve checked against Siril's WCS: 230.14°, 4.08° × 2.72°, top-left at E+2.42 N+0.66
    g = dict(ref, rotation=230.14, fov_w=4.08, fov_h=2.72, flipped=True)
    tl = corners(g, g)[0]
    assert abs(tl[0] - 2.42) < 0.1 and abs(tl[1] - 0.66) < 0.1
    r = corners(dict(ref, rotation=90.0), ref)  # up points east: top-left lies south-east
    assert abs(r[0][0] - 0.9) < 1e-9 and abs(r[0][1] + 1.35) < 1e-9


def test_failed_solve_with_few_stars_blames_the_sky():
    from apps.processing.solving import _reason

    assert _reason(["log: Plate solving failed"], stars=24).startswith("Only 24 stars")
    assert _reason(["log: Plate solving failed"], stars=4000) == "Siril couldn't solve it."
