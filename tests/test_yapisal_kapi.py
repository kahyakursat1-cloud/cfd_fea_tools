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
    r = stress_admissibility(max_vm_mpa=0.0, yield_mpa=275.0, uygulanan_yuk_n=50.0)
    assert r["verdict"] == "inadmissible"
    assert "AKTARILMAMIŞ" in r["reasons"][0]


def test_yuk_uygulandi_ama_gerilme_sifir():
    """Doğru ölçüt: yük UYGULANMIŞKEN tepki yoksa aktarım kopmuştur."""
    r = stress_admissibility(max_vm_mpa=0.0, yield_mpa=275.0, uygulanan_yuk_n=160.0)
    assert r["verdict"] == "inadmissible"
    assert "160" in r["reasons"][0] and "AKTARILMAMIŞ" in r["reasons"][0]


def test_hafif_yuklu_gercek_vaka_reddedilmez():
    """GERÇEK ÇÖZÜCÜ DERSİ (2026-07-27): 0.4 m plaka, 20 m/s, 160 N aero yükünde
    ccx σ_max=0.122 MPa ölçtü (elle kontrol M·c/I ≈ 0.38 MPa ile aynı mertebe).
    Bu FİZİKSEL OLARAK DOĞRU — yapı sadece fazlasıyla güvenli. Önceki ölçüt
    (σ < akma·1e-3 → 'yük uygulanmadı') hafif yüklü gerçek aero vakalarının
    neredeyse tamamını haksız yere reddederdi."""
    r = stress_admissibility(max_vm_mpa=0.122, yield_mpa=290.0, sf=2373.88,
                             uygulanan_yuk_n=160.0, max_disp_mm=0.03)
    assert r["verdict"] != "inadmissible", "hafif yüklü geçerli sonuç reddedildi"
    assert r["verdict"] == "suspect"
    assert "fazlasıyla güvenli OLABİLİR" in r["reasons"][0], "tek olasılık sunulmamalı"


def test_bos_yuk_alani_statikte_kabul_edilemez():
    """Kullanıcı yüklü analiz istedi ama basınç alanı boş geldi (CFD çözülmemiş /
    yanlış patch / birim hatası) — sıfır gerilme burada 'meşru' değil, hiçbir şey
    sorulmamış demektir."""
    r = stress_admissibility(max_vm_mpa=0.0, uygulanan_yuk_n=0.0)
    assert r["verdict"] == "inadmissible"
    assert "toplam kuvvet SIFIR" in r["reasons"][0]


def test_yuk_bilinmiyorken_sifir_gerilme_muhafazakar_reddedilir():
    """Yük bilgisi yoksa varsayım YÜKLÜ'dür: sıfır gerilme muhafazakâr olarak
    reddedilir (güvenli taraf). Frekans analizi bu fonksiyona hiç uğramaz —
    vehicle_fea'nın frekans kolu ayrı sözlük döndürür."""
    assert stress_admissibility(max_vm_mpa=0.0)["verdict"] == "inadmissible"


def test_nan_gerilme_kabul_edilemez():
    r = stress_admissibility(max_vm_mpa=float("nan"))
    assert r["verdict"] == "inadmissible" and "ıraksadı" in r["reasons"][0]


def test_sifir_deplasman_kabul_edilemez():
    r = stress_admissibility(max_vm_mpa=100.0, yield_mpa=275.0, max_disp_mm=0.0,
                             uygulanan_yuk_n=50.0)
    assert r["verdict"] == "inadmissible"
    assert any("hareket etmemiş" in s for s in r["reasons"])


def test_asiri_sf_supheli_ama_ret_degil():
    r = stress_admissibility(max_vm_mpa=1.0, yield_mpa=275.0, sf=SF_MAKUL_UST + 1)
    assert r["verdict"] == "suspect", "aşırı güvenli yapı ön-tasarımda meşrudur, reddedilmez"


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

    yuksuz = _stress_assessment(np.array([0.0, 0.0, 0.0]), 275.0,
                                uygulanan_yuk_n=160.0)                 # yük var, tepki yok
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
    r = _stress_assessment(np.array([vm, vm * 0.9]), 275.0, uygulanan_yuk_n=100.0)
    assert r["fizik_kabul"]["verdict"] == beklenen
