"""run_polar akış testi — CFD/WSL ÇAĞIRMADAN (mock). _C duck-type nesnesinin
_write_control_dict/_write_field_U ile uyumu burada donar: kanonik yazıcılara alan
eklenirse (ör. compressible regresyonu) bu test kırılır, sessiz AttributeError kalmaz."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vehicle_polar as vp  # noqa: E402
from vehicle_pipeline import VehicleAnalysisResult  # noqa: E402

COEFF_HEADER = "# Time Cd Cl Cm\n"


def _write_coeffs(case_dir: Path, cd=0.006, cl=0.002, cm=0.001):
    d = case_dir / "postProcessing" / "forceCoeffs1" / "0"
    d.mkdir(parents=True, exist_ok=True)
    rows = "".join(f"{t} {cd} {cl} {cm}\n" for t in range(1, 121))
    (d / "coefficient.dat").write_text(COEFF_HEADER + rows)


def _base_case(tmp_path: Path) -> Path:
    base = tmp_path / "runs" / "model"
    (base / "system").mkdir(parents=True)
    (base / "system" / "controlDict").write_text("endTime         400;\n")
    (base / "constant" / "triSurface").mkdir(parents=True)
    (base / "constant" / "triSurface" / "model_oriented.stl").write_text("solid x\nendsolid x\n")
    (base / "0").mkdir()
    _write_coeffs(base)
    return base


def _mock_r0(base: Path) -> VehicleAnalysisResult:
    r = VehicleAnalysisResult(
        status="ok", vehicle_type="ucak", stl="model.stl", velocity=25.0, alpha_deg=0.0,
        geometry={"lmax_m": 0.5}, case_dir=str(base))
    r.cd, r.cl, r.aref_m2 = 0.3, 0.1, 0.005
    r.sinir_tabaka = None
    return r


def test_run_polar_reuses_mesh_and_scales(tmp_path, monkeypatch):
    base = _base_case(tmp_path)
    monkeypatch.setattr(vp, "run_vehicle_analysis",
                        lambda *a, **k: _mock_r0(base))

    solved = []

    def fake_solve(case_dir, timeout=7200):
        solved.append(Path(case_dir))
        _write_coeffs(Path(case_dir))
        return subprocess.CompletedProcess(args="foamRun", returncode=0,
                                           stdout="", stderr="")

    monkeypatch.setattr(vp, "_wsl_solve", fake_solve)

    out = vp.run_polar("model.stl", "ucak", 25.0, alphas=(0, 4, 8))
    assert out["status"] == "ok"
    assert len(out["polar"]) == 3
    # scale = lmax² / aref = 0.25 / 0.005 = 50 → Cd_ham 0.006 → 0.3
    assert all(abs(r["Cd"] - 0.3) < 1e-9 for r in out["polar"])
    assert len(solved) == 2                      # mesh yeniden kullanıldı, 2 ek çözüm
    assert Path(out["report"]).exists()

    # ikinci α case'i: U dosyası döndürülmüş akış yönünü taşımalı (α=4°)
    case4 = base.parent / "model_a4"
    u_txt = (case4 / "0" / "U").read_text()
    assert "24.9" in u_txt                        # 25·cos4° ≈ 24.94
    # controlDict _C duck-type ile yazılabildi (compressible alanı regresyonu)
    cd_txt = (case4 / "system" / "controlDict").read_text()
    assert "incompressibleFluid" in cd_txt and "magUInf" in cd_txt


def test_run_polar_marks_failed_point(tmp_path, monkeypatch):
    base = _base_case(tmp_path)
    monkeypatch.setattr(vp, "run_vehicle_analysis",
                        lambda *a, **k: _mock_r0(base))
    monkeypatch.setattr(vp, "_wsl_solve",
                        lambda case_dir, timeout=7200: subprocess.CompletedProcess(
                            args="foamRun", returncode=-1, stdout="", stderr="TIMEOUT"))
    out = vp.run_polar("model.stl", "ucak", 25.0, alphas=(0, 4))
    assert out["status"] == "ok"                 # ilk nokta (mock CFD) sağlam
    assert out["polar"][1]["durum"] == "failed" and out["polar"][1]["Cd"] is None
