"""Arayüz uçtan uca: formdaki değer çözücüye AYNEN ulaşıyor mu?

`test_app_analyzer_gui` sonucun nasıl GÖSTERİLDİĞİNİ sınar. Bu dosya bir adım
öncesini sınar: kullanıcının seçtiği ayarın çözücüye ne olarak gittiğini.
Aradaki fark önemli, çünkü yanlış parametreyle koşulan bir analizde bütün
kapılar KUSURSUZ çalışır — yalnızca başka bir problemi korurlar.

ÖLÇÜLEN KUSUR: `ref_bump="oto"` (y⁺'ı banda sokan tek kaldıraç) kuyruk yoluna
eklenmiş, ana "ANALİZ ET" düğmesine eklenmemişti. Düzeltme beş çağıranın
yalnız birine ulaşmıştı ve kullanıcının en çok kullandığı yol varsayılan (0)
ile koşuyordu — MiniHawk'ta y⁺'ı 5399'dan 129'a indiren ayar tam da budur.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="GUI yığını yok (CI)")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def pencere(qapp, monkeypatch):
    """Pencere + çözücüyü hiç başlatmayan sahte işçiler. Yakalanan `params`
    sözlükleri `w._yakalanan` içinde birikir."""
    import app_analyzer
    yakalanan: list[tuple[str, dict]] = []

    def _sahte_isci(ad):
        class _I:
            def __init__(self, params):
                yakalanan.append((ad, dict(params)))
                self.params = params

            def __getattr__(self, _):        # progress/finished_ok/failed sinyalleri
                return type("S", (), {"connect": lambda *a, **k: None})()

            def start(self):
                pass
        return _I

    for ad in ("AnalysisWorker", "PolarWorker", "SupersonicWorker"):
        if hasattr(app_analyzer, ad):
            monkeypatch.setattr(app_analyzer, ad, _sahte_isci(ad))
    monkeypatch.setattr(app_analyzer, "QMessageBox",
                        type("K", (), {"warning": staticmethod(lambda *a: None),
                                       "critical": staticmethod(lambda *a: None),
                                       "information": staticmethod(lambda *a: None)}))
    w = app_analyzer.AnalyzerWindow()
    w._yakalanan = yakalanan
    w.model_path = KOK / "vehicle_runs" / "minihawk" / "minihawk_prep.stl"
    return w


# ── 1. Yapısal çapa: hiçbir yol y⁺ kaldıracını düşüremez ────────────────────

def test_run_vehicle_analysis_e_giden_HER_yol_ref_bump_tasir():
    """Kusur sınıfı: düzeltme çağıranlardan yalnız birine ulaşır. Bu test yeni
    bir çağrı yolu eklendiğinde de aynı kusuru yakalar."""
    src = (KOK / "app_analyzer.py").read_text(encoding="utf-8")
    eksik = []
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for d in ast.walk(fn):
            if not isinstance(d, ast.Dict):
                continue
            anahtar = [k.value for k in d.keys if isinstance(k, ast.Constant)]
            # RANS arac hattina giden sozluklerin imzasi: stl + arac tipi + hiz
            if {"stl_path", "vehicle_type", "velocity"} <= set(anahtar) \
                    and "ref_bump" not in anahtar:
                eksik.append(f"{fn.name}:{d.lineno}")
    assert not eksik, ("y⁺ kaldıracı taşımayan çözücü çağrısı: " + ", ".join(eksik))


def test_polar_hatti_ref_bump_kabul_ediyor():
    """GUI 'oto' geçse bile `run_polar` kabul etmiyorsa TypeError olurdu."""
    import inspect

    from vehicle_polar import run_polar
    assert "ref_bump" in inspect.signature(run_polar).parameters
    kaynak = inspect.getsource(run_polar)
    assert "ref_bump=ref_bump" in kaynak, "parametre alınıp kullanılmıyor"


# ── 2. Davranış: düğmeye basıldığında ne gidiyor ────────────────────────────

def test_analiz_et_dugmesi_oto_kademe_gonderir(pencere):
    pencere._run()
    assert pencere._yakalanan, "çözücü hiç çağrılmadı"
    ad, params = pencere._yakalanan[-1]
    assert ad == "AnalysisWorker"
    assert params["ref_bump"] == "oto"


def test_formdaki_degerler_AYNEN_gidiyor(pencere):
    pencere.spn_v.setValue(23.5)
    pencere.spn_aoa.setValue(6.0)
    pencere.spn_layers.setValue(8)
    pencere.spn_yplus.setValue(1.0)
    pencere.chk_sens.setChecked(True)
    pencere._run()
    _, p = pencere._yakalanan[-1]
    assert p["velocity"] == 23.5
    assert p["alpha_deg"] == 6.0
    assert p["n_layers"] == 8
    assert p["yplus_target"] == 1.0
    assert p["mesh_sensitivity"] is True
    assert p["vehicle_type"] == pencere.cmb_type.currentData()
    assert p["quality"] == pencere.cmb_quality.currentData()


def test_polar_yolu_da_oto_kademe_gonderir(pencere):
    pencere._run_polar()
    ad, p = pencere._yakalanan[-1]
    assert ad == "PolarWorker"
    assert p["ref_bump"] == "oto"
    assert p["alphas"] == sorted(p["alphas"])


def test_ayni_eksen_secilirse_kosu_BASLAMAZ(pencere):
    """Burun ve üst eksen aynıysa oryantasyon anlamsızdır; kapı çözücüden önce."""
    i = pencere.cmb_nose.findText(pencere.cmb_up.currentText())
    if i < 0:
        pytest.skip("eksen listeleri örtüşmüyor")
    pencere.cmb_nose.setCurrentIndex(i)
    pencere._run()
    assert not pencere._yakalanan, "eksen hatasına rağmen çözücü çağrıldı"
    assert pencere.btn_run.isEnabled(), "arayüz kilitli bırakılmamalı"


def test_model_yokken_kosu_baslamaz(pencere):
    pencere.model_path = None
    pencere._run()
    pencere._run_polar()
    assert not pencere._yakalanan


# ── 3. Geometri paneli ölçümü gösteriyor mu ────────────────────────────────

def test_gecerli_stl_olculen_geometriyi_panele_yazar(pencere):
    stl = KOK / "vehicle_runs" / "minihawk" / "minihawk_prep.stl"
    if not stl.exists():
        pytest.skip("örnek STL yok")
    pencere._load_model(stl)
    metin = pencere.geo_label.text()
    assert "0.704" in metin and "1.5" in metin, metin      # ölçülen kutu boyutu
    assert "üçgen" in metin
    assert pencere.model_path == stl


# ── 4. Koşu geçmişi: karşılaştırma hükmü ekrana ULAŞIYOR mu ────────────────

def _sahte_kayit(ad, cd, u_pct):
    return {"ad": ad, "tip": "ucak", "kalite": "standart", "hiz": 15.0,
            "alpha": 0.0, "cd": cd, "u_pct": u_pct, "cl": 0.1,
            "cells": 400000, "status": "ok", "rapor": ""}


@pytest.fixture
def gecmis(qapp, monkeypatch):
    import app_analyzer

    def _kur(kayitlar):
        monkeypatch.setattr(app_analyzer.KosularDialog.__init__.__globals__["kosu_gecmisi"]
                            if "kosu_gecmisi" in app_analyzer.KosularDialog.__init__.__globals__
                            else __import__("kosu_gecmisi"), "tara", lambda: kayitlar)
        d = app_analyzer.KosularDialog(None)
        d.kayitlar = kayitlar
        return d
    return _kur


def _sec(d, satirlar):
    d.tbl.clearSelection()
    for r in satirlar:
        d.tbl.selectRow(r)
        d.tbl.setSelectionMode(d.tbl.SelectionMode.MultiSelection)


def test_bandi_olan_iki_kosu_hukum_aliyor(gecmis):
    d = gecmis([_sahte_kayit("A", 0.030, 5.0), _sahte_kayit("B", 0.031, 5.0)])
    _sec(d, [0, 1])
    d._karsilastir()
    m = d.det.toPlainText()
    assert "Ayırt-edilebilirlik" in m
    assert "İÇİNDE" in m, "%3.3'lük fark %7.1'lik bandın içindedir"


def test_bandsiz_kosuda_HUKUM_VERILEMEZ_yaziyor(gecmis):
    """En tehlikeli hâl: band yokken satırın hiç yazılmaması. Kullanıcı iki
    çıplak sayıyı görüp farkı gerçek sanar."""
    d = gecmis([_sahte_kayit("A", 0.030, None), _sahte_kayit("B", 0.050, 5.0)])
    _sec(d, [0, 1])
    d._karsilastir()
    m = d.det.toPlainText()
    assert "HÜKÜM VERİLEMEZ" in m
    assert "A" in m


def test_iki_satir_secilmezse_ne_yapacagi_soyleniyor(gecmis):
    d = gecmis([_sahte_kayit("A", 0.03, 5.0), _sahte_kayit("B", 0.031, 5.0)])
    d.tbl.clearSelection()
    d._karsilastir()
    assert "İKİ satır" in d.det.toPlainText()


def test_aile_uyusmazligi_ekranda_gorunur(gecmis):
    a = _sahte_kayit("A", 0.030, 5.0)
    b = _sahte_kayit("B", 0.031, 5.0)
    b["kalite"] = "hassas"
    d = gecmis([a, b])
    _sec(d, [0, 1])
    d._karsilastir()
    assert "mesh kalitesi farklı" in d.det.toPlainText()


# ── 5. Kuyruk diyaloğu: kilit durumu ve kurtarma arayüzden erişilebilir mi ──

@pytest.fixture
def kuyruk_dlg(qapp, tmp_path, monkeypatch):
    import app_analyzer
    import kuyruk
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "kuyruk.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "kuyruk.lock")
    kutular = []
    monkeypatch.setattr(app_analyzer, "QMessageBox", type("K", (), {
        "warning": staticmethod(lambda *a: kutular.append(("warning",) + a[1:])),
        "critical": staticmethod(lambda *a: kutular.append(("critical",) + a[1:])),
        "information": staticmethod(lambda *a: kutular.append(("information",) + a[1:])),
    }))
    d = app_analyzer.KuyrukDialog(None)
    d._kutular = kutular
    d._kuyruk = kuyruk
    return d


def test_bayat_kilit_ARAYUZDE_gorunur(kuyruk_dlg):
    """Bayat kilit sessiz kalırsa kullanıcı 'worker koşuyor' sanıp bekler."""
    kuyruk_dlg._kuyruk.KILIT.write_text("999999", encoding="utf-8")
    kuyruk_dlg._yenile()
    assert "BAYAT KİLİT" in kuyruk_dlg.lbl_kilit.text()


def test_canli_worker_arayuzde_kosuyor_der(kuyruk_dlg):
    kuyruk_dlg._kuyruk.KILIT.write_text(str(os.getpid()), encoding="utf-8")
    kuyruk_dlg._yenile()
    assert "koşuyor" in kuyruk_dlg.lbl_kilit.text()


def test_yarim_is_sayisi_arayuzde_duyuruluyor(kuyruk_dlg):
    k = kuyruk_dlg._kuyruk
    i = k.ekle({"stl_path": "a.stl", "vehicle_type": "ucak", "velocity": 15.0})
    k._guncelle(i["id"], durum="yarim")
    kuyruk_dlg._yenile()
    assert "YARIM" in kuyruk_dlg.lbl_kilit.text()


def test_devam_dugmesi_yarim_isi_geri_alir(kuyruk_dlg):
    k = kuyruk_dlg._kuyruk
    i = k.ekle({"stl_path": "a.stl", "vehicle_type": "ucak", "velocity": 15.0})
    k._guncelle(i["id"], durum="yarim")
    kuyruk_dlg._devam()
    assert k.listele()[0]["durum"] == "bekliyor"


def test_iptal_dugmesi_kosan_isi_reddeder(kuyruk_dlg):
    k = kuyruk_dlg._kuyruk
    i = k.ekle({"stl_path": "a.stl", "vehicle_type": "ucak", "velocity": 15.0})
    k._guncelle(i["id"], durum="kosuyor")
    kuyruk_dlg._yenile()
    kuyruk_dlg.tbl.selectRow(0)
    kuyruk_dlg._iptal()
    assert k.listele()[0]["durum"] == "kosuyor"
    assert any(x[0] == "warning" for x in kuyruk_dlg._kutular)
