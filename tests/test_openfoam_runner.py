"""openfoam_runner orphan-önleme + diverjans bekçisi — saf-mantık (WSL çağırmadan)."""
from analysis.openfoam_runner import (
    _OF_BINS,
    _wrap_timeout,
    _wsl_kill,
    divergence_in_log,
)


def test_divergence_detector_catches_nan():
    assert divergence_in_log("Solving for Ux, Initial residual = nan, Final") is not None
    assert divergence_in_log("Initial residual = inf") is not None
    assert "exception" in (divergence_in_log("forrtl: Floating point exception") or "")
    assert divergence_in_log("#0  Foam::error::printStack") is not None


def test_divergence_detector_ignores_normal_log():
    # 'bounding' normal mesajdir; saglikli yakinsama diverjans DEGIL → yanlis-pozitif yok
    ok = ("bounding k, min: 0 max: 12 average: 3\n"
          "Solving for Ux, Initial residual = 0.0012, Final residual = 1e-7\n"
          "Solving for omega, Initial residual = 3.4e-05\n")
    assert divergence_in_log(ok) is None


def test_wrap_timeout_wraps_solver():
    # foamRun → WSL-içi GNU timeout ile sarılır (orphan-önleme), binary listelenir
    wrapped, bins = _wrap_timeout("mpirun -np 4 foamRun -parallel", 600)
    assert wrapped.startswith("timeout -k 10 -s TERM 580 ")
    assert "foamRun" in bins and "mpirun" in bins


def test_wrap_timeout_skips_short_cmds():
    # kısa yardımcı (OF binary değil) sarılmaz (komut log-redirect içermez; _step sonra ekler)
    wrapped, bins = _wrap_timeout("checkMesh -allTopology", 120)
    assert wrapped == "checkMesh -allTopology" and bins == []


def test_wrap_timeout_floor():
    # çok küçük tmo'da iç süre tabanı 30 s
    wrapped, _ = _wrap_timeout("blockMesh", 25)
    assert "timeout -k 10 -s TERM 30 " in wrapped


def test_wsl_kill_safe_on_empty():
    # boş liste no-op; istisna fırlatmaz
    assert _wsl_kill([]) is None
    assert "mpirun" in _OF_BINS and "foamRun" in _OF_BINS
