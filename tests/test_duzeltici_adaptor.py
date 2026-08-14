"""Adaptör — düzelticiyi gerçek araç çözücüsüne bağlayan tek çözücü-bilen katman.

Çözücü ÇAĞRILMAZ: testler `run_vehicle_analysis`'i sahte bir işlevle
değiştirir. Sınanan şey çeviri katmanıdır — sonucun kanıta doğru çevrilip
çevrilmediği ve düzelticinin ürettiği kurulum değişikliğinin doğru çözücü
argümanına gidip gitmediği.
"""
import sys
import types

import duzeltici as D
import duzeltici_adaptor as A


class _Sonuc:
    """VehicleAnalysisResult'ın adaptörün okuduğu alanları."""

    def __init__(self, cd=0.30, cl=0.1, yplus=None, p=None, uyarilar=None,
                 katman=0, case_dir=""):
        self.cd, self.cl = cd, cl
        self.case_dir = case_dir
        self.uyarilar = uyarilar or []
        self.sinir_tabaka = {"katman_sayisi": katman, "yplus": yplus or {}}
        self.mesh_duyarlilik = {"gci": {"p": p}} if p is not None else {}


def test_kanit_kur_ALANLARI_dogru_cevirir():
    r = _Sonuc(cd=0.42, cl=1.2, yplus={"ort": 0.009}, p=0.2,
               uyarilar=["çözüm sigFpe ile durdu"])
    k = A.kanit_kur(r)
    assert k["olculen"]["Cd"] == 0.42
    assert k["olculen"]["yplus"]["ort"] == 0.009
    assert k["olculen"]["gozlenen_mertebe"] == 0.2
    assert k["olculen"]["sigFpe"] is True


def test_duvar_islemi_VAKADAN_okunur_ayardan_DEGIL(tmp_path):
    """Niyet ile gerçeklik ayrışabilir: n_layers>0 duvarın çözüldüğünü kanıtlamaz."""
    (tmp_path / "0").mkdir()
    (tmp_path / "0" / "nut").write_text(
        "boundaryField { airfoil { type nutLowReWallFunction; } }", encoding="utf-8")
    assert A._duvar_islemi_oku(tmp_path) == "nutLowReWallFunction"
    assert A._duvar_islemi_oku(None) == ""
    assert A._duvar_islemi_oku(tmp_path / "yok") == ""


def _sahte_hat(monkeypatch, sonuclar):
    """`vehicle_pipeline.run_vehicle_analysis`'i sıradan sahte sonuçlarla değiştir."""
    gelen = iter(sonuclar)
    cagrilar = []

    def sahte(stl, **kw):
        cagrilar.append(kw)
        return next(gelen)

    mod = types.ModuleType("vehicle_pipeline")
    mod.run_vehicle_analysis = sahte
    monkeypatch.setitem(sys.modules, "vehicle_pipeline", mod)
    return cagrilar


def test_dusuk_Re_duzeltmesi_AG_ARGUMANLARINA_cevrilir(monkeypatch):
    """`nut_wall` doğrudan bir çözücü argümanı değil; araç hattında AĞ üzerinden
    uygulanır. Çeviri yapılmazsa düzeltme sessizce etkisiz kalırdı."""
    ilk = _Sonuc(cd=0.40, yplus={"ort": 0.009})       # duvar fonksiyonu + ince ağ
    ikinci = _Sonuc(cd=0.31, yplus={"ort": 0.8})
    cagrilar = _sahte_hat(monkeypatch, [ilk, ikinci])
    monkeypatch.setattr(A, "_duvar_islemi_oku", lambda c: "nutkWallFunction")

    r, s = A.duzelterek_analiz("x.stl", referans=0.30, n_layers=0)
    assert len(cagrilar) == 2                     # ilk koşu + düzeltilmiş koşu
    assert cagrilar[1]["n_layers"] >= 10          # katman istendi
    assert cagrilar[1]["yplus_target"] == 1.0     # düşük-Re hedefi
    assert s.mudahaleler[0].duzeltme == "duvar_islemini_aga_uydur"


def test_ON_KOSULSUZ_duzeltme_cozucuyu_HIC_cagirmaz(monkeypatch):
    """sigFpe var ama kaba çözüm yok: yeniden koşu YAPILMAMALI, gerekçe yazılmalı."""
    cagrilar = _sahte_hat(monkeypatch, [_Sonuc(uyarilar=["sigFpe"])])
    r, s = A.duzelterek_analiz("x.stl", referans=0.30)
    assert len(cagrilar) == 1                     # yalnız ilk koşu
    assert s.mudahaleler == []
    assert [ad for ad, _ in s.engellenenler] == ["rampali_baslangic"]


def test_fiziksel_olmayan_sonuc_YENIDEN_KOSMADAN_dusurulur(monkeypatch):
    """Cd<0 bir kurulum kusuru değil, ıraksama; yeniden koşmak para yakmaktır."""
    cagrilar = _sahte_hat(monkeypatch, [_Sonuc(cd=-0.019)])
    r, s = A.duzelterek_analiz("x.stl", referans=0.30)
    assert len(cagrilar) == 1
    assert s.sinif == D.OUT


def test_REFERANSSIZ_kosuda_duzeltme_BASARILI_sayilmaz(monkeypatch):
    """Referans yoksa iyileşme ölçülemez; düzeltici bunu 'işe yaradı' DEMEZ."""
    _sahte_hat(monkeypatch, [_Sonuc(cd=0.40, yplus={"ort": 0.009}),
                             _Sonuc(cd=0.31, yplus={"ort": 0.8})])
    monkeypatch.setattr(A, "_duvar_islemi_oku", lambda c: "nutkWallFunction")
    r, s = A.duzelterek_analiz("x.stl")            # referans YOK
    assert s.mudahaleler[0].ise_yaradi is None
    assert "ölçülemedi" in s.mudahaleler[0].ozet()
