"""Δ_entegrasyon — hesaplandı, ama bandı değerinin 6 katı.

ÖLÇÜLDÜ: Δ = 0.01504 ± 0.09070 (kanat alanı tabanında). Bandın tamamı RANS'ten
geliyor (GCI %379); birleştirmenin payı 2.7e-05, yani 3360 kat küçük. Sayıyı
bandsız yayınlamak, olmayan bir kesinlik yayınlamak olurdu.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KAYNAK = ROOT / "experiments" / "delta_entegrasyon.py"
KANIT = ROOT / "delta_entegrasyon.json"


def _d():
    return json.loads(KANIT.read_text(encoding="utf-8")) if KANIT.exists() else None


def test_REFERANS_ALANI_ortak_tabana_ceviriliyor():
    """1.72 katlık uyumsuzluk daha önce Δ'nın çıkarılmasını engellemişti;
    çevirmeden çıkarılan fark anlamsızdır."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    ra = d["referans_alani"]
    # olcek 5 haneye yuvarlanarak kaydediliyor; tolerans onu karsilamali.
    assert abs(ra["olcek"] - ra["rans_m2"] / ra["birlestirme_m2"]) < 1e-5
    assert abs(d["rans"]["Cd_kanat_tabani"]
               - d["rans"]["Cd_kendi_tabani"] * ra["olcek"]) < 1e-6


def test_DELTA_girisim_diye_ADLANDIRILMIYOR():
    """RANS geometrisi gövde+kanat ve yatay kuyruk içeriyor, birleştirme yalnız
    kanat. Farkı 'girişim' demek, modellenmemiş iki bileşeni yutmak olurdu."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    assert "GIRISIM DEGIL" in d["_ne_olculuyor"]
    assert "govde parazit" in d["_ne_olculuyor"].lower()


def test_BAND_devralınıyor_yutulmuyor():
    d = _d()
    if not d or "delta" not in d:
        pytest.skip('kanıt/girdi yok: not d or "delta" not in d')
    dd = d["delta"]
    if not dd.get("band_olculdu"):
        return                       # bandsiz durum ayri testte baglaniyor
    # Band RANS'ten gelir; birlestirmenin payi mertebe olarak KUCUK olmali.
    assert dd["band_paylari"]["rans"] > dd["band_paylari"]["birlestirme"]
    # Kareler toplami: bilesenlerden buyuk, toplamlarindan kucuk-esit.
    toplam = sum(dd["band_paylari"].values())
    assert dd["band"] >= max(dd["band_paylari"].values()) - 1e-12
    assert dd["band"] <= toplam + 1e-12


def test_SAVUNULAMAZ_RANS_ile_Delta_YAYINLANMIYOR():
    """RANS'in kendi verdikti mesh-bağımsızlığı reddediyor; Δ o bandı devralır."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    if d["rans"]["gci_fine_pct"] > 15.0 or not (30 <= d["rans"]["yplus_ort"] <= 300):
        assert d["engeller"], "savunulamaz RANS engelsiz gecti"
        assert "KULLANILAMAZ" in d["verdikt"] or "HESAPLANAMADI" in d["verdikt"]


def test_AYNI_DURUM_kapisi_var():
    """Cl uyuşmuyorsa iki sürükleme aynı aerodinamik noktaya ait değildir."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    cl_r, cl_b = d["rans"]["Cl"], (d["birlestirme"] or {}).get("Cl")
    if cl_b is not None and abs(cl_r - cl_b) > 0.05:
        assert any("AYNI DURUMDA DEGILLER" in e for e in d["engeller"])


def test_BAGIMSIZ_kestirim_var():
    """Ölçülen değerin mertebesi bağımsız bir hesapla karşılaştırılmalı."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    ia = d["islak_alan"]
    assert ia["Cd_parazit_kestirimi"] > 0
    assert ia["s_islak_m2"] > 0
    if "delta" in d:
        assert d["delta"]["kestirime_orani"] is not None


def test_GEREKLI_adimlar_YAZILI():
    """Gerekçesiz ret eylem üretmez."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    # ADIMLAR OLCUMDEN URETILIR: sabit anahtar listesi baglamak, duzelen bir
    # adimin metinden dusmesini HATA gibi gosterirdi. Baglanan sey SIRA ve
    # dort adimin da adinin gecmesi.
    g = d["_gerekli"]
    assert g.startswith("SIRA ONEMLI.")
    for adim in ("(0)", "(1)", "(2)", "(3)"):
        assert adim in g, f"{adim} eksik"
    assert "y+" in g and "Cl" in g


def test_URETIM_komutu_KAYITLI():
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    assert "delta_entegrasyon.py" in d["_uretim"]
    assert KAYNAK.exists()
