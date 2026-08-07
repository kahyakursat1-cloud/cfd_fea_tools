"""Araç hattındaki SAF karar fonksiyonları — çözücü gerektirmeyenler.

`vehicle_pipeline` %52 kapsamda ve büyük kısmı çözücü orkestrasyonu (WSL
gerektirir). Ama içinde çözücüye HİÇ dokunmayan karar fonksiyonları var ve
bunlar bu oturumda sertleştirilen kapıların GİRDİSİ: y⁺ hedefinden ilk hücre
yüksekliği, pervane itki kapağı, eksen oryantasyonu. Yanlış girdiyle kapılar
kusursuz çalışır ve yanlış problemi korurlar.

`propeller_params` özellikle önemli: Froude sınırını aşan itkiyi SESSİZCE
kırpıyor (τ ≤ 0.24). Kırpma gerçekleşirse kullanıcı istediği itkiyi analiz
ettiğini sanır; uyarı metni tek koruma ve o metin test edilmemişti.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from vehicle_pipeline import (  # noqa: E402
    first_layer_height,
    orientation_matrix,
    propeller_params,
)

# ── Pervane: Froude sınırı ve KIRPMA ──────────────────────────────────────

def test_sinirin_altinda_itki_KIRPILMAZ():
    p = propeller_params(thrust_n=5.0, cap_m=0.30, velocity=20.0)
    assert p["uyari"] is None
    assert p["itki_N"] == 5.0
    assert 0 < p["tau"] < 0.24


def test_sinir_asilinca_UYARI_ve_kirpma():
    """Kırpma sessiz olamaz: kullanıcı istediği itkiyi analiz ettiğini sanır."""
    p = propeller_params(thrust_n=5000.0, cap_m=0.10, velocity=5.0)
    assert p["uyari"], "Froude sınırı aşıldı ama uyarı yok"
    assert "sınıra kapatıldı" in p["uyari"]
    assert p["tau"] == 0.24
    # ISTENEN korunur, UYGULANAN ayri alanda: rapor hangisini yazacagini bilsin
    assert p["itki_N"] == 5000.0
    assert p["kirpildi"] is True
    assert p["uygulanan_itki_N"] < 5000.0


def test_kirpilmayan_kosuda_uygulanan_ISTENENE_esit():
    p = propeller_params(5.0, cap_m=0.30, velocity=20.0)
    assert p["kirpildi"] is False
    assert p["uygulanan_itki_N"] == pytest.approx(5.0, rel=1e-6)


def test_uygulanan_itki_COZUCUYE_giden_tau_ile_tutarli():
    """Cp kırpılmış τ'dan türüyor; uygulanan itki de aynı τ'dan gelmeli.
    İkisi ayrışırsa rapor çözücünün gördüğünden farklı bir sayı yazar."""
    p = propeller_params(5000.0, cap_m=0.10, velocity=5.0)
    q_disk = 2 * 1.225 * p["area"] * 5.0 ** 2
    assert p["uygulanan_itki_N"] == pytest.approx(p["tau"] * q_disk, rel=1e-3)


def test_uyari_UYGULANABILIR_max_itkiyi_soyluyor():
    """'Aştın' demek yetmez; bu hız/çapta ne kadar mümkün olduğu yazılmalı."""
    p = propeller_params(thrust_n=5000.0, cap_m=0.10, velocity=5.0)
    import re
    m = re.search(r"max ~([\d.]+) N", p["uyari"])
    assert m, p["uyari"]
    mumkun = float(m.group(1))
    assert 0 < mumkun < 5000.0
    # Soylenen max GERCEKTEN kirpilmadan geciyor mu?
    q = propeller_params(mumkun * 0.98, cap_m=0.10, velocity=5.0)
    assert q["uyari"] is None


def test_induksiyon_faktoru_fiziksel_bantta():
    """a = (1-√(1-4τ))/2; τ≤0.24 iken a gerçel ve 0<a<0.5 olmalı."""
    for t, d, v in ((1.0, 0.3, 20.0), (50.0, 0.4, 15.0), (5000.0, 0.1, 5.0)):
        p = propeller_params(t, d, v)
        assert 0.0 < p["a"] < 0.5, p
        assert math.isfinite(p["Cp"])


def test_buyuk_cap_ayni_itkiyi_KIRPMADAN_gecirir():
    """Kırpma çapa bağlı: alan büyüdükçe aynı itki sınırın altına iner."""
    kucuk = propeller_params(200.0, cap_m=0.15, velocity=20.0)
    buyuk = propeller_params(200.0, cap_m=2.00, velocity=20.0)
    assert kucuk["uyari"] and not buyuk["uyari"]


# ── İlk katman yüksekliği: y⁺ hedefinin karşılığı ─────────────────────────

def test_hedef_yplus_ile_ORANTILI():
    a = first_layer_height(20.0, 1.0, 30.0)
    b = first_layer_height(20.0, 1.0, 60.0)
    assert b == pytest.approx(2 * a, rel=1e-9)


def test_hiz_arttikca_ilk_hucre_INCELIR():
    """Daha hızlı akış daha ince ilk hücre ister — ters çıkarsa y⁺ hedefi
    hiçbir zaman tutmaz."""
    yavas = first_layer_height(10.0, 1.0, 30.0)
    hizli = first_layer_height(40.0, 1.0, 30.0)
    assert hizli < yavas


def test_referans_uzunluk_arttikca_ilk_hucre_BUYUR():
    kisa = first_layer_height(20.0, 0.2, 30.0)
    uzun = first_layer_height(20.0, 5.0, 30.0)
    assert uzun > kisa


def test_cok_dusuk_hizda_Re_tabani_patlamayi_onluyor():
    """Re→0'da korelasyon patlar; taban (1e3) sonlu değer garanti eder."""
    h = first_layer_height(0.01, 0.01, 30.0)
    assert math.isfinite(h) and h > 0


def test_duvar_cozunur_hedef_cok_daha_ince_hucre_ister():
    fonksiyon = first_layer_height(20.0, 1.0, 30.0)
    cozunur = first_layer_height(20.0, 1.0, 1.0)
    assert cozunur < fonksiyon / 20


# ── Eksen oryantasyonu: geometri kapısının koruduğu şey ───────────────────

def test_varsayilan_eksen_birim_matris():
    import numpy as np
    M = orientation_matrix("+x", "+z")
    assert np.allclose(M, np.eye(3))


@pytest.mark.parametrize("burun,ust", [("+z", "+x"), ("-x", "+z"), ("+y", "+z")])
def test_donusum_ORTOGONAL_ve_yansitmasiz(burun, ust):
    """Dönme matrisi olmalı: det=+1. det=-1 yansıtma demektir ve geometriyi
    aynalar — Cl işareti sessizce ters döner."""
    import numpy as np
    M = orientation_matrix(burun, ust)
    assert np.allclose(M @ M.T, np.eye(3), atol=1e-9)
    assert np.isclose(np.linalg.det(M), 1.0, atol=1e-9), "yansıtma (det=-1)"


def test_burun_ekseni_akis_yonune_TASINIYOR():
    """+z burunlu model döndürüldüğünde burun +x'e gelmeli."""
    import numpy as np
    M = orientation_matrix("+z", "+x")
    assert np.allclose(M @ np.array([0.0, 0.0, 1.0]), [1.0, 0.0, 0.0], atol=1e-9)
