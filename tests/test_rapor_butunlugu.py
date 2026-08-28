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


# ══════════════════ KAPI GENISLETILDI: iki kusur ELEKTEN GECMISTI ═════════
#
# Ikinci bir dis hakem, kapinin "butun" dedigi PDF'te IKI kusur buldu ve
# ikisi de kapinin OLCUTU IDDIASINDAN DAR oldugu icin gorunmuyordu:
#
#   1. Sayfa 21'de "efsub:fsi-korunumlu" duz metin olarak basiliyordu.
#      Kaynakta "\S\ref{...}" satir sonunda kirilmisti; LaTeX hic \ref
#      gormedigi icin cikti "??" DEGILDI --- kapi yalniz "??" ariyordu.
#   2. Sekil numaralari 1-4 arasinda CIFTLENIYORDU: elle yazilmis TikZ
#      basliklari "Sekil N." (nokta), \caption ailesi "Sekil N:" (iki
#      nokta) biciminde ve AYRI sayaclar yuruTuyordu. Kapi yalniz iki
#      noktali bicimi sayiyor, "11 numara tekil" diyordu.
#
# Asagidaki testler her iki olcutu de HEM yakalayan HEM yakalamamasi
# gereken veriyle sinar.

def test_HAM_LATEX_KALINTISI_YOK(kanit):
    d = kanit["olcum"]
    if d is None:
        pytest.skip(kanit["verdikt"])
    assert d.get("ham_latex_kalintisi") == [], (
        f"ham LaTeX metne sızmış: {d.get('ham_latex_kalintisi')}")


def test_SEKIL_NUMARALARI_TEKIL_VE_ARTAN(kanit):
    d = kanit["olcum"]
    if d is None:
        pytest.skip(kanit["verdikt"])
    assert d["tekrar_eden_sekil"] == {}, d["tekrar_eden_sekil"]
    assert d.get("sekil_monoton") is True, d.get("sekil_sirasi")


# --------------------------------------------------------- olcutun kendisi
# SENTETIK: PDF'ten BAGIMSIZ, atlanamaz.

def _hukum(**olcum):
    import rapor_butunlugu as rb
    tam = {"sayfa_metni_bayt": 1000, "cozulmemis_ham": 0,
           "cozulmemis_bicim": {}, "icindekiler_girdi": 19,
           "sekil_numaralari": 3, "tekrar_eden_sekil": {},
           "sekil_monoton": True, "sekil_sirasi": [1, 2, 3],
           "ham_latex_kalintisi": [], "pdf_bayat": False, "tex_var": True}
    tam.update(olcum)
    return rb._hukum(tam, None)


def test_OLCUT_HAM_KALINTIYI_YAKALIYOR():
    h = _hukum(ham_latex_kalintisi=["efsub:fsi-korunumlu"])
    assert "HAZIR DEĞİL" in h and "efsub:fsi-korunumlu" in h


def test_OLCUT_TEMIZ_METNE_KALINTI_DEMIYOR():
    """Yanlis-pozitif tarafi: kalinti YOKKEN hukum temiz olmali."""
    assert "HAZIR DEĞİL" not in _hukum()


def test_OLCUT_CIFTLENEN_SEKLI_YAKALIYOR():
    h = _hukum(tekrar_eden_sekil={"1": 2}, sekil_monoton=False,
               sekil_sirasi=[1, 2, 1, 2])
    assert "HAZIR DEĞİL" in h and "tekrar eden şekil" in h


def test_OLCUT_ATLAYAN_NUMARAYI_DA_YAKALIYOR():
    """Tekrar olmadan da bozulabilir: 1,2,4 numaralandirma kaymasidir."""
    h = _hukum(sekil_monoton=False, sekil_sirasi=[1, 2, 4])
    assert "HAZIR DEĞİL" in h and "artan değil" in h


def test_CARE_KUSURA_GORE_VERILIYOR():
    """Kapi genisletilince eski tek-cumlelik care YANLIS oldu: ham kalinti
    ve cakisan numaralandirma pdflatex'i tekrar kosmakla GECMEZ. Yanlis
    care kusur kadar zarar verir."""
    h = _hukum(ham_latex_kalintisi=["efsub:x"])
    assert "KAYNAK düzeltmesi" in h
    assert "pdflatex" not in h, "yeniden derlemek bu kusuru cozmez"
    h2 = _hukum(cozulmemis_ham=3, cozulmemis_bicim={"§??": 3})
    assert "pdflatex" in h2 and "KAYNAK düzeltmesi" not in h2


def test_KALINTI_DESENI_DAVRANISLA_SINANIR():
    """Olcut BICIME degil DIZGI GERCEGINE baglanir: susluler dizgide
    yenilir, yani '{' arayan bir desen kusuru HIC bulamazdi --- ilk
    denememde tam bu oldu ve `ef{` aramasi sifir dondurdu. Desen artik
    modul duzeyinde ve DAVRANISLA sinaniyor."""
    from rapor_butunlugu import ham_latex_kalintisi as k

    # (a) gercek sizinti --- PDF'ten birebir alindi
    assert k("degistirildi (§efsub:fsi-korunumlu) ve ayni") == [
        "efsub:fsi-korunumlu"]
    # (b) baska kirilma bicimleri
    assert k("bkz. igfig:polar") == ["igfig:polar"]
    assert k("Tablo abletab:kanit-2") == ["abletab:kanit-2"]
    # (c) YANLIS-POZITIF TARAFI: saglam dizgi kalinti sayilmamali
    for temiz in ("Bolum 4.2'de gosterildigi gibi",
                  "sub:fsi gibi bir etiket adi metinde gecerse",
                  "§4.16 ve §12.1 capraz referanslari",
                  "ref: bu bir iki nokta, makro degil"):
        assert k(temiz) == [], temiz
