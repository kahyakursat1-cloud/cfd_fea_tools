"""CFD1 ağ ailesi: bir turdur açık duran kısıt kapandı --- ve ADAYI ELEDİ.

CFD1 kaydında ``ağ-bağımsızlığı SINANMADI'' notu bir turdur duruyordu.
Dört seviye koşuldu ve not kapandı: sürükleme yayılımı %0,17, taşıma
%3,1. Taşıma sürüklemeden yirmi kat duyarlı çıktı, yani ``taşıma bu
geometride 5 mm'lik eksen kaçıklığından doğar'' gerekçesi doğrulandı.

Aile bir hata avı sırasında yazıldı: o gün iki-yönlü FSI1 sehimi
referansın %77 üstündeydi ve ağ şüphelilerden biriydi. Ağ elendi ve kusur
sonradan o döngünün kendi bayat-veri yolunda bulundu. Testler bu yüzden
AVA değil ÖLÇÜME bağlanır --- av anlatısı değişse de aile geçerli kalır.

SÜRÜKLEMEDE GÖZLEMLENEN MERTEBE NEGATİF ÇIKTI (p<0). Bu bir kusur değil,
Richardson'ın uygulanamadığının işaretidir: seviyeler arası fark (%0,17)
sayısal gürültü mertebesinde. Kayıt hem GCI'yi hem çıplak yayılımı taşır
ki ``band yok'' ile ``band sıfır'' karışmasın.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_ag_bagimsizligi.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_ag_bagimsizligi.json yok "
                    "(python experiments/turek_hron_ag_bagimsizligi.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_AILE_TAM_ve_HER_SEVIYE_KOSTU(kanit):
    dusen = [s["olcek"] for s in kanit["seviyeler"] if not s.get("kosdu")]
    assert not dusen, f"düşen seviyeler: {dusen}"
    assert len(kanit["seviyeler"]) >= 4, "LSR için en az 4 seviye gerekir"


def test_SEVIYELER_GERCEKTEN_AYRISIYOR(kanit):
    """Ölçek değişip hücre sayısı değişmiyorsa aile sahtedir."""
    h = [s["hucre"] for s in kanit["seviyeler"]]
    assert len(set(h)) == len(h), f"hücre sayıları tekrarlıyor: {h}"
    assert max(h) / min(h) > 3.0, (
        f"en ince/en kaba hücre oranı yalnız {max(h) / min(h):.2f} --- "
        "aile bir yakınsama iddiası taşıyamaz")


def test_HER_SEVIYE_YAKINSADI(kanit):
    yak = [s["olcek"] for s in kanit["seviyeler"]
           if s.get("yakinsadi") is False]
    assert not yak, f"rezidüel eşiğini geçmeyen seviyeler: {yak}"


def test_URETIM_AGI_AILENIN_ICINDE(kanit):
    """Yayımlanan sayının ailenin neresinde durduğu görünmeli; üretim ağı
    dışarıda bırakılsaydı band o sayı hakkında bir şey söylemezdi."""
    assert 1.0 in kanit["olcekler"]


def test_BAND_ve_CIPLAK_YAYILIM_BIRLIKTE(kanit):
    """GCI mertebe tanımsız kalabilir; o durumda elde en azından yayılım
    kalmalı, yoksa 'band yok' ile 'band sıfır' karışır."""
    for ad in ("surukleme", "tasima"):
        d = kanit[ad]
        assert d.get("yayilim_pct") is not None, f"{ad}: yayılım yok"
        assert "gci" in d, f"{ad}: GCI hesaplanmamış"


def test_SURUKLEME_MERTEBESI_TANIMSIZLIGI_GIZLENMIYOR(kanit):
    """Negatif ya da anlamsız p bir SONUÇTUR ve kayıtta durmalıdır ---
    'GCI %-0,27' diye tek başına raporlanırsa okur onu bir band sanır."""
    g = kanit["surukleme"]["gci"]
    if g.get("p_order") is not None and g["p_order"] < 0.5:
        assert kanit["surukleme"]["yayilim_pct"] < 1.0, (
            "mertebe anlamsız ama yayılım büyük --- bu bir gürültü "
            "açıklaması değildir")


def test_TASIMA_SURUKLEMEDEN_DAHA_DUYARLI(kanit):
    """Vakanın fizik iddiası: taşıma 5 mm'lik kaçıklıktan doğar ve ağa
    sürüklemeden çok daha duyarlıdır. Tersi çıkarsa gerekçe yanlıştır."""
    assert (kanit["tasima"]["yayilim_pct"]
            > kanit["surukleme"]["yayilim_pct"]), (
        "taşıma sürüklemeden daha az duyarlı çıktı; kaydın gerekçesi bu "
        "veriyle desteklenmiyor")


def test_HUKUM_YAYILIMI_ve_KAPATTIGI_NOTU_SOYLUYOR(kanit):
    """Hüküm, ailenin ne ölçtüğünü ve neyi kapattığını söylemeli."""
    v = kanit["verdikt"]
    assert str(kanit["tasima"]["yayilim_pct"]) in v
    assert str(kanit["surukleme"]["yayilim_pct"]) in v
    assert "SINANMADI" in v, (
        "hüküm hangi kısıtı kapattığını söylemiyor")


def test_KISIT_RIJIT_oldugunu_ve_YAPI_AGINI_DISLADIGINI_soyluyor(kanit):
    k = kanit["_kisit"]
    assert "RIJIT" in k
    assert "Yapisal ag bu ailenin DISINDADIR" in k
    assert "tekduze" in k


def test_URETIM_AGI_CFD1_SONUCUYLA_TUTARLI(kanit):
    """Aile üretim ağını da koşuyor; o seviye CFD1 kanıtından belirgin
    sapıyorsa iki yol ayrışmıştır."""
    cfd1 = KOK / "turek_hron_cfd1.json"
    if not cfd1.exists():
        pytest.skip("CFD1 kanıtı yok")
    c = json.loads(cfd1.read_text(encoding="utf-8"))
    if not c["kuvvet"].get("okundu"):
        pytest.skip("CFD1 kuvveti okunamadı")
    uretim = next((s for s in kanit["seviyeler"] if s["olcek"] == 1.0), None)
    assert uretim is not None
    assert uretim["surukleme_N_m"] == pytest.approx(
        c["kuvvet"]["surukleme_N"], rel=0.02)


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "ag\\_bagimsizligi" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    for deger in (kanit["surukleme"]["yayilim_pct"],
                  kanit["tasima"]["yayilim_pct"]):
        s = f"{deger}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
