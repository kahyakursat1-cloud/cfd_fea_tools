"""URANS eskalasyonu — "kesin çözüm URANS'tır" cümlesi UYGULANABİLİR mi?

Hüküm salınan koşuyu doğru tespit ediyor ve doğru olanı söylüyordu: akış
zaman-bağımlıdır. Ama orada duruyordu. Kullanıcının elinde ne zaman adımı
vardı, ne kaç adım koşacağı, ne de maliyeti. Aynı kusur `propeller_params`'ta
da yaşandı: "sınırı aştın" demek yetmiyordu, o hız ve çapta ne kadar mümkün
olduğu da yazılmalıydı.

Bu testler REÇETENİN KURALINI bağlar, sayısını değil: Strouhal öncülü
değişirse sayılar değişir ama zaman adımı hâlâ periyodun yüzde biri olmalı ve
öncül olduğu HÂLÂ yazmalı.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from urans_kapisi import (  # noqa: E402
    ADIM_PER_PERIYOT,
    GECIS_PERIYODU,
    ISTATISTIK_PERIYODU,
    recete_metni,
    urans_recetesi,
)

SALINIYOR = {"osilasyon": True, "genlik_pct": 4.2, "gecis": 11}


def test_salinim_yoksa_recete_YOK():
    r = urans_recetesi({"osilasyon": False}, 0.5, 20.0, "bluff")
    assert r["gerekli"] is False
    assert recete_metni(r) == []


def test_zaman_adimi_PERIYODUN_yuzde_biri():
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert r["zaman_adimi_s"] == pytest.approx(r["periyot_s"] / ADIM_PER_PERIYOT,
                                               rel=1e-2)


def test_frekans_STROUHAL_tanimindan():
    """f = St·U/L. Hız iki katına çıkarsa frekans da iki katına çıkar,
    zaman adımı yarıya iner."""
    yavas = urans_recetesi(SALINIYOR, 0.5, 10.0, "bluff")
    hizli = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert hizli["frekans_hz"] == pytest.approx(2 * yavas["frekans_hz"], rel=1e-6)
    assert hizli["zaman_adimi_s"] < yavas["zaman_adimi_s"]


def test_buyuk_cisim_DAHA_UZUN_periyot():
    kucuk = urans_recetesi(SALINIYOR, 0.2, 20.0, "bluff")
    buyuk = urans_recetesi(SALINIYOR, 2.0, 20.0, "bluff")
    assert buyuk["periyot_s"] > kucuk["periyot_s"]


def test_adim_sayisi_GECIS_ARTI_ISTATISTIK():
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert r["adim_sayisi"] == (GECIS_PERIYODU + ISTATISTIK_PERIYODU) * ADIM_PER_PERIYOT


def test_ONCUL_oldugu_her_ciktida_yaziyor():
    """En tehlikeli hâl: türetilmiş sayıların ölçüm sanılması. Kararlı
    çözücüde iterasyon zaman değildir; frekans literatür öncülünden gelir."""
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    metin = " ".join(recete_metni(r))
    assert "ÖNCÜL" in metin.upper()
    assert "Courant" in metin, "Δt yalnız periyottan geliyor; Co kısıtı söylenmeli"


def test_maliyet_OLCULEN_iterasyon_maliyetinden():
    """Tahmin uydurma bir katsayıdan değil, aynı ağda aynı makinede ölçülen
    iterasyon maliyetinden gelmeli."""
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff",
                       rans_sure_s=1200.0, rans_iterasyon=600)
    assert r["tahmini_sure_s"] > 0
    iki_kat = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff",
                             rans_sure_s=2400.0, rans_iterasyon=600)
    assert iki_kat["tahmini_sure_s"] == pytest.approx(2 * r["tahmini_sure_s"], rel=1e-6)


def test_maliyet_bilinmiyorsa_SURE_UYDURULMUYOR():
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert "tahmini_sure_s" not in r
    assert "tahmini" not in recete_metni(r)[0]


def test_uzunluk_yoksa_HESAPLANAMADI_deniyor():
    """Sessizce atlamak yerine niçin hesaplanamadığı söylenmeli."""
    r = urans_recetesi(SALINIYOR, None, 20.0, "bluff")
    assert r["gerekli"] is True and r["hesaplanabilir"] is False
    assert "hesaplanamaz" in r["gerekce"]
    assert recete_metni(r) == [r["gerekce"]]


# ── Hükme gerçekten bağlı mı ────────────────────────────────────────────────

def _kapi(kosu):
    from validity_envelope import sonuc_kapisi
    conv = {"drift_ok": True, "rezidual_ok": False, "cd_drift_son20pct": 1.2,
            "salinim": SALINIYOR}
    return sonuc_kapisi({"verdict": "ok"}, conv, None, kosu=kosu)


def test_salinan_kosunun_HUKMUNDE_recete_var():
    k = _kapi({"lref_m": 0.5, "velocity": 20.0, "rejim": "bluff",
               "sure_s": 1800.0, "iterasyon": 600})
    assert k["seviye"] == "uyari"
    assert any("URANS reçetesi" in g for g in k["gerekce"])


def test_kosu_baglami_verilmezse_hukum_COKMEZ():
    """Eski çağıranlar `kosu` geçmiyor; reçete olmaz ama hüküm çalışmalı."""
    k = _kapi(None)
    assert k["seviye"] == "uyari"
    assert any("SALINIYOR" in g for g in k["gerekce"])


def test_KABUL_edilen_salinimli_kosuya_recete_EKLENMIYOR():
    """Genliği bantta olan salınım kabul ediliyor; orada reçete gereksiz
    gürültüdür — kullanıcı zaten devam ediyor."""
    from validity_envelope import sonuc_kapisi
    conv = {"drift_ok": True, "rezidual_ok": True, "cd_drift_son20pct": 0.4,
            "salinim": {"osilasyon": True, "genlik_pct": 1.0, "gecis": 6}}
    k = sonuc_kapisi({"verdict": "ok"}, conv,
                     {"u_sayisal_pct": 2.0, "u_model_pct": 12.0},
                     kosu={"lref_m": 0.5, "velocity": 20.0, "rejim": "bluff"})
    assert k["seviye"] == "ok"
    assert not any("URANS reçetesi" in g for g in k["gerekce"])
