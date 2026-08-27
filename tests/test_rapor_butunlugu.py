"""Rapor PDF dizgi bütünlüğü --- dış hakemin P0 saydığı kusurun kapısı.

Hakem 61 sayfalık PDF'de 32 adet ``§??'' saydı, boş içindekiler ve çift
``Şekil 1'' bildirdi. Sebep yazımda değil ÜRETİM ADIMINDAYDI: pdflatex bir
kez koşulmuştu, oysa çapraz referanslar ikinci geçişte çözülür ve dosyanın
kendi başlığı ``(iki kez)'' diyordu. Üç geçişten sonra sayım sıfıra indi.

Kusurun sınıfı bu depoda tanıdık: bir üretim adımı vardı, onu denetleyen
yoktu. Testler hem GERÇEK çıktıyı hem ÖLÇÜTÜN KENDİSİNİ sınar --- ikincisi
olmadan yeşil bir test yalnız ``bu kez sorun yoktu'' demiş olurdu.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "rapor_butunlugu.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("rapor_butunlugu.json yok "
                    "(python experiments/rapor_butunlugu.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_COZULMEMIS_REFERANS_YOK(kanit):
    """Asıl iddia. Raporun ana savı izlenebilirlik; ``bkz. §??'' o zinciri
    okurun gözünde koparır."""
    d = kanit["olcum"]
    if d is None:
        pytest.skip(kanit["verdikt"])
    assert d["cozulmemis_ham"] == 0, (
        f"{d['cozulmemis_ham']} çözülmemiş referans: "
        f"{d['cozulmemis_bicim']} --- pdflatex'i 2-3 kez koş")


def test_ICINDEKILER_DOLU(kanit):
    """Başlık var ama liste yok hâli --- tek geçişli derlemenin imzası."""
    d = kanit["olcum"]
    if d is None:
        pytest.skip(kanit["verdikt"])
    assert d["icindekiler_girdi"] >= 5, (
        f"içindekiler yalnız {d['icindekiler_girdi']} girdi gösteriyor")


def test_SEKIL_NUMARALARI_TEKIL(kanit):
    d = kanit["olcum"]
    if d is None:
        pytest.skip(kanit["verdikt"])
    assert not d["tekrar_eden_sekil"], (
        f"aynı numarayı taşıyan şekiller: {d['tekrar_eden_sekil']}")


def test_PDF_KAYNAGINDAN_YENI(kanit):
    """Bayat bir PDF bütün görünür ve YAYIMLANAN başka bir belgedir. Bu
    ders bu depoda bugün ayrıca FSI döngüsünde de ödendi."""
    d = kanit["olcum"]
    if d is None:
        pytest.skip(kanit["verdikt"])
    assert d["tex_var"], "kaynak .tex bulunamadı; bayatlık ölçülemez"
    assert d["pdf_bayat"] is False, (
        "PDF kaynağından eski --- denetlenen şey yayımlanan şey değil")


def test_OLCUT_BOZUK_BELGEYI_GERCEKTEN_YAKALIYOR():
    """YANLIŞ-NEGATİF KAPISI. Yeşil bir test, ölçütün çalıştığını değil
    yalnız bu kez sorun olmadığını gösterir. Hüküm fonksiyonu sentetik
    bozuk ölçümlerle ayrı ayrı sınanır."""
    from rapor_butunlugu import _hukum
    temiz = {"cozulmemis_ham": 0, "cozulmemis_bicim": {},
             "icindekiler_girdi": 19, "sekil_numaralari": 11,
             "tekrar_eden_sekil": {}, "pdf_bayat": False, "tex_var": True}
    assert "Bütün:" in _hukum(temiz, None)
    for bozuk, imza in (
        ({**temiz, "cozulmemis_ham": 32}, "çözülmemiş referans"),
        ({**temiz, "icindekiler_girdi": 0}, "içindekiler"),
        ({**temiz, "tekrar_eden_sekil": {"1": 2}}, "tekrar eden şekil"),
        ({**temiz, "pdf_bayat": True}, "ESKİ"),
    ):
        h = _hukum(bozuk, None)
        assert "YAYINA HAZIR DEĞİL" in h, f"{imza} yakalanmadı: {h}"
        assert imza in h


def test_OLCULEMEDI_ile_GECTI_AYRI(kanit):
    """pdftotext yoksa kapı sessizce geçmemeli. 'Ölçemedim' ile 'sorun
    yok' aynı görünürse kapı âtıl olur ve kimse fark etmez."""
    from rapor_butunlugu import _hukum
    assert "ÖLÇÜLEMEDİ" in _hukum(None, "pdftotext yok")
    assert "Bütün" not in _hukum(None, "pdftotext yok")


def test_KISIT_ICERIGI_DENETLEMEDIGINI_soyluyor(kanit):
    k = kanit["_kisit"]
    assert "DIZGI" in k
    assert "ICERIK dogrulugunu denetlemez" in k
    assert "SESSIZCE gecmez" in k
