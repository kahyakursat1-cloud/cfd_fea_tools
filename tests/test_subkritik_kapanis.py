"""Subkritik Re'de tam-türbülanslı kapanış — ölçülmüş hata banda GİRMİYORDU.

Model-form tablosu bir künt-cisim koşusuna `bluff`/`separated` diyor ve
%9,31–25 band veriyor. Ama TAM BU konfigürasyonun ölçülen hatası:

    3B URANS (kOmegaSST)     Cd −26,88 %   St +29,74 %
    3B DES   (kOmegaSSTDES)  Cd −39,16 %   St +38,16 %

Band, hatayı 1,6–4 kat EKSİK gösteriyor. Kanıt zaten ölçülmüştü
(silindir_urans_3b.json, silindir_des_3b.json) ama hiçbir tüketiciye
bağlı değildi --- bu deponun baskın kusuru.

SAPMANIN KAYNAĞI ÖLÇÜLDÜ, ÇIKARSANMADI: aynı ağ önce duvar-fonksiyonuyla
(y⁺=0,009, geçersiz) sonra düşük-Re ile (y⁺=0,78, geçerli) koşuldu ve cevap
%1'den az değişti. Sorun çözünürlük ya da duvar işlemi değil, KAPANIŞ.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from validity_envelope import (  # noqa: E402
    SUBKRITIK_OLCUM,
    SUBKRITIK_RE,
    _subkritik_uyari,
    subkritik_kapanis_hukmu,
)


def test_UC_KOSUL_birlikte_gerekli():
    """Künt + subkritik Re + tam-türbülanslı kapanış. Biri eksikse susmalı."""
    assert subkritik_kapanis_hukmu("bluff", 1.4e5, "kOmegaSSTDES")["tetiklendi"]
    # gecis modeli — bagli tabakayi laminer baslatir, kapi TETIKLENMEMELI
    assert not subkritik_kapanis_hukmu("bluff", 1.4e5, "kOmegaSSTLM")["tetiklendi"]
    # superkritik — tabaka kendiliginden turbulanslasir
    assert not subkritik_kapanis_hukmu("bluff", 1e6, "kOmegaSST")["tetiklendi"]
    # tasiyici yuzey — bagli tabaka mantigi ayni degil
    assert not subkritik_kapanis_hukmu("lifting", 1.4e5, "kOmegaSST")["tetiklendi"]


@pytest.mark.parametrize("re", [SUBKRITIK_RE[0], SUBKRITIK_RE[1]])
def test_BAND_UCLARI_dahil(re):
    assert subkritik_kapanis_hukmu("bluff", re, "kOmegaSST")["tetiklendi"]


@pytest.mark.parametrize("re", [SUBKRITIK_RE[0] * 0.9, SUBKRITIK_RE[1] * 1.1])
def test_BAND_DISI_susuyor(re):
    assert not subkritik_kapanis_hukmu("bluff", re, "kOmegaSST")["tetiklendi"]


def test_BILINMEYEN_girdi_SORUN_YOK_sayilmiyor():
    """Yokluğun hükmü yok: Re ya da model bilinmiyorsa 'temiz' denemez."""
    r = subkritik_kapanis_hukmu(None, None, None)
    assert r["tetiklendi"] is False
    assert "DEĞERLENDİRİLMEDİ" in r["neden"]
    r2 = subkritik_kapanis_hukmu("bluff", None, "kOmegaSST")
    assert "DEĞERLENDİRİLMEDİ" in r2["neden"]


def test_HUKUM_OLCULEN_sayilari_tasiyor():
    """Uyarı bir kanıya değil ÖLÇÜME dayanmalı ve sayıyı göstermeli."""
    r = subkritik_kapanis_hukmu("bluff", 1.4e5, "kOmegaSSTDES")
    assert r["olculen_sapmalar"] == SUBKRITIK_OLCUM
    assert "39" in r["hukum"], "en kötü ölçülen sapma hükümde yok"
    assert "kOmegaSSTLM" in r["hukum"], "somut alternatif önerilmiyor"
    assert r["en_kotu_Cd_pct"] < -25


def test_OLCUMLER_KANIT_dosyalariyla_ayni():
    """Sayılar koda GÖMÜLÜ; kanıt yenilenirse ayrışmamalı."""
    import json
    for dosya, anahtar in (("silindir_urans_3b.json", "3B URANS (kOmegaSST)"),
                           ("silindir_des_3b.json", "3B DES (kOmegaSSTDES)")):
        p = KOK / dosya
        if not p.exists():
            pytest.skip(f"{dosya} yok")
        s = json.loads(p.read_text(encoding="utf-8"))["sapma_pct"]
        assert SUBKRITIK_OLCUM[anahtar]["Cd_pct"] == pytest.approx(s["Cd"], abs=0.01)
        assert SUBKRITIK_OLCUM[anahtar]["St_pct"] == pytest.approx(s["St"], abs=0.01)


def test_IKI_KANAL_da_kapiyi_cagiriyor():
    """Kapının bir kanalda görünüp öbüründe susması bu deponun baskın kusuru.

    AST ile aranır: `_subkritik_uyari` dizisi yorumlarda da geçebilir.
    """
    for dosya in ("hizmet.py", "app_analyzer.py"):
        src = (KOK / dosya).read_text(encoding="utf-8")
        cagri = [d for d in ast.walk(ast.parse(src))
                 if isinstance(d, ast.Call)
                 and getattr(d.func, "id", None) == "_subkritik_uyari"]
        assert cagri, f"{dosya} subkritik kapısını ÇAĞIRMIYOR"


def test_YARDIMCI_Re_yi_kosudan_TURETIYOR():
    """Re elle verilmez; geometri ve hızdan türetilir."""
    class R:
        geometry = {"lmax_m": 0.1}
        velocity = 21.0
        vehicle_type = "roket"
        turbulence_model = "kOmegaSST"
    r = _subkritik_uyari(R())
    assert r["tetiklendi"] is True
    assert r["Re"] == pytest.approx(0.1 * 21.0 / 1.5e-5, rel=1e-9)


def test_YARDIMCI_eksik_veride_SUSUYOR():
    class R:
        geometry = {}
        velocity = None
        vehicle_type = None
        turbulence_model = None
    assert _subkritik_uyari(R())["tetiklendi"] is False
