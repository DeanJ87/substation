"""G4: grading against the session median, with reasons (spec 003 v2 amendment) and the spike profile."""

from __future__ import annotations

from apps.processing.config import DEFAULTS
from apps.processing.grading import Sub, grade_spike, grade_standard, wfwhm

CFG = DEFAULTS["grading"]


def session(**changes: Sub) -> list[Sub]:
    subs = [Sub(f"s{i}", 1300 + i * 5, 1.5 + (i % 3) * 0.02, 450.0, 0.35, 0.94, 1.58) for i in range(10)]
    for k, v in changes.items():
        subs[int(k[1:])] = v
    return subs


def test_normal_subs_are_accepted():
    g, med = grade_standard(session(), CFG)
    assert all(x.verdict == "accept" and x.weight == 1.0 for x in g.values())
    assert 1300 < med["stars"] < 1350


def test_cloud_rejected_with_reason():
    g, _ = grade_standard(session(s3=Sub("s3", 560, 1.6, 520.0, 0.38, 0.92, 1.58)), CFG)
    assert g["s3"].verdict == "reject"
    assert g["s3"].reason.startswith("Stars 42% of median: cloud.")


def test_soft_sub_down_weighted_with_weight_and_arcsec():
    g, _ = grade_standard(session(s4=Sub("s4", 1300, 1.98, 450.0, 0.35, 0.94, 1.58)), CFG)
    assert g["s4"].verdict == "down"
    assert g["s4"].reason == "FWHM 3.13″, 30% above median: seeing."
    assert 0.5 < g["s4"].weight < 0.65


def test_no_stars_never_divides_by_zero():
    g, _ = grade_standard(session(s0=Sub("s0", 0, None, 900.0, None, None, 1.58)), CFG)
    assert g["s0"].verdict == "reject" and "No stars" in g["s0"].reason


def test_elongated_and_bright_background():
    g, _ = grade_standard(session(s1=Sub("s1", 1100, 1.5, 1000.0, 0.7, 0.71, 1.58)), CFG)
    assert g["s1"].verdict == "reject"
    assert g["s1"].notes  # the second problem is kept too
    assert any("moonlight" in n for n in [g["s1"].reason, *g["s1"].notes])


def test_a_brighter_background_with_as_many_stars_is_signal_not_sky_glow():
    """Owner 2026-10-10 (Soul Nebula Hα): on a transparent night the nebula filling the frame raises the median;
    with the stars all there, that's more signal, not moonlight."""
    g, _ = grade_standard(session(s1=Sub("s1", 1400, 1.5, 1200.0, 0.35, 0.94, 1.58)), CFG)
    assert g["s1"].verdict == "accept" and g["s1"].weight == 1.0
    g, _ = grade_standard(session(s1=Sub("s1", 700, 1.5, 1200.0, 0.35, 0.94, 1.58)), CFG)
    assert g["s1"].verdict == "reject" and "moonlight" in g["s1"].reason and "stars 53%" in g["s1"].reason


def test_near_threshold_is_flagged_for_review():
    g, _ = grade_standard(session(s2=Sub("s2", 960, 1.5, 450.0, 0.35, 0.94, 1.58)), CFG)
    assert g["s2"].verdict == "accept" and g["s2"].near


def test_wfwhm_matches_siril():
    assert round(wfwhm(3.4547, 798, 916), 4) == 4.3448  # docs/spikes phase 2, NGC 7000 P3 sub 1


def test_spike_profile():
    subs = session(
        s5=Sub("s5", 700, 1.5, 450.0, 0.3, 0.95, 1.58), s6=Sub("s6", 1300, 1.5, 450.0, 0.6, 0.80, 1.58)
    )
    g, _ = grade_spike(subs, DEFAULTS["spike_profile"])
    assert g["s5"].verdict == "reject" and "stars 700" in g["s5"].reason  # 700 < 0.6 × median, and wFWHM
    assert g["s6"].verdict == "reject" and "roundness 0.80" in g["s6"].reason
    assert sum(x.verdict == "reject" for x in g.values()) == 2


def test_a_session_of_elongated_stars_is_the_rig_not_the_subs():
    """Eccentricity follows the session: a lens that elongates every star doesn't reject the whole night, but a
    sub that trails beyond its session still does."""
    subs = [Sub(f"s{i}", 1300, 1.5, 450.0, 0.62 + (i % 3) * 0.01, 0.8, 1.58) for i in range(10)]
    subs[4] = Sub("s4", 1300, 1.5, 450.0, 0.85, 0.5, 1.58)
    g, _ = grade_standard(subs, CFG)
    assert all(g[f"s{i}"].verdict == "accept" for i in range(10) if i != 4)
    assert g["s4"].verdict == "reject"


def test_sqm_and_cloud_flag_but_never_reject():
    """003 v2 amendment: a sub well below its session's SQM, or logged as cloudy, is flagged, not rejected."""
    from apps.processing.grading import condition_flags

    subs = [(f"s{i}", 21.1, None) for i in range(6)] + [
        ("dim", 20.6, None),
        ("cloudy", 21.1, 80.0),
        ("bare", None, None),
    ]
    flags = condition_flags(subs)
    assert set(flags) == {"dim", "cloudy"}
    assert "0.50 below session" in flags["dim"] and "flagged, not rejected" in flags["dim"]
    assert "Cloud cover 80%" in flags["cloudy"]
