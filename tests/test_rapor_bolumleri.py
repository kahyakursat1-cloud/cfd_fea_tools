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


# ── Roket: stabilite ve flutter hükümleri VERİDEN ─────────────────────────

def _roket(stab_min=1.8, stab_max=2.4):
    return {"status": "SUCCESS", "apogee_m": 1240.0, "time_to_apogee_s": 16.2,
            "max_velocity_ms": 210.0, "max_mach": 0.62, "max_accel_g": 12.4,
            "burnout_time_s": 2.1, "burnout_altitude_m": 210.0,
            "liftoff_mass_kg": 6.4,
            "stability_min_cal": stab_min, "stability_max_cal": stab_max,
            "cd_vs_mach": [{"Mach": 0.3, "Cd": 0.48}, {"Mach": 0.6, "Cd": 0.51}]}


def test_roket_stabilite_hukmu_VERIYLE_degisiyor(kur):
    """Stabilite marjı <1 cal ise roket KARARSIZDIR; metin bunu söylemeli."""
    stabil = kur(rocket=_roket(stab_min=1.8))
    kararsiz = kur(rocket=_roket(stab_min=0.6))
    assert "stabil" in stabil and "kararsız" not in stabil
    assert "kararsız" in kararsiz


def test_roket_basarisiz_kosu_bolum_ACMAZ(kur):
    """status != SUCCESS ise sayı yayımlanmamalı."""
    r = _roket()
    r["status"] = "FAILED"
    md = kur(rocket=r)
    assert "Roket Uçuş Analizi" not in md


def test_fin_flutter_marji_hukmu_VERIYLE_degisiyor(kur):
    guvenli = kur(rocket=_roket(), rocket_fin={
        "flutter": {"flutter_velocity_ms": 320.0, "flutter_mach": 0.94},
        "flutter_margin": 1.52, "v_flight_ms": 210.0, "flutter_safe": True,
        "static_fea": {"status": "SUCCESS", "tip_deflection_mm": 1.2,
                       "max_von_mises_MPa": 84.0, "safety_factor": 2.6,
                       "is_safe": True}})
    kritik = kur(rocket=_roket(), rocket_fin={
        "flutter": {"flutter_velocity_ms": 190.0, "flutter_mach": 0.55},
        "flutter_margin": 0.90, "v_flight_ms": 210.0, "flutter_safe": False,
        "static_fea": {"status": "SUCCESS", "tip_deflection_mm": 6.4,
                       "max_von_mises_MPa": 260.0, "safety_factor": 0.8,
                       "is_safe": False}})
    assert "KRİTİK" in kritik
    assert "KRİTİK" not in guvenli


# ── FEA gerilme mesh-yakınsaması ──────────────────────────────────────────

def test_stress_gci_Heywood_sapmasini_yaziyor(kur):
    md = kur(fea_stress_gci={
        "vaka": "Delikli plaka", "yontem": "C3D10, 3 seviye",
        "analitik_Kt_MPa": 300.0, "tepe_yayilim_pct": 0.8,
        "seviyeler": [{"h_mm": 2.0, "dugum": 12000, "sigma_tepe_MPa": 288.0,
                       "tepe_temsili": 1.02},
                      {"h_mm": 1.0, "dugum": 48000, "sigma_tepe_MPa": 295.0,
                       "tepe_temsili": 1.01},
                      {"h_mm": 0.5, "dugum": 190000, "sigma_tepe_MPa": 298.0,
                       "tepe_temsili": 1.00}],
        "gci": {"p": 1.9, "f_exact": 300.5, "gci_fine_pct": 0.9},
        "fiziksel_sonuc": "Tepe gerilme YAKINSADI",
        "strict_gci_verdict": "✅ GECTI"})
    assert "Heywood" in md
    assert "0.9" in md


# ── Çözücü validasyonu ────────────────────────────────────────────────────

