"""Raporun KAPSAM cümlesi, çözücünün GERÇEK yeteneğiyle senkron mu?

BU KAPI BİR DIŞ HAKEM BULGUSUNDAN DOĞDU ve kusur tam olarak şuydu: rapor
bir yerde ``geometrik doğrusalsızlık (NLGEOM) doğrulanmamıştır ve üretim
yolunda yoktur; analiz tipleri STATIC, FREQUENCY ve BUCKLE ile
sınırlıdır'' derken, aynı raporun ilerisi NLGEOM'un eklendiğini,
doğrulandığını ve `*DYNAMIC`'in koşulduğunu anlatıyordu. Doğrudan iç
çelişki --- ve teknik içerikten çok daha düşük bir olgunluk izlenimi
bırakıyor.

SINIF TANIDIK: yetenek eklendi, onu ANLATAN cümle güncellenmedi. Bu depo
aynı kusuru daha önce üç yerde ödedi (kalan-engel gerekçesi, doğrulama
durumu, iki-hızlı katman notu) ve her seferinde çözüm aynı oldu: cümleyi
sabit yazma, KAYNAKTAN türet ya da kaynağa karşı DENETLE.

Burada denetim yolu seçildi --- proza serbest kalsın ama iddiası
yazıcının gerçek yeteneğiyle çelişmesin.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

TEX = KOK / "docs" / "teknik_rapor.tex"


@pytest.fixture(scope="module")
def yetenek():
    from fsi_capa_ulasilabilirlik import _yapisal_yetenek
    y = _yapisal_yetenek()
    if not y.get("okunabildi"):
        pytest.skip(f"yazıcı okunamadı: {y.get('neden')}")
    return y


@pytest.fixture(scope="module")
def kapsam() -> str:
    """``Kapsam dışı kalanlar'' kutusunun METNİ --- rapor bütünü değil.

    Bütün rapor içinde arasaydık test hiçbir şey ayırt etmezdi: NLGEOM
    zaten ileride onlarca kez geçiyor. Sınanan şey KAPSAM BEYANIDIR.
    """
    if not TEX.exists():
        pytest.skip("rapor yok")
    t = TEX.read_text(encoding="utf-8")
    i = t.find("Kapsam dışı kalanlar")
    if i < 0:
        pytest.skip("kapsam kutusu bulunamadı")
    son = t.find(r"\end{dikkat}", i)
    return t[i:son if son > 0 else i + 3000]


def test_YAZICININ_DESTEKLEDIGI_HER_TIP_KAPSAMDA_ANILIYOR(yetenek, kapsam):
    """Yazıcı bir analiz tipini destekliyorsa kapsam beyanı onu ya
    'doğrulandı' ya da açıkça 'doğrulanmadı' diye ANMALIDIR. Hiç anmamak,
    okurun eski listeyi tam sanmasına yol açar --- hakemin gördüğü kusur
    tam olarak buydu."""
    eksik = [tip for tip in yetenek["analiz_tipleri"] if tip not in kapsam]
    assert not eksik, (
        f"yazıcı {eksik} tipini destekliyor ama rapor kapsam beyanı onu "
        f"anmıyor; beyan şunları anıyor: "
        f"{[t for t in yetenek['analiz_tipleri'] if t in kapsam]}")


def test_NLGEOM_ICIN_ZIT_IKI_IDDIA_AYNI_ANDA_OLAMAZ(yetenek, kapsam):
    """Asıl çelişki buydu. Yazıcıda NLGEOM varsa kapsam beyanı onu
    'doğrulanmamıştır ve üretim yolunda yoktur' listesine koyamaz."""
    if not yetenek["nlgeom"]:
        pytest.skip("yazıcıda NLGEOM yok; ters yön ayrı sınanır")
    i = kapsam.find("doğrulanmamıştır")
    if i < 0:
        return
    # "dogrulanmamistir" cumlesinin BITTIGI yere kadar bak: nokta ya da
    # paragraf sonu. NLGEOM o cumlenin ICINDE gecmemeli.
    son = kapsam.find(".", i)
    cumle = kapsam[i:son if son > 0 else i + 400]
    assert "NLGEOM" not in cumle, (
        "kapsam beyanı NLGEOM'u 'doğrulanmamıştır' listesinde tutuyor, "
        "oysa yazıcı onu destekliyor ve rapor ilerisinde doğrulandığını "
        f"anlatıyor. Çelişen cümle: {cumle[:200]}")


def test_KAPSAM_MALZEME_ile_GEOMETRIK_dogrusalsizligi_AYIRIYOR(kapsam):
    """NLGEOM doğrulandı diye malzeme doğrusalsızlığı da doğrulandı
    sanılmamalı; ikisi ayrı şeydir ve beyan bunu söylemeli."""
    assert "plastisite" in kapsam.lower()
    assert "malzeme" in kapsam.lower() and "geometrik" in kapsam.lower()


def test_SINIRLIDIR_IDDIASI_ESKI_LISTEYI_TASIMIYOR(yetenek, kapsam):
    """'... ile sınırlıdır' kalıbı bir KAPALI liste beyanıdır; yazıcı o
    listenin dışında bir tip destekliyorsa beyan yanlıştır."""
    for m in re.finditer(r"([^.]*?)\s+ile sınırlıdır", kapsam):
        liste = m.group(1)
        disarida = [tip for tip in yetenek["analiz_tipleri"]
                    if tip not in liste]
        assert not disarida, (
            f"'{liste[-80:].strip()} ile sınırlıdır' deniyor ama yazıcı "
            f"{disarida} tipini de destekliyor")


# ─────────────────────────────────────────────────────────────────────────
# AYNI SINIF, IKINCI YER: ust duzey YETENEK beyani vs FSI kaniti
# ─────────────────────────────────────────────────────────────────────────
# Hakem ayni raporda ikinci bir bayat cumle buldu: yetenekler tablosu ve
# Bolum 12'nin basligi "2-yonlu FSI --- ilmek kosuyor, fizik henuz tahrik
# etmiyor" diyordu, oysa Turek-Hron FSI1 uctan uca kosulmus ve yayimlanan
# dort nicelik birlikte tutturulmustu. Kusur ayni: yetenek eklendi, onu
# ANLATAN cumle guncellenmedi.

import json  # noqa: E402

FSI2Y = KOK / "turek_hron_fsi1_iki_yonlu.json"


def _tutturdu() -> bool:
    """İki-yönlü FSI kanıtı dört niceliği de bandında veriyor mu?"""
    if not FSI2Y.exists():
        return False
    d = json.loads(FSI2Y.read_text(encoding="utf-8"))
    s = d.get("sapma") or {}
    if not s or d.get("surukleme_sapma_pct") is None:
        return False
    return (abs(s["uy_pct"]) < 5 and abs(s["ux_pct"]) < 5
            and abs(d["surukleme_sapma_pct"]) < 2
            and abs(d["tasima_sapma_pct"]) < 5)


def test_YETENEK_BEYANI_FSI_KANITIYLA_CELISMIYOR():
    """Kanıt 'tutturdu' diyorsa, rapor 'fizik henüz tahrik etmiyor'
    DİYEMEZ. Ölçüt tek bir kalıba bağlanır --- prozanın geri kalanı
    serbest; sınanan şey ZIT İDDİA."""
    if not TEX.exists():
        pytest.skip("rapor yok")
    if not _tutturdu():
        pytest.skip("iki-yönlü FSI kanıtı bandı tutturmuyor; ters yön "
                    "ayrı sınanır")
    t = TEX.read_text(encoding="utf-8")
    # Tarihce ANLATILABILIR; yasak olan onu GUNCEL yetenek gibi sunmak.
    # O yuzden yalniz BASLIK/TABLO baglaminda aranir: `\item[...]` ve
    # yetenek tablosu satiri.
    for m in re.finditer(r"\\item\[([^\]]*2-yönlü FSI[^\]]*)\]", t):
        assert "tahrik etmiyor" not in m.group(1), (
            f"madde başlığı hâlâ eski hükmü taşıyor: {m.group(1)}")
    for satir in t.split("\n"):
        if satir.strip().startswith("2-yönlü FSI &"):
            assert "henüz gösterilmedi" not in satir, (
                f"yetenek tablosu eski hükmü taşıyor: {satir.strip()}")


def test_ZAMAN_BAGIMLI_FSI_ACIK_OLDUGU_da_SOYLENIYOR():
    """Ters aşırılık: 'FSI1 tuttu' diye FSI2/FSI3'ü de kapanmış göstermek.
    Beyan iki durumu AYIRMALI."""
    if not TEX.exists() or not _tutturdu():
        pytest.skip("koşul yok")
    t = TEX.read_text(encoding="utf-8")
    i = t.find(r"\label{sec:fsi2}")
    if i < 0:
        pytest.skip("fsi2 maddesi yok")
    blok = t[max(0, i - 400):i + 1200]
    assert "FSI2/FSI3" in blok
    assert ("yazılmadı" in blok or "tamamlanmadı" in blok), (
        "kararlı vaka doğrulandı ama zaman-bağımlı kuplajın hâlâ açık "
        "olduğu aynı yerde söylenmiyor")
