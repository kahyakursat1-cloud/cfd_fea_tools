"""Güvenilirlik taraması — "savunulabilir" tanımının kendisini test eder.

Bu taramanın DEĞERİ tanımın katılığına bağlı. Gevşek bir tanım %100 başarı
raporlar ve hiçbir şey öğretmez; bu yüzden tanım yazarın yargısı değil, mevcut
kapıların (sonuc_kapisi + duvar çözünürlüğü) birleşimidir.
"""
import pytest

pytest.importorskip("numpy")
from experiments.guvenilirlik_taramasi import duvar_hukmu, savunulabilir_mi


class _R:
    def __init__(self, **k):
        self.status = "ok"
        self.cd = 0.35
        self.convergence = {"drift_ok": True, "rezidual_ok": True,
                            "salinim": {"osilasyon": False}}
        self.fizik_kabul = {"verdict": "ok"}
        self.mesh = {"cells": 500000}
        self.sinir_tabaka = {"yplus": {"ort": 80.0}, "katman_olcumu": {"durum": "katman_istenmedi"}}
        self.__dict__.update(k)


def test_saglikli_kosu_savunulabilir():
    h = savunulabilir_mi(_R())
    assert h["savunulabilir"] is True and h["gerekce"] == []


def test_MINIHAWK_yplus_5399_REDDEDILIR():
    """Ölçülen gerçek değer. Bant 30-300; 5399 bunun 18 katı."""
    h = savunulabilir_mi(_R(sinir_tabaka={"yplus": {"ort": 5399.0},
                                          "katman_olcumu": {"durum": "katman_istenmedi"}}))
    assert h["savunulabilir"] is False
    assert any("5399" in g for g in h["gerekce"])


def test_KATMAN_COKMESI_reddedilir_yplus_kucuk_olsa_bile():
    """Katman istenip örülmemişse 'duvar-çözünür' iddiası geçersizdir."""
    h = savunulabilir_mi(_R(sinir_tabaka={
        "yplus": {"ort": 2.0},
        "katman_olcumu": {"durum": "COKTU", "istenen": 12, "eklenen": 0}}))
    assert h["savunulabilir"] is False
    assert any("ÇÖKTÜ" in g for g in h["gerekce"])


def test_gercek_duvar_cozunur_kabul():
    ok, _ = duvar_hukmu({"yplus": {"ort": 0.8},
                         "katman_olcumu": {"durum": "ok", "eklenen": 12}})
    assert ok is True


def test_yakinsamayan_kosu_reddedilir():
    h = savunulabilir_mi(_R(convergence={"drift_ok": False, "rezidual_ok": False,
                                         "salinim": {"osilasyon": False}}))
    assert h["savunulabilir"] is False


def test_SALINAN_kosu_reddedilir():
    h = savunulabilir_mi(_R(convergence={"drift_ok": True, "rezidual_ok": True,
                                         "salinim": {"osilasyon": True, "genlik_pct": 4.0,
                                                     "gecis": 6}}))
    assert h["savunulabilir"] is False


def test_fizik_disi_kosu_reddedilir():
    h = savunulabilir_mi(_R(fizik_kabul={"verdict": "inadmissible", "reasons": ["Cd<0"]}))
    assert h["savunulabilir"] is False


def test_yplus_olculemezse_savunulabilir_SAYILMAZ():
    """'Ölçemedim' ile 'iyi' aynı şey değil — bu oturumun temel dersi."""
    h = savunulabilir_mi(_R(sinir_tabaka={"yplus": {"olculemedi": True, "neden": "log yok"},
                                          "katman_olcumu": {"durum": "katman_istenmedi"}}))
    assert h["savunulabilir"] is False


def test_TUM_gerekceler_toplanir_ilkinde_durulmaz():
    h = savunulabilir_mi(_R(
        convergence={"drift_ok": False, "rezidual_ok": False, "salinim": {"osilasyon": True}},
        sinir_tabaka={"yplus": {"ort": 5399.0}, "katman_olcumu": {"durum": "katman_istenmedi"}}))
    assert len(h["gerekce"]) >= 2


def test_kosmayan_geometri_de_ORANA_girer():
    """Çöken koşu yutulursa başarı oranı sistematik olarak şişer."""
    h = savunulabilir_mi(_R(status="FAILED", cd=None))
    assert h["savunulabilir"] is False


def test_fizik_kabul_NITELIK_ADI_dogru():
    """İlk sürüm `r.fizik` okuyordu; gerçek ad `fizik_kabul`. getattr sessizce None
    döndürüyor ve sonuc_kapisi eksik veriyi "ok" sayıyordu — fizik kapısı fark
    edilmeden DEVRE DIŞI kalıyordu. Ad değişirse bu test kırılsın."""
    from dataclasses import fields

    from vehicle_pipeline import VehicleAnalysisResult
    adlar = {f.name for f in fields(VehicleAnalysisResult)}
    assert "fizik_kabul" in adlar, "sonuc nesnesinde fizik_kabul yok — tarama kapisi kor kalir"

    import inspect

    import experiments.guvenilirlik_taramasi as gt
    src = inspect.getsource(gt.savunulabilir_mi)
    assert '"fizik_kabul"' in src
