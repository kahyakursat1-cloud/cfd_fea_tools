"""FEA orkestrasyon iç mantığı — saf-fonksiyon birim testleri.

CalculiX .frd sonuç-çıkarımı (von Mises → emniyet faktörünün kaynağı) ve yardımcı
fonksiyonlar, mevcut .frd fixture ile dondurulur. CalculiX çalıştırmaz; yalnızca
parse mantığını test eder.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPHERE_FRD = ROOT / "test_fea_run" / "sphere_test.frd"


def test_fea_to_wsl_path():
    from fea_runner import _to_wsl_path
    assert _to_wsl_path(Path(r"C:\fea\case")) == "/mnt/c/fea/case"


def test_is_float():
    from fea_runner import _is_float
    assert _is_float("3.14") and _is_float("-1e-5")
    assert not _is_float("abc") and not _is_float("")


@pytest.mark.skipif(not SPHERE_FRD.exists(), reason="sphere_test.frd fixture diskte yok")
def test_parse_frd_golden():
    """CalculiX .frd → von Mises stres çıkarımı (sonuç-extraction kalbi)."""
    from fea_runner import FEASimulationRunner
    r = FEASimulationRunner._parse_frd(SPHERE_FRD)
    assert r["max_von_mises_mpa"] == pytest.approx(0.39733, rel=1e-3)
    assert r["max_von_mises_pa"] > 0
    assert r["max_displacement_m"] >= 0


def test_stress_assessment_singularity():
    """Tekillik-dayanıklı gerilme özeti: sivri-köşe tekilliği tepe-SF'yi yapay
    düşürür; temsili (99%) değer doğru kararı verir."""
    import numpy as np

    from vehicle_fea import _stress_assessment
    # düzgün alan: tepe ≈ temsili → tekillik yok, makul SF
    smooth = np.full(1000, 100e6); smooth[0] = 110e6
    a = _stress_assessment(smooth, 290.0)
    assert a["tekillik_suphesi"] is False
    assert a["emniyet_faktoru"] and 2.0 < a["emniyet_faktoru"] < 3.5
    # tekillik: birkaç düğüm çok yüksek → tepe-SF<1 (yanlış 'güvensiz') ama temsili güvenli
    sing = np.full(1000, 100e6); sing[:3] = [900e6, 700e6, 500e6]
    b = _stress_assessment(sing, 290.0)
    assert b["tekillik_suphesi"] is True
    assert b["tepe_temsili_orani"] > 2.5
    assert b["emniyet_faktoru"] < 1.0            # tepe → yanlış 'yetersiz'
    assert b["emniyet_faktoru_temsili"] > 2.0    # temsili → doğru 'güvenli'
    assert _stress_assessment(None, 290.0) is None


def test_fea_validation_inp_structure():
    """Ankastre kiriş doğrulama .inp'i: düğüm/eleman yapısı (ccx çalıştırmadan,
    saf-mantık). Tam analitik doğrulama: experiments/fea_validation.py."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
    import fea_validation as fv
    out = Path(__file__).resolve().parent.parent / "_fea_val_test.inp"
    fv.write_inp(out)
    txt = out.read_text()
    assert "*ELEMENT, TYPE=C3D8I" in txt
    assert "*BOUNDARY" in txt and "*CLOAD" in txt
    assert (fv.nx + 1) * (fv.ny + 1) * (fv.nz + 1) == 625    # düğüm sayısı
    assert fv.delta_an > 0 and fv.sigma_an > 0               # analitik pozitif
    out.unlink()


def test_fea_validation_hole_analytic():
    """Delikli-plaka Kt analitiği (Heywood). Tam V&V: experiments/fea_validation_hole.py
    (ccx koşar, %1.7). Burada yalnız kapalı-form ilişkiler — gmsh/ccx çalıştırmadan."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
    import fea_validation_hole as fh
    assert pytest.approx(0.2) == fh.DW
    assert pytest.approx(2 + 0.8 ** 3) == fh.KT_NET           # Heywood net-kesit
    assert pytest.approx(fh.KT_NET / (1 - fh.DW)) == fh.KT_GROSS
    assert 3.0 < fh.KT_GROSS < 3.3                            # delik için fiziksel aralık
    assert fh.SIG_MAX_AN > fh.SIG_GROSS                       # konsantrasyon > brüt


def test_fea_validation_cyl_analytic():
    """Basınçlı silindir hoop analitiği (Lamé). Tam V&V: experiments/fea_validation_cyl.py
    (ccx koşar, %7.2 — BASINÇ yolunu doğrular). Burada yalnız kapalı-form."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
    import fea_validation_cyl as fc
    # Lamé iç-yüzey hoop > basınç (ince cidar r/t≈20 → büyük çarpan)
    assert pytest.approx(fc.P * (fc.R_IN ** 2 + fc.R_OUT ** 2)
                                         / (fc.R_OUT ** 2 - fc.R_IN ** 2)) == fc.SIG_THETA
    assert fc.SIG_THETA > 15 * fc.P                           # r/t≈20 → σθ≈20p
    assert fc.SIG_VM_AN > 0 and pytest.approx(-fc.P) == fc.SIG_R


