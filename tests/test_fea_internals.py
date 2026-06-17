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
