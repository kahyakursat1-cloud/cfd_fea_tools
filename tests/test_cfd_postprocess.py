"""CFD orkestrasyon iç mantığı — saf-fonksiyon birim testleri (OpenFOAM gerektirmez).

Kuvvet→Cl/Cd çıkarımı ve wind-axis rotasyonu, sentetik forces.dat ile test edilir.
Bu, regresyon ağının (gerçek solver çıktısı) kapatamadığı boşluğu kapatır:
post-processing matematiği OpenFOAM olmadan dondurulur.
"""
import math
from pathlib import Path

import pytest


# ── _to_wsl_path: Windows → WSL mount yol dönüşümü ───────────────────────────
def test_to_wsl_path():
    from simulation_runner import _to_wsl_path
    out = _to_wsl_path(Path(r"D:\bilsem_beyin\case"))
    assert out == "/mnt/d/bilsem_beyin/case"


def test_wsl_openfoam_sources_bashrc():
    from simulation_runner import _wsl_openfoam
    cmd = _wsl_openfoam("/mnt/d/x", "blockMesh")
    assert "source /opt/openfoam11/etc/bashrc" in cmd
    assert "cd /mnt/d/x" in cmd and "blockMesh" in cmd


# ── parse_forces: forces.dat → Cl/Cd (wind-axis rotasyon) ───────────────────
def _write_forces(case: Path, line: str):
    """OpenFOAM forces function-object çıktısını taklit eden forces.dat üret."""
    d = case / "postProcessing" / "forces" / "0"
    d.mkdir(parents=True)
    (d / "forces.dat").write_text(
        "# Forces\n# time  (pressure) (viscous) (porous)\n" + line + "\n"
    )


def test_parse_forces_alpha0(tmp_path):
    """alpha=0: drag=Fx, lift=Fz (rotasyon kimlik)."""
    import run_aoa_polar as rp
    case = tmp_path / "alpha_00"
    # time=200, pressure F=(100,0,50), viscous F=(10,0,5) → Fx=110, Fz=55
    _write_forces(case, "200  100 0 50  10 0 5  0 0 0")
    r = rp.parse_forces(case, 0)
    q = 0.5 * rp.RHO * rp.V ** 2
    assert r["Cd"] == pytest.approx(110 / (q * rp.S), rel=1e-3)
    assert r["Cl"] == pytest.approx(55 / (q * rp.S), rel=1e-3)


def test_parse_forces_rotation_alpha10(tmp_path):
    """alpha=10: drag/lift wind-axis rotasyonu doğru uygulanmalı."""
    import run_aoa_polar as rp
    case = tmp_path / "alpha_10"
    _write_forces(case, "200  100 0 50  10 0 5  0 0 0")
    Fx, Fz = 110.0, 55.0
    a = math.radians(10)
    exp_drag = Fx * math.cos(a) + Fz * math.sin(a)
    exp_lift = -Fx * math.sin(a) + Fz * math.cos(a)
    q = 0.5 * rp.RHO * rp.V ** 2
    r = rp.parse_forces(case, 10)
    assert r["Cd"] == pytest.approx(exp_drag / (q * rp.S), rel=1e-3)
    assert r["Cl"] == pytest.approx(exp_lift / (q * rp.S), rel=1e-3)


def test_parse_forces_missing_returns_none(tmp_path):
    """forces.dat yoksa None (sessiz crash değil)."""
    import run_aoa_polar as rp
    assert rp.parse_forces(tmp_path / "bos", 0) is None
