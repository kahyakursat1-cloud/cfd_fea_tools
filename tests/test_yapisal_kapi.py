"""Yapısal fizik kapısı — "güvenli" hükmü, hiçbir şey test edilmemişken verilemez.

En tehlikeli FEA başarısızlığı yüksek gerilme değil, yükün HİÇ AKTARILMAMASIDIR:
ccx sıfır dönüş kodu verir, .frd okunur, σ≈0 çıkar, SF astronomik olur ve rapor
"çok güvenli" der. Aero tarafındaki `force_admissibility`'nin yapısal eşi.
"""
import numpy as np
import pytest

from validity_envelope import SF_MAKUL_UST, stress_admissibility


def test_saglikli_sonuc_gecer():
    r = stress_admissibility(max_vm_mpa=180.0, yield_mpa=275.0, sf=1.53, max_disp_mm=12.0)
    assert r["verdict"] == "ok" and r["reasons"] == []


def test_sifir_gerilme_kabul_edilemez():
    r = stress_admissibility(max_vm_mpa=0.0, yield_mpa=275.0)
    assert r["verdict"] == "inadmissible"
    assert "AKTARILMAMIŞ" in r["reasons"][0]


def test_gurultu_mertebesinde_gerilme_yakalanir():
    """σ akmanın binde birinden küçükse yapı pratikte yüklenmemiştir."""
    r = stress_admissibility(max_vm_mpa=0.05, yield_mpa=275.0, sf=5500.0)
    assert r["verdict"] == "inadmissible"
    assert "binde birinden" in r["reasons"][0]


def test_nan_gerilme_kabul_edilemez():
    r = stress_admissibility(max_vm_mpa=float("nan"))
    assert r["verdict"] == "inadmissible" and "ıraksadı" in r["reasons"][0]


def test_sifir_deplasman_kabul_edilemez():
    r = stress_admissibility(max_vm_mpa=100.0, yield_mpa=275.0, max_disp_mm=0.0)
    assert r["verdict"] == "inadmissible"
    assert any("hareket etmemiş" in s for s in r["reasons"])


def test_asiri_sf_supheli():
    r = stress_admissibility(max_vm_mpa=1.0, yield_mpa=275.0, sf=SF_MAKUL_UST + 1)
    assert r["verdict"] in ("suspect", "inadmissible")


def test_tipik_tasarim_sf_supheli_degil():
    for sf in (1.1, 1.5, 2.32, 5.0, 20.0):
        r = stress_admissibility(max_vm_mpa=100.0, yield_mpa=275.0, sf=sf)
        assert r["verdict"] == "ok", f"SF={sf} tipik banttadır"


def test_eksik_veri_hukumsuz():
    assert stress_admissibility()["verdict"] == "ok"


def test_stress_assessment_kapiyi_tasir():
    """`vehicle_fea._stress_assessment` sonucu kapı hükmünü ve gerekçeyi taşımalı."""
    from vehicle_fea import _stress_assessment

    saglikli = _stress_assessment(np.array([1.8e8, 1.5e8, 1.2e8]), 275.0)
    assert saglikli["fizik_kabul"]["verdict"] == "ok"
    assert "⛔" not in saglikli["_gerilme_notu"]

    yuksuz = _stress_assessment(np.array([1.0e3, 5.0e2, 2.0e2]), 275.0)   # ~1e-3 MPa
    assert yuksuz["fizik_kabul"]["verdict"] == "inadmissible"
    assert "⛔" in yuksuz["_gerilme_notu"]
    assert "SF ANLAMSIZ" in yuksuz["_gerilme_notu"], "SF hâlâ geçerliymiş gibi sunulmamalı"


def test_bos_alan_none_doner():
    from vehicle_fea import _stress_assessment
    assert _stress_assessment(np.array([]), 275.0) is None
    assert _stress_assessment(None, 275.0) is None


@pytest.mark.parametrize("vm,beklenen", [(1e9, "ok"), (0.0, "inadmissible")])
def test_uc_degerler(vm, beklenen):
    from vehicle_fea import _stress_assessment
    r = _stress_assessment(np.array([vm, vm * 0.9]), 275.0)
    assert r["fizik_kabul"]["verdict"] == beklenen
