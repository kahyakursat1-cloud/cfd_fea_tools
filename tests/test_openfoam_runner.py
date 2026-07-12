"""openfoam_runner orphan-önleme + diverjans bekçisi — saf-mantık (WSL çağırmadan)."""
import trimesh

from analysis.openfoam_runner import (
    _OF_BINS,
    CFDCase,
    _wrap_timeout,
    _wsl_kill,
    build_case,
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


def _box_case(tmp_path, **kw):
    stl = tmp_path / "kutu.stl"
    trimesh.creation.box(extents=(0.2, 0.1, 0.1)).export(stl)
    return CFDCase(name="kutu", stl_path=stl, n_processors=1, **kw)


def test_build_case_free_air_bottom_slip(tmp_path):
    case_dir = build_case(_box_case(tmp_path), tmp_path / "out")
    assert "bottom    { type patch;" in (case_dir / "system" / "blockMeshDict").read_text()
    assert "bottom  { type slip; }" in (case_dir / "0" / "U").read_text()


def test_build_case_ground_plane(tmp_path):
    # Ahmed-tipi zemin: taban wall + noSlip + duvar fonksiyonları; domain tabanı clearance'ta
    case_dir = build_case(_box_case(tmp_path, ground_clearance=0.02), tmp_path / "out")
    bm = (case_dir / "system" / "blockMeshDict").read_text()
    assert "bottom    { type wall;" in bm
    import re
    zs = [float(m.split()[2]) for m in
          re.findall(r"\(\s*([-\d.eE+]+\s+[-\d.eE+]+\s+[-\d.eE+]+)\s*\)", bm)]
    assert abs(min(zs) - (-0.05 - 0.02)) < 1e-6   # gövde zmin=-0.05, clearance 0.02
    assert "bottom  { type noSlip; }" in (case_dir / "0" / "U").read_text()
    assert "kqRWallFunction" in (case_dir / "0" / "k").read_text().split("bottom")[1][:60]
    assert "omegaWallFunction" in (case_dir / "0" / "omega").read_text().split("bottom")[1][:60]
    assert "nutUSpaldingWallFunction" in (case_dir / "0" / "nut").read_text().split("bottom")[1][:60]
    assert "zeroGradient" in (case_dir / "0" / "p").read_text().split("bottom")[1][:60]