def test_gravity_load_writes_dload_grav(tmp_path):
    """GravityLoad → write_inp '*DLOAD / EALL, GRAV, accel, gx,gy,gz' yazar (g-yükü yolu)."""
    import numpy as np

    from analysis.calculix_writer import (
        FEACase,
        FEAMaterial,
        FixedBC,
        GravityLoad,
        write_inp,
    )
    from analysis.tet_mesher import TetMesh
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.0]])
    mesh = TetMesh(points=pts, tets=np.array([[0, 1, 2, 3]]),
                   surface_tris=np.zeros((0, 3), int), msh_path=tmp_path / "x.msh",
                   element_type="C3D4")
    case = FEACase(name="g", mesh=mesh, material=FEAMaterial("m", 1e9, 0.3, 1000.0),
                   fixed_bcs=[FixedBC(np.array([1]))],
                   gravity_loads=[GravityLoad(3.8 * 9.81, (0, 0, -1.0))],
                   analysis_type="STATIC")
    txt = write_inp(case, tmp_path).read_text(encoding="utf-8")
    assert "*DLOAD" in txt and "EALL, GRAV" in txt
    assert "3.72780" in txt and "0.000000, 0.000000, -1.000000" in txt  # 3.8*9.81


def test_fea_validation_grav_analytic():
    """Öz-ağırlık çubuk analitiği. Tam V&V: experiments/fea_validation_grav.py
    (ccx koşar, σ %4.8 / δ %0.2 — GÖVDE-KUVVETİ yolunu doğrular)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
    import fea_validation_grav as fg
    assert pytest.approx(fg.RHO * fg.G * fg.LZ) == fg.SIG_MAX_AN
    assert pytest.approx(fg.RHO * fg.G * fg.LZ ** 2 / (2 * fg.E)) == fg.DELTA_AN


def test_thermal_card_written(tmp_path):
    """delta_t + α → write_inp '*EXPANSION' ve '*TEMPERATURE' yazar (termal yolu)."""
    import numpy as np

    from analysis.calculix_writer import FEACase, FEAMaterial, FixedBC, write_inp
    from analysis.tet_mesher import TetMesh
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.0]])
    mesh = TetMesh(points=pts, tets=np.array([[0, 1, 2, 3]]),
                   surface_tris=np.zeros((0, 3), int), msh_path=tmp_path / "x.msh",
                   element_type="C3D4")
    mat = FEAMaterial.from_gpa("AL", 70, 0.3, 2700.0, alpha_per_k=23e-6)
    case = FEACase(name="t", mesh=mesh, material=mat,
                   fixed_bcs=[FixedBC(np.array([1]))], analysis_type="STATIC", delta_t=50.0)
    txt = write_inp(case, tmp_path).read_text(encoding="utf-8")
    assert "*EXPANSION" in txt and "2.300000e-05" in txt
    assert "*TEMPERATURE" in txt and "NALL, 5.000000e+01" in txt
    # delta_t=0 → termal kart YOK
    case2 = FEACase(name="t2", mesh=mesh, material=mat,
                    fixed_bcs=[FixedBC(np.array([1]))], analysis_type="STATIC")
    assert "*TEMPERATURE" not in write_inp(case2, tmp_path).read_text(encoding="utf-8")


def test_fea_validation_thermal_analytic():
    """Termal gerilme çubuk analitiği σ=E·α·ΔT. Tam V&V: fea_validation_thermal.py
    (ccx koşar, %0.0 — TERMAL yolunu doğrular)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
    import fea_validation_thermal as ft
    assert pytest.approx(ft.E * ft.ALPHA * ft.DT) == ft.SIG_AN
