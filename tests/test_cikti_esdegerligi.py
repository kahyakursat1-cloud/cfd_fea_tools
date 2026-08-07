"""Arayüz ile rapor aynı UYARIYI söylüyor mu?

`test_giris_noktasi_esdegerligi` girdileri karşılaştırır: kullanıcının seçtiği
ayar her yoldan çözücüye aynı gidiyor mu. Bu dosya çıktının aynısını yapar ve
asıl tehlike burada: rapor bir kusuru söyleyip arayüz susarsa, kullanıcı
kusurdan habersiz karar verir --- önerilen giriş noktası arayüzdür ve çoğu koşu
raporu hiç açılmadan okunur.

ÖLÇÜLEN KUSUR: `kurulum` (yanlış birim ölçeği / eksen / A_ref) raporun en
üstünde ve rapor bunun için "aşağıdaki tüm bölümleri geçersizler" diyor.
Arayüz bu alanı hiç okumuyordu.

SİMETRİ TAM DEĞİLDİR ve olmamalıdır: rapor geometri ayrıntısını, A_ref
kipini, VTK yollarını da yazar; arayüz özet gösterir. Bağlanan kural dar:
KARAR-SINIRLAYICI alanlar iki kanalda da görünür.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

# Alan -> neden karar-sınırlayıcı olduğu (gerekçe kodda değil burada tutulur:
# bir alanı bu listeden çıkarmak bilinçli bir karar olsun).
KARAR_SINIRLAYICI = {
    "kurulum": "yanlış ölçek/eksen/A_ref — TÜM sayıları geçersizler",
    "gerilemeler": "bir çapraz-kontrol düştü; koşu sürdü ama güvence azaldı",
    "uyarilar": "mesh kalitesi, itki kırpması, y⁺ — sayıyı sınırlayan koşullar",
    "fizik_kabul": "fizik kapısı; geçmezse katsayılar kullanılmaz",
}


def _okur_mu(kaynak: str, alan: str) -> bool:
    return bool(re.search(rf'\.{alan}\b|["\']{alan}["\']', kaynak))


def test_karar_sinirlayici_alanlar_IKI_kanalda_da_okunuyor():
    gui = (KOK / "app_analyzer.py").read_text(encoding="utf-8")
    rap = (KOK / "vehicle_report.py").read_text(encoding="utf-8")
    eksik = []
    for alan, neden in KARAR_SINIRLAYICI.items():
        for ad, src in (("arayüz", gui), ("rapor", rap)):
            if not _okur_mu(src, alan):
                eksik.append(f"{alan} ({neden}) — {ad} okumuyor")
    assert not eksik, "\n  ".join(["Karar-sınırlayıcı alan tek kanalda:"] + eksik)


def test_kurulum_uyarisi_arayuzde_KUTUYLA_soyleniyor():
    """Günlüğe yazmak yetmez: kurulum kusuru fizik kapısından GEÇER, yani
    ekranda hiçbir engel işareti çıkmaz. Sessiz kalırsa makul görünen bir Cd
    tasarım kararına girer."""
    gui = (KOK / "app_analyzer.py").read_text(encoding="utf-8")
    i = gui.find("def _on_done")
    j = gui.find("def _on_fail", i)
    govde = gui[i:j]
    assert "kurulum" in govde
    assert "QMessageBox.warning" in govde
    assert govde.count("QMessageBox.warning") >= 2, \
        "fizik kapısı kutusu var ama kurulum kutusu yok"
