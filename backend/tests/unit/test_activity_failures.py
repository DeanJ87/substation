"""005 T012: failed jobs show Siril's own output and a plain-English cause."""

from apps.engine.siril import EngineDied, EngineError
from substation.tasks.activity import _error_line
from substation.tasks.worker import engine_excerpt


def _text(exc: BaseException) -> str:
    import traceback

    return "".join(traceback.format_exception(exc)) + engine_excerpt(exc)


def test_engine_output_is_kept_with_the_failure():
    try:
        try:
            raise EngineError("stack r_pp_light", ["log: Stacking...", "log: Not enough memory to stack"])
        except EngineError as e:
            raise RuntimeError("Stack failed") from e
    except RuntimeError as exc:
        msg, log = _error_line(_text(exc))
    assert msg == "Stack failed"
    assert (
        "Siril output:" in log
        and "$ stack r_pp_light" in log
        and log[-1] == "log: Not enough memory to stack"
    )


def test_common_causes_are_named_in_plain_english():
    try:
        raise EngineDied("register", [], "Siril stopped (exit -9)")
    except EngineDied as exc:
        msg, _ = _error_line(_text(exc))
    assert msg and msg.startswith("Siril crashed")
    msg, log = _error_line("OSError: [Errno 30] Read-only file system: '/data/x'")
    assert msg and msg.startswith("Output folder is read-only") and "Siril output:" not in log


def test_guiding_rms_is_read_from_the_file_name():
    """Owner 2026-10-10: the rig will carry guiding RMS in the file name."""
    from apps.processing.api import rms_from_name

    assert rms_from_name("M31_300s_RMS0.62_20251021.fits") == 0.62
    assert rms_from_name("2026-10-03_Halpha_600.00s_RMS-0.48_0020.xisf") == 0.48
    assert rms_from_name("Light_guiding_0.8_0001.fit") == 0.8
    assert rms_from_name("Light_TotalRMS_1.1.fit") == 1.1
    assert rms_from_name("M_31_300s_20251021200405.fits") is None
    assert rms_from_name("NGC7000_Hα_FARMS_600s.fits") is None
