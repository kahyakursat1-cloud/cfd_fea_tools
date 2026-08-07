"""Arayüz kipleri — aynı yapılandırmanın üç yüzü.

TEMEL DEĞİŞMEZ: kipler farklı yazılım YOLU üretmez. Üçü de aynı `analysis/`
çekirdeğine ve AYNI koşu-yapılandırmasına gider. Bu bozulursa "Otopilot
sonucu" ile "Mühendis sonucu" aynı problem için farklı case kurabilir ve tek
kanonik çekirdek ilkesi çöker --- bu depo o ilkeyi savunuyor.

İKİNCİ DEĞİŞMEZ: gizlemek sıfırlamak değildir. Gizlenen alanın değeri korunur
ve çözücüye aynen gider; kullanıcının göremediği bir ayarın sessizce değişmesi
tam olarak bu deponun avladığı kusur sınıfıdır.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="GUI yığını yok (CI)")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from arayuz_kipleri import (  # noqa: E402
    GORUNURLUK,
    KIP_ACIKLAMA,
    KIP_ETIKET,
    KIPLER,
    gorunur_mu,
    kip_dogrula,
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def pencere(qapp, monkeypatch):
    import app_analyzer

    class _Kutu:
        @staticmethod
        def warning(*a): pass
        @staticmethod
        def critical(*a): pass
        @staticmethod
        def information(*a): pass

    monkeypatch.setattr(app_analyzer, "QMessageBox", _Kutu)
    return app_analyzer.AnalyzerWindow()


def _kip_yap(w, kip: str):
    w.cmb_kip.setCurrentIndex(KIPLER.index(kip))
    w._kip_degisti()


# ── Görünürlük kuralı ───────────────────────────────────────────────────────

def test_bilinmeyen_alan_HER_kipte_gorunur():
    """Varsayılan gizlemek değil GÖSTERMEKTİR: yeni bir ayar eklendiğinde
    haritaya yazılmayı unutursa sessizce kaybolmasın."""
    for k in KIPLER:
        assert gorunur_mu("yepyeni_bir_ayar", k) is True


def test_kip_hiyerarsisi_MONOTON():
    """Araştırmada görünen her şey mühendiste de, mühendiste görünen her şey
    otopilotta... değil — ama tersi TUTMALI: kip yükseldikçe görünürlük
    yalnız ARTAR, hiçbir alan geri kaybolmaz."""
    for alan in GORUNURLUK:
        gor = [gorunur_mu(alan, k) for k in KIPLER]
        assert gor == sorted(gor), f"{alan}: görünürlük kip yükselirken azalıyor"


def test_gecersiz_kip_GUVENLI_varsayilana_duser():
    assert kip_dogrula(None) == "muhendis"
    assert kip_dogrula("saçma") == "muhendis"
    assert kip_dogrula("arastirma") == "arastirma"


def test_her_kipin_etiketi_ve_aciklamasi_var():
    for k in KIPLER:
        assert KIP_ETIKET.get(k) and KIP_ACIKLAMA.get(k)


# ── Arayüzde gerçekten uygulanıyor mu ───────────────────────────────────────

def test_otopilotta_ayrintilar_GIZLI(pencere):
    _kip_yap(pencere, "otopilot")
    for ad in ("spn_yplus", "cmb_quality", "cmb_rejim", "spn_layers"):
        assert getattr(pencere, ad).isHidden(), f"{ad} otopilotta görünüyor"
    assert not pencere.gb_plan.isHidden(), "otopilotta plan kutusu görünmeli"


def test_muhendiste_ayarlar_ACIK_duyarlilik_KAPALI(pencere):
    _kip_yap(pencere, "muhendis")
    for ad in ("spn_yplus", "cmb_quality", "gb_fea"):
        assert not getattr(pencere, ad).isHidden(), f"{ad} mühendiste gizli"
    assert pencere.chk_sens.isHidden(), "mesh-duyarlılık araştırma kipine ait"


def test_arastirmada_VV_katmani_acik(pencere):
    _kip_yap(pencere, "arastirma")
    for ad in ("chk_sens", "spn_seviye", "spn_yplus", "gb_fea"):
        assert not getattr(pencere, ad).isHidden(), f"{ad} araştırmada gizli"


# ── EN KRİTİK: kip yapılandırmayı DEĞİŞTİRMEZ ──────────────────────────────

def _params(w) -> dict:
    """Çözücüye gidecek yapılandırmayı, koşuyu başlatmadan yakala."""
    yakalanan = {}

    class _SahteIsci:
        def __init__(self, params):
            yakalanan.update(params)
        def __getattr__(self, ad):
            class _Sinyal:
                def connect(self, *a, **k): pass
            return _Sinyal()
        def start(self): pass

    import app_analyzer
    eski = app_analyzer.AnalysisWorker
    app_analyzer.AnalysisWorker = _SahteIsci
    try:
        w._run()
    finally:
        app_analyzer.AnalysisWorker = eski
    return yakalanan


def test_KIP_cozucuye_giden_yapilandirmayi_DEGISTIRMIYOR(pencere, tmp_path):
    """Aynı form, üç kip, AYNI params. Bozulursa 'Otopilot sonucu' ile
    'Mühendis sonucu' aynı problem için farklı case kurar."""
    stl = tmp_path / "m.stl"
    stl.write_text("solid x\nendsolid x\n", encoding="utf-8")
    pencere.model_path = stl

    sonuc = {}
    for k in KIPLER:
        _kip_yap(pencere, k)
        sonuc[k] = _params(pencere)
    if not sonuc["muhendis"]:
        pytest.skip("worker yakalanamadı (arayüz akışı değişmiş olabilir)")
    temel = sonuc["muhendis"]
    for k in KIPLER:
        assert sonuc[k] == temel, (
            f"{k} kipi farklı yapılandırma üretti:\n"
            f"  {k}: {sonuc[k]}\n  muhendis: {temel}")


def test_GIZLEMEK_degeri_sifirlamiyor(pencere):
    """Mühendis kipinde bir değer değiştirilip otopilota geçilince değer
    KORUNMALI ve çözücüye aynen gitmeli."""
    _kip_yap(pencere, "muhendis")
    pencere.spn_yplus.setValue(77.0)
    pencere.spn_layers.setValue(5)
    _kip_yap(pencere, "otopilot")
    assert pencere.spn_yplus.value() == 77.0
    assert pencere.spn_layers.value() == 5


def test_otopilot_plani_GIZLENEN_degerleri_yaziyor(pencere):
    """Gizlenen ayar görünmez olabilir ama İZLENEBİLİR kalmalı."""
    _kip_yap(pencere, "muhendis")
    pencere.spn_yplus.setValue(42.0)
    _kip_yap(pencere, "otopilot")
    metin = pencere.lbl_plan.text()
    assert "42" in metin, f"plan kutusu gizlenen y⁺'ı yazmıyor: {metin}"
    assert "Mesh kalitesi" in metin


def test_kanit_gezgini_ARASTIRMA_kipinde(pencere):
    """Yayımlanacak bir sayı üretiliyorsa hangi kanıtın hangi ortamda
    üretildiği görülebilmeli."""
    _kip_yap(pencere, "arastirma")
    assert not pencere.btn_kanit.isHidden()
    _kip_yap(pencere, "otopilot")
    assert pencere.btn_kanit.isHidden()


def test_kanit_gezgini_DAMGASIZI_ayirt_ediyor(pencere, monkeypatch):
    """Damgasız kanıt 'damgalı' gibi görünmemeli; gezgin ikisini ayırmalı ve
    damgasızlığın BİLEREK olduğunu söylemeli."""
    yakalanan = {}

    class _Kutu:
        @staticmethod
        def information(parent, baslik, metin):
            yakalanan["metin"] = metin
        @staticmethod
        def warning(*a): pass
        @staticmethod
        def critical(*a): pass

    import app_analyzer
    monkeypatch.setattr(app_analyzer, "QMessageBox", _Kutu)
    pencere._kanit_gezgini()
    m = yakalanan.get("metin", "")
    assert "damgalı" in m and "damgasız" in m
    assert "BİLEREK" in m
