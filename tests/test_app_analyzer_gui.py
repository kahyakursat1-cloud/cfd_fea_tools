"""Ana kullanıcı yüzeyi (`app_analyzer`) — 60 günde 22 değişiklik, 1039 satır, testsizdi.

Mühendis sayıyı burada görür; rozet yanlışsa fizik kapısının hiçbir değeri kalmaz.
Testler gerçek pencereyi offscreen Qt ile kurar ve `_on_done`'u sahte sonuçlarla sürer —
kaynak-metin denetimi değil, gerçek davranış.

CI'da PySide6 yok → importorskip ile atlanır.
"""
import os

import pytest

pytest.importorskip("PySide6", reason="GUI yığını yok (CI)")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def pencere(qapp, monkeypatch):
    import app_analyzer

    kutular = []

    class _SahteKutu:
        @staticmethod
        def warning(parent, baslik, metin):
            kutular.append(("warning", baslik, metin))

        @staticmethod
        def critical(parent, baslik, metin):
            kutular.append(("critical", baslik, metin))

        @staticmethod
        def information(parent, baslik, metin):
            kutular.append(("information", baslik, metin))

    monkeypatch.setattr(app_analyzer, "QMessageBox", _SahteKutu)
    w = app_analyzer.AnalyzerWindow()
    w._kutular = kutular
    return w


class _Sonuc:
    velocity = 30.0
    alpha_deg = 0.0
    cd = 0.032
    cl = 0.44
    ld = 12.2
    drag_N = 0.88
    mesh = {"cells": 250000}
    convergence = {"drift_ok": True, "rezidual_ok": True}
    report = "rapor.md"
    fizik_kabul = {"verdict": "ok", "reasons": []}
    uyarilar = []
    kurulum = []


def _metin(w, anahtar):
    return w.metric_labels[anahtar][1].text()


def test_saglikli_kosu_rozeti(pencere):
    pencere._on_done(_Sonuc())
    assert "yakınsadı" in _metin(pencere, "verdict")
    assert "⛔" not in _metin(pencere, "cd")
    assert pencere._kutular == [], "sağlıklı koşuda uyarı kutusu çıkmamalı"


def test_fizik_disi_kosu_rozeti_ve_engel_kutusu(pencere):
    r = _Sonuc()
    r.cd = -0.0036
    r.fizik_kabul = {"verdict": "inadmissible",
                     "reasons": ["negatif/sıfır sürükleme (Cd=-0.00360)"]}
    pencere._on_done(r)

    assert "fizik-dışı" in _metin(pencere, "verdict"), "rozet yakınsama demeye devam ediyor"
    assert "⛔" in _metin(pencere, "cd"), "Cd çıplak sayı olarak gösterilmemeli"
    assert len(pencere._kutular) == 1 and pencere._kutular[0][0] == "warning"
    assert "KULLANILMAZ" in pencere._kutular[0][2]


def test_yakinsamayan_kosu_sinirda_der(pencere):
    r = _Sonuc()
    r.convergence = {"drift_ok": False, "rezidual_ok": True}
    pencere._on_done(r)
    assert "sınırda" in _metin(pencere, "verdict")
    assert pencere._kutular == [], "yakınsama sorunu engel değil, uyarıdır"


def test_supheli_fizik_engel_kutusu_acmaz(pencere):
    r = _Sonuc()
    r.fizik_kabul = {"verdict": "suspect", "reasons": ["taşıma işareti ters"]}
    pencere._on_done(r)
    assert "şüpheli" in _metin(pencere, "verdict")
    assert pencere._kutular == []


def test_uyarilar_log_panelinde_gorunur(pencere):
    r = _Sonuc()
    r.kurulum = ["ÖLÇEK ŞÜPHESİ: model 1200 m"]
    r.uyarilar = list(r.kurulum) + ["y⁺ ÖLÇÜLEMEDİ"]
    pencere._on_done(r)
    log = pencere.log.toPlainText()
    assert "ÖLÇEK ŞÜPHESİ" in log and "y⁺ ÖLÇÜLEMEDİ" in log


def test_metrikler_dolduruluyor(pencere):
    """Kartlar artık değere EK OLARAK sınıf rozeti taşıyor (✅ tasarım /
    🟡 eğilim), bu yüzden `endswith` yerine `in` sınanır — rozet bilerek
    eklendi ve testin onu yasaklamaması gerekir."""
    pencere._on_done(_Sonuc())
    assert "0.44" in _metin(pencere, "cl")
    assert "12.2" in _metin(pencere, "ld")
    assert "250,000" in _metin(pencere, "cells")