def test_validasyon_hata_esigi_HUKMU_belirliyor(kur):
    iyi = kur(validation={"cfd_a0": {"alpha": 0, "Cd_ref": 0.0081, "Cd_sim": 0.0083,
                                     "Cd_err_pct": 2.5, "Cl_ref": 0.0,
                                     "Cl_sim": 0.001, "Cl_err_pct": 0.1}})
    kotu = kur(validation={"cfd_a0": {"alpha": 0, "Cd_ref": 0.0081, "Cd_sim": 0.0140,
                                      "Cd_err_pct": 72.8, "Cl_ref": 0.0,
                                      "Cl_sim": 0.001, "Cl_err_pct": 0.1}})
    assert "❌" in kotu, "eşik aşıldı ama başarısız işareti yok"
    assert iyi != kotu


# ── Geçiş modeli poları ───────────────────────────────────────────────────

def test_gecis_polari_basarisiz_alfayi_ISARETLIYOR(kur):
    md = kur(transition={
        "model": "kOmegaSSTLM", "mesh": "C-grid 512×192",
        "0": {"Cl": 0.001, "Cl_ref": 0.0, "Cd": 0.0083, "Cd_ref": 0.0081},
        "4": {"Cl": 0.44, "Cl_ref": 0.452, "Cd": 0.0094, "Cd_ref": 0.0092},
        "8": {"Cl": None, "status": "DIVERGED"}})
    assert "DIVERGED" in md
    assert "Geçiş-Modeli Polar" in md


# ── Mesh kalitesi, FEA, kuplaj, polar ─────────────────────────────────────

def test_mesh_kalitesi_olculen_yplusu_yaziyor(kur):
    md = kur(mesh_quality={"cells": 453_975, "non_ortho_max": 62.4,
                           "non_ortho_avg": 4.1, "layers_avg": 3.2,
                           "yplus_min": 12.0, "yplus_avg": 129.0,
                           "yplus_max": 410.0, "coverage_pct": 88.0})
    assert "129" in md
    assert "453,975" in md or "453975" in md


def test_FEA_emniyet_hukmu_VERIYLE_degisiyor(kur):
    guvenli = kur(fea={"material": "AL6061", "shell_thickness_mm": 2.0,
                       "span_m": 1.5, "root_chord_m": 0.25, "g_factor": 3.8,
                       "max_von_mises_MPa": 90.0, "tip_deflection_mm": 3.1,
                       "safety_factor": 3.2, "is_safe": True})
    riskli = kur(fea={"material": "AL6061", "shell_thickness_mm": 0.5,
                      "span_m": 1.5, "root_chord_m": 0.25, "g_factor": 3.8,
                      "max_von_mises_MPa": 380.0, "tip_deflection_mm": 41.0,
                      "safety_factor": 0.7, "is_safe": False})
    assert guvenli != riskli, "emniyet durumu değişti, metin değişmedi"


def test_kuplaj_korunum_hatasi_raporlaniyor(kur):
    """FSI'da yükün korunumu makine hassasiyetinde olmalı; sayı görünmeli."""
    md = kur(coupling={"n_cfd_faces": 24_477, "n_loaded_nodes": 8_112,
                       "p_min_Pa": -420.0, "p_max_Pa": 310.0,
                       "lift_Fz_N": 12.4, "drag_Fx_N": 2.05,
                       "conservation_error": 1.2e-13})
    assert "24,477" in md or "24477" in md
    assert "e-13" in md or "1.2" in md


def test_polar_tablosu_LD_tepesini_iceriyor(kur):
    md = kur(polar=[{"alpha": -4, "Cl": -0.18, "Cd": 0.021, "LD": -8.6},
                    {"alpha": 0, "Cl": 0.09, "Cd": 0.019, "LD": 4.8},
                    {"alpha": 4, "Cl": 0.36, "Cd": 0.023, "LD": 15.6},
                    {"alpha": 8, "Cl": 0.61, "Cd": 0.034, "LD": 17.9}])
    assert "17.9" in md
    for a in ("-4", "0", "4", "8"):
        assert a in md
