"""Raporun HER BÖLÜMÜ kendi verisiyle tutarlı mı?

`VVReport.build` 491 satır ve 209'u test edilmemişti — yani raporun çoğu
bölümü hiç sürülmemişti. Bu depoda bulunan dört rapor kusurunun hepsi aynı
sınıftandı: **metin sabit, veri değişti**. Örnekler (hepsi gerçek):

  - VLM kısıt cümlesi "kamburluk uygulanmaz" diyordu; kamburluk açıldı, cümle
    aynı kaldı
  - TMR bölümü GCI kötü olsa da aynı metni basıyordu
  - FEA suite işareti kanıt METNİNDEN okunuyordu ("GECTI" in sonuc)
  - kademe üçlüsü yanlış seçiliyordu (en kaba + ikinci-en-ince)

Bu yüzden testler sabit çıktı beklemez; verinin bir özelliğini DEĞİŞTİRİP
metnin onunla birlikte değiştiğini bağlar. Sabit metin bu testlerde kırılır.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from report_generator import VVReport  # noqa: E402


@pytest.fixture
def kur(tmp_path):
    def _kur(**kw):
        r = VVReport(out_dir=str(tmp_path))
        r.build(**kw)
        return (r.out / "VV_report.md").read_text(encoding="utf-8")
    return _kur


def _seviye(ad, cells, cd, cl=0.0, durum="ok"):
    return {"name": ad, "grid": f"{cells}", "cells": cells, "Cd": cd, "Cl": cl,
            "drift": 1e-6, "status": durum}


# ── 2B airfoil GCI: fizik kapısı her KADEMEYE ayrı uygulanır ───────────────

def test_airfoil_fizik_disi_kademe_ISARETLENIR(kur):
    md = kur(airfoil_gci={
        "alpha": 0, "model": "kOmegaSST", "reference": {},
        "levels": [_seviye("kaba", 10_000, -0.004),      # NEGATIF sürükleme
                   _seviye("orta", 40_000, 0.0085),
                   _seviye("ince", 160_000, 0.0082)]})
    assert "fizik-dışı" in md
    assert "kaba" in md


def test_airfoil_saglikli_kademeler_kabul_ediliyor(kur):
    md = kur(airfoil_gci={
        "alpha": 0, "model": "kOmegaSST", "reference": {},
        "levels": [_seviye("kaba", 10_000, 0.0090),
                   _seviye("orta", 40_000, 0.0085),
                   _seviye("ince", 160_000, 0.0082)]})
    assert "fizik-dışı" not in md
    assert "kabul" in md


# ── VSPAERO: kısıt metni VERİDEN türetilir ─────────────────────────────────

def test_kamburluk_cumlesi_VERIYLE_degisiyor(kur):
    """Ölçülen kusur: metin "kamburluk uygulanmaz" diye SABİTTİ; kamburluk
    açılınca rapor kendi verisiyle çelişti."""
    kambursuz = kur(vspaero=[{"alpha": 0.0, "Cl": 0.0, "Cd_i": 0.0},
                             {"alpha": 4.0, "Cl": 0.30, "Cd_i": 0.004}])
    kamburlu = kur(vspaero=[{"alpha": 0.0, "Cl": 0.21, "Cd_i": 0.002},
                            {"alpha": 4.0, "Cl": 0.52, "Cd_i": 0.009}])
    assert "kamburluk uygulanmaz" in kambursuz
    assert "kamburluk UYGULANIYOR" in kamburlu
    assert kambursuz != kamburlu


def test_VLM_induklenen_direnc_ALINMAZ_uyarisi_hep_var(kur):
    """VSPAERO'nun iki CDi çıktısı da kuramdan sapıyor; tablo CDi için
    kullanılmamalı ve bu her durumda yazılmalı."""
    for cl0 in (0.0, 0.21):
        md = kur(vspaero=[{"alpha": 0.0, "Cl": cl0, "Cd_i": 0.001}])
        assert "İndüklenen direnç bu tablodan alınmaz" in md


# ── TMR: hüküm kanıt METNİNDEN değil, ÖLÇÜMDEN ────────────────────────────

def _tmr(gci_pct, p=2.0, monoton=True):
    return {"TMR_referans_SST_alpha0": 0.00809,
            "seviyeler": [{"grid": "a", "cells": 1e4, "Cd": 0.0090},
                          {"grid": "b", "cells": 4e4, "Cd": 0.0084},
                          {"grid": "c", "cells": 16e4, "Cd": 0.0081}],
            "gci": {"gci_fine_pct": gci_pct, "p": p, "p_in_range": 0.5 <= p <= 3.0,
                    "monotonic": monoton, "f_exact": 0.00809, "asymptotic": 1.0},
            "strict_gci_verdict": "✅ GECTI"}


def test_TMR_bolumu_KOTU_GCI_ile_iyi_GCI_ayni_metni_basmaz(kur):
    """Ölçülen kusur: bölüm GCI kötü olsa da 'VALIDATED' basıyordu."""
    iyi = kur(tmr_gci=_tmr(1.7))
    kotu = kur(tmr_gci=_tmr(48.0, p=0.2, monoton=False))
    assert iyi != kotu, "GCI değişti, rapor metni değişmedi"


def test_TMR_bolumu_olculen_GCIyi_yaziyor(kur):
    md = kur(tmr_gci=_tmr(1.7))
    assert "1.7" in md or "1,7" in md


# ── FEA doğrulama tablosu ─────────────────────────────────────────────────

def test_fea_dogrulama_vakalari_tabloda(kur):
    md = kur(fea_validations=[
        {"vaka": "Ankastre kiriş",
         "sehim": {"fem": 1.02, "analitik": 1.00, "hata_pct": 2.0,
                   "formul": "Euler–Bernoulli"}},
        {"vaka": "İç-basınçlı silindir",
         "analitik": {"formul": "Lamé"},
         "sehim": {"fem": 0.51, "analitik": 0.50, "hata_pct": 1.3}}])
    assert "Ankastre kiriş" in md and "Lamé" in md


# ── V-n zarfı ─────────────────────────────────────────────────────────────

def test_vn_zarfi_EKSIK_parcada_raporu_dusurmuyor(kur):
    """Ölçülen kırılganlık: `envelope["gust"]["lines"]` sert erişimdi; kanıt
    dosyası o alanı taşımıyorsa KeyError TÜM rapor üretimini çökertiyordu."""
    md = kur(envelope={
        "category": "Normal", "n_max": 3.8, "n_min": -1.5,
        "wing_loading_Pa": 120.0, "limit_load_N": 456.0, "ultimate_load_N": 684.0,
        "speeds_ms": {"Vs1": 12.0, "Va": 23.4, "Vc": 30.0, "Vd": 42.0},
        "critical_cases": [{"name": "n_max @ Va", "n": 3.8, "V": 23.4,
                            "limit_load_N": 456.0, "ultimate_load_N": 684.0,
                            "is_design_critical": True}]})
    assert "n_max @ Va" in md, "eksik parça yüzünden bölüm hiç yazılmamış"


def test_vn_zarfi_kritik_vakalari_yaziyor(kur):
    md = kur(envelope={
        "gust": {"lines": {"Vc": {"V": 30.0, "n_up": 2.4, "n_down": -0.4}}},
        "category": "Normal", "n_max": 3.8, "n_min": -1.5,
        "wing_loading_Pa": 120.0, "limit_load_N": 456.0, "ultimate_load_N": 684.0,
        "speeds_ms": {"Vs1": 12.0, "Va": 23.4, "Vc": 30.0, "Vd": 42.0,
                      "upper_curve": [[0, 0], [23.4, 3.8], [42.0, 3.8]],
                      "lower_curve": [[0, 0], [23.4, -1.5], [42.0, 0.0]]},
        "critical_cases": [{"name": "n_max @ Va", "n": 3.8, "V": 23.4,
                            "limit_load_N": 456.0, "ultimate_load_N": 684.0,
                            "is_design_critical": True}]})
    assert "n_max @ Va" in md
    assert "3.8" in md


# ── Bölümler birbirini bozmuyor ───────────────────────────────────────────

def test_bos_kanit_bolumu_HIC_yazmaz_uydurmaz(kur):
    """Kanıt yoksa bölüm çıkmamalı — boş tablo basmak 'ölçüldü' izlenimi verir."""
    md = kur()
    for baslik in ("2D Airfoil GCI", "VSPAERO", "V-n"):
        assert baslik not in md


def test_tum_bolumler_birlikte_uretilebiliyor(kur):
    """Bölümler tek tek sınandı; birlikte de çalışmalı (ortak durum bozulmasın)."""
    md = kur(
        airfoil_gci={"alpha": 0, "model": "SST", "reference": {},
                     "levels": [_seviye("k", 1e4, 0.009), _seviye("o", 4e4, 0.0085),
                                _seviye("i", 16e4, 0.0082)]},
        tmr_gci=_tmr(1.7),
        vspaero=[{"alpha": 0.0, "Cl": 0.0, "Cd_i": 0.0}],
        fea_validations=[{"vaka": "Kiriş", "formul": "E–B",
                          "sehim": {"fem": 1.0, "analitik": 1.0, "hata_pct": 0.4}}],
    )
    for baslik in ("2D Airfoil GCI", "VSPAERO"):
        assert baslik in md
    assert md.count("# CFD/FEA Doğrulama") == 1