def test_rapor_butonu_rapor_varsa_acilir(pencere):
    r = _Sonuc()
    r.report = ""
    pencere._on_done(r)
    assert not pencere.btn_report.isEnabled()
    r.report = "vehicle_runs/x/rapor.md"
    pencere._on_done(r)
    assert pencere.btn_report.isEnabled()


def test_hata_yolunda_kritik_kutu_ve_buton_geri_gelir(pencere):
    pencere.btn_run.setEnabled(False)
    pencere._on_fail("snappyHexMesh çöktü")
    assert pencere.btn_run.isEnabled(), "başarısızlıkta arayüz kilitli kalmamalı"
    assert pencere._kutular and pencere._kutular[0][0] == "critical"


def test_eksik_alanli_sonuc_cokmez(pencere):
    """Eski/kısmi sonuç nesnesi (fizik_kabul yok) arayüzü düşürmemeli."""
    r = _Sonuc()
    del r.__class__.fizik_kabul
    try:
        pencere._on_done(r)
        assert _metin(pencere, "verdict")
    finally:
        _Sonuc.fizik_kabul = {"verdict": "ok", "reasons": []}


def test_kurulum_uyarisi_ARAYUZDE_de_gorunuyor(pencere):
    """Rapor kurulum uyarılarını en üste koyup 'aşağıdaki tüm bölümleri
    geçersizler' diyor (yanlış ölçek/eksen/A_ref). Arayüz bunları hiç
    okumuyordu: ekranda doğru görünümlü bir Cd duruyor, kullanıcı raporu
    açmadıkça öğrenmiyordu. Ana giriş noktası arayüz olduğu için bu, raporda
    çözülmüş bir tehlikeyi uygulamada açık bırakıyordu."""
    r = _Sonuc()
    r.kurulum = ["ÖLÇEK ŞÜPHESİ: model 1200 m — mm cinsinden ihraç edilmiş olabilir"]
    r.uyarilar = list(r.kurulum)
    pencere._on_done(r)
    kayit = pencere.log.toPlainText()
    assert "ÖLÇEK ŞÜPHESİ" in kayit
    assert kayit.count("ÖLÇEK ŞÜPHESİ") == 1, "uyarı listesinde tekrarlanmamalı"
    assert any("Kurulum uyarısı" in b for _, b, _ in pencere._kutular), \
        "fizik kapısı geçse bile kurulum kusuru kutuyla söylenmeli"


def test_guvence_kaybi_ARAYUZDE_gorunuyor(pencere):
    r = _Sonuc()
    r.gerilemeler = ["iz-momentum çapraz kontrolü yapılamadı (VTK yok)"]
    pencere._on_done(r)
    assert "GÜVENCE KAYBI" in pencere.log.toPlainText()


def test_saglikli_kosuda_kurulum_kutusu_CIKMAZ(pencere):
    pencere._on_done(_Sonuc())
    assert pencere._kutular == []


def test_CD_karti_CIPLAK_sayi_gostermiyor(pencere):
    """Raporun ilkesi: 'Ekranda çıplak sayı yoktur — her metrik ya bandıyla ya
    da bandın niçin hesaplanmadığını söyleyen etiketle gösterilir.' Kartlar bu
    ilkeyi ihlal ediyordu: C_D bandsız duruyordu."""
    r = _Sonuc()
    r.belirsizlik = {"u_toplam_pct": 6.4}
    pencere._on_done(r)
    m = _metin(pencere, "cd")
    assert "±%6.4" in m, m


def test_band_YOKSA_nedeni_yaziliyor(pencere):
    """Band hesaplanmadıysa kart bunu söylemeli — sessizce çıplak sayı değil."""
    r = _Sonuc()
    r.belirsizlik = None
    pencere._on_done(r)
    assert "band YOK" in _metin(pencere, "cd")


def test_QoI_sinif_rozeti_RAPORLA_ayni_kaynaktan(pencere):
    """`classify_cfd` QoI başına hüküm üretiyor ve rapor bunu en üstte
    gösteriyordu; arayüz hiç okumuyordu — aynı kanal-ayrışması sınıfı."""
    r = _Sonuc()
    pencere._on_done(r)
    rozetler = [_metin(pencere, k) for k in ("cd", "cl", "ld")]
    assert any(("tasarım" in x or "eğilim" in x or "zarf-dışı" in x)
               for x in rozetler), rozetler
