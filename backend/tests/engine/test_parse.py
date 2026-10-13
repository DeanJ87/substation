def test_regional_quality_and_tilt_note():
    """004 FR-007: FWHM by zone, and a tilt note when one corner is much softer than its opposite."""
    from apps.engine.parse import Star, regional

    stars = []
    for i in range(10):
        for x, y, f in ((500, 500, 2.0), (50, 950, 3.2), (950, 950, 2.1), (50, 50, 2.1), (950, 50, 2.0)):
            stars.append(Star(x=x + i, y=y + i % 3, fwhm_x=f, fwhm_y=f * 0.95, amplitude=100))
    r = regional(stars, 1000, 1000)
    assert r["zones"]["centre"]["stars"] == 10
    # the soft stars are at y=950 of 1000: y runs from the top, so that's the bottom left
    assert r["zones"]["bottom_left"]["fwhm_px"] > 3
    assert "bottom left corner" in r["tilt_note"] and "top right" in r["tilt_note"]
    assert regional(stars[:3], 1000, 1000)["tilt_note"] == ""
