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
