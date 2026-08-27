"""Basınç-yalnız aktarımın eksik bıraktığı pay --- ve ÖLÇÜLEMEYENİN sayımı.

BU TARAMA İKİ KEZ YANLIŞ KURULDU ve ikisi de kendi lehine yanlıştı:

  1. ÖLÇÜT FAZLA GENİŞ. İlk sürüm bileşeni kendi paydasıyla normalize
     ediyordu: |v_i| / (|p_i| + |v_i|). Basıncın sıfıra yakın olduğu bir
     bileşende (2B vakanın z ekseni) bu %100 verir --- fiziksel olarak
     önemsiz bir sayının içinde. Sonuç: 16 ailenin 16'sı işaretlendi ve
     tarama hiçbir şey ayırt etmedi. Doğru payda TAŞINAN TOPLAM yüktür.

  2. KAPSAM SESSİZCE DÜŞTÜ. Okunamayan dosyalar atlanıyordu; hüküm ``16
     ailede ölçüldü'' diyordu ama 35 aile vardı ve 19'unda diskte yalnız
     forceCoeffs.dat var --- o dosya basınç/viskoz ayrımı taşımaz. Yani
     üretim araç yolu dahil 138 kayıtta sorunun cevabı ``önemsiz'' değil
     ``bilinmiyor''du, ve tarama bunu söylemiyordu.

Testler bu iki kusuru kilitler.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "kayma_payi.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("kayma_payi.json yok (python experiments/kayma_payi.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_OLCUT_TASINAN_YUKE_gore_normalize(_=None):
    """Ölçüt saf fonksiyondan sınanır --- o anki veriye pinlenmez."""
    from kayma_payi import _pay
    # Basincin sifira yakin oldugu bir BILESENDE eski olcut %100 verirdi.
    # Yeni olcut o bileseni TOPLAM yuke gore tartar ve kucuk bulur.
    r = _pay(basinc=[100.0, 0.0, 0.0], viskoz=[0.0, 0.001, 0.0])
    assert r["eksik_bilesen_pct"] < 1.0, (
        "yükü olmayan bir bileşendeki viskoz kuvvet büyük görünüyor; "
        "payda yine kendi bileşeni olmuş")
    # Turek-Hron imzasi: viskoz basinctan BUYUK -> oran %100'u asar.
    r2 = _pay(basinc=[-0.003, 0.006, 0.0], viskoz=[0.0289, 0.0, 0.0])
    assert r2["eksik_oran_pct"] > 100.0


def test_OLCUT_YANLIS_NEGATIF_vermiyor():
    """Bandın diğer yüzü: gerçekten önemsiz bir viskoz pay eşiği AŞMAMALI.
    Yalnız birincisi olsaydı ölçütü sıfıra bağlamak da testi geçerdi."""
    from kayma_payi import ESIK_PCT, _pay
    r = _pay(basinc=[1000.0, 50.0, 0.0], viskoz=[1.0, 0.2, 0.0])
    assert r["eksik_oran_pct"] < ESIK_PCT


def test_CEVAPSIZ_AILELER_SAYILIYOR_ve_hukumde(kanit):
    """Kapsam boşluğu kayıtta ve hükümde görünmeli. Görünmezse tarama
    'ölçtüm' der ama ölçemediğini saklar."""
    assert "cevapsiz_aile" in kanit
    v = kanit["verdikt"]
    if kanit["cevapsiz_aile"]:
        assert "AYRIM YOK" in v or "CEVAPSIZ" in v
        assert "bilinmiyor" in kanit["_cevapsizlik_sebebi"]
        # Sayilar kayitla TUTARLI olmali; elle yazilsaydi ayrisirdi.
        assert str(len(kanit["cevapsiz_aile"])) in v


def test_TARAMA_TARAYABILDIGINDEN_COK_DOSYA_GORDU(kanit):
    """Yokluk iddiasını doğrula: taranan dosya sayısı, okunabilen aile
    kayıtlarının toplamından büyükse fark AÇIKLANMIŞ olmalı."""
    okunan = sum(a["n"] for a in kanit["aileler"])
    cevapsiz = sum(c["dosya"] for c in kanit["cevapsiz_aile"])
    assert okunan + cevapsiz <= kanit["taranan_dosya"]
    assert kanit["taranan_dosya"] > 0


def test_AYRIM_HEM_ASAN_HEM_ASMAYAN_uretiyor(kanit):
    """Bir ölçüt her şeyi ya da hiçbir şeyi işaretliyorsa ayırt etmiyordur
    --- ilk sürüm tam olarak bunu yapıyordu (16/16)."""
    if len(kanit["aileler"]) < 4:
        pytest.skip("ayrım için yeterli aile yok")
    asan = [a for a in kanit["aileler"] if a["esigi_asiyor"]]
    assert 0 < len(asan) < len(kanit["aileler"]), (
        f"{len(asan)}/{len(kanit['aileler'])} aile işaretli --- ölçüt "
        "ayırt etmiyor")


def test_VISKOZ_TAM_SIFIR_SUPHESI_kayitli(kanit):
    """Tarama sırasında OpenFOAM 11'in wallShearStress'i laminer bir
    vakada tam sıfır yazdı. Aynı imza forces kayıtlarında çıkarsa 'viskoz
    önemsiz' okuması YANLIŞ olur; sayaç bunun için var."""
    for a in kanit["aileler"]:
        assert "viskoz_tam_sifir_kayit" in a


def test_KISIT_yapisal_yaniti_OLCMEDIGINI_soyluyor(kanit):
    k = kanit["_kisit"]
    assert "YAPISAL YANIT" in k
    assert "duzeltme katsayisi degil" in k


def test_URETIM_YOLU_artik_AYRIMI_YAZIYOR():
    """Bulgunun kapanışı: vaka yazıcısı basınç/viskoz ayrımını da yazmalı.
    Yoksa yeni koşular da cevapsız kalır ve bulgu tekrarlanır."""
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    assert "type            forces;" in src, (
        "vaka yazıcısı yalnız forceCoeffs yazıyor; basınç/viskoz ayrımı "
        "kaydedilmezse bu soru yeni koşularda da sorulamaz")
    assert "kuvvetBilesenleri" in src


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if r"kayma\_payi" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    assert str(kanit["taranan_dosya"]) in t, "taranan dosya sayısı raporda yok"
    assert str(len(kanit["aileler"])) in t
    cevapsiz_dosya = sum(c["dosya"] for c in kanit["cevapsiz_aile"])
    assert str(cevapsiz_dosya) in t, (
        f"cevapsız dosya sayısı ({cevapsiz_dosya}) raporda yok --- kapsam "
        "boşluğu prozadan düşerse bulgunun yarısı kaybolur")
    assert str(len(kanit["cevapsiz_aile"])) in t
    # ESIK ve EN YUKSEK deger de kayittan gelmeli
    assert "\\%" + f"{kanit['esik_pct']:.0f}" in t
