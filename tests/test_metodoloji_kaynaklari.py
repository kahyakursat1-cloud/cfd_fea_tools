"""Metodoloji kaynakları: liste ELLE yazılır, KAPSAMI denetlenir.

DIŞ HAKEM P2 (2026-08-26): kaynakça var ama metodolojide kullanılan bazı
önemli kaynaklar metinde geçtiği hâlde listede yok --- Svanberg, Eça &
Hoekstra, Celik ve ark., Le ve ark., ASME V&V 20.

Haklıydı, ve `kaynakca.py`nin KENDİ DOCSTRING'İ bu isimleri sayıyordu ama
üretici onları basmıyordu: betik yalnız çapa kayıtlarının `kaynak`
alanlarını topluyor.

YÖN NEDEN TERS. Bu depoda kural ``elle liste yazma, kanıttan üret''. Burada
uygulanamaz: bir GCI formülünün ya da MMA'nın kaynağı hiçbir koşunun
çıktısında yazmaz --- üretilecek bir yer yoktur. O yüzden liste BEYAN edilir
ama bu testler KAPSAMI bağlar: raporda atfı geçen her metodoloji kaynağı
kayıtta olmalı. Böylece liste eskirse ya da rapora yeni bir atıf girerse
süit düşer --- ``sabit metin, değişen veri'' kusuru bu kez kaynakçada
yakalanır.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

KAYIT = KOK / "docs" / "metodoloji_kaynaklari.json"
TEX = KOK / "docs" / "teknik_rapor.tex"
KAYNAKCA = KOK / "docs" / "kaynakca.tex"

# RAPORDA ATFI GECEBILEN METODOLOJI KAYNAKLARI: metin deseni -> kayit anahtari.
# Desen RAPORUN yazdigi bicimdir (LaTeX kacislariyla), anahtar kayittaki ad.
ATIF_DESENLERI = {
    r"Svanberg": "Svanberg 1987",
    r"Le ve ark": "Le ve ark. 2010",
    r"Celik ve ark": "Celik ve ark. 2008",
    r"Eça \\& Hoekstra|Eça ve Hoekstra": "Eça & Hoekstra 2014",
    r"ASME V\\&V 20": "ASME V&V 20",
    r"Richardson ekstrapolasyonu": "Richardson",
}


@pytest.fixture(scope="module")
def kayit():
    if not KAYIT.exists():
        pytest.skip("docs/metodoloji_kaynaklari.json yok")
    return json.loads(KAYIT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tex():
    if not TEX.exists():
        pytest.skip("teknik_rapor.tex yok")
    return TEX.read_text(encoding="utf-8")


def test_RAPORDA_gecen_her_metodoloji_kaynagi_KAYITTA(kayit, tex):
    """Kapsam kapısı: atıf varsa künye de olmalı."""
    anahtarlar = {k["anahtar"] for k in kayit["kaynaklar"]}
    eksik = []
    for desen, ad in ATIF_DESENLERI.items():
        if re.search(desen, tex) and ad not in anahtarlar:
            eksik.append(ad)
    assert not eksik, (
        f"rapor bu kaynaklara atıf yapıyor ama künyeleri kayıtta yok: {eksik}")


def test_KAYITTAKI_her_kaynak_RAPORDA_KULLANILIYOR(kayit, tex):
    """Ters yön: kullanılmayan künye kaynakçayı şişirir.

    Yalniz-pozitif denetim yetmez --- liste zamanla artik kullanilmayan
    kaynaklarla dolar ve kaynakca oldugundan zengin gorunur.
    """
    kullanilmayan = []
    for k in kayit["kaynaklar"]:
        desen = next((d for d, ad in ATIF_DESENLERI.items()
                      if ad == k["anahtar"]), None)
        if desen is None:
            kullanilmayan.append(f"{k['anahtar']} (atıf deseni tanımlı değil)")
        elif not re.search(desen, tex):
            kullanilmayan.append(k["anahtar"])
    assert not kullanilmayan, (
        f"kayıtta olup raporda kullanılmayan künye: {kullanilmayan}")


def test_KUNYELER_kaynakca_TEX_ciktisina_giriyor(kayit):
    """Kayıtta olup üretilen kaynakçaya girmeyen künye, olmayan künyeyle
    aynı kapıya çıkar --- okuyucu onu göremez."""
    if not KAYNAKCA.exists():
        pytest.skip("kaynakca.tex üretilmemiş (python experiments/kaynakca.py)")
    t = KAYNAKCA.read_text(encoding="utf-8")
    for k in kayit["kaynaklar"]:
        # Kunyenin ilk yazar soyadi + yil, TEX kacislarindan etkilenmez.
        m = re.match(r"([A-ZÇĞİÖŞÜ][\w'-]+)", k["kunye"])
        assert m and m.group(1) in t, \
            f"{k['anahtar']} kaynakça çıktısında yok"


def test_DOGRULANMAMIS_DOI_oyle_ISARETLENIYOR(kayit):
    """DOI'ler bu depoda birincil kaynaktan doğrulanmadı ve bu GÖRÜNMELİ.

    Doğrulanmamış bir DOI, eksik DOI'den tehlikelidir: tamamlanmış görünür.
    """
    dogrulanmamis = [k for k in kayit["kaynaklar"]
                     if k.get("doi") and not k.get("doi_dogrulandi")]
    if not dogrulanmamis:
        return
    if not KAYNAKCA.exists():
        pytest.skip("kaynakca.tex üretilmemiş")
    t = KAYNAKCA.read_text(encoding="utf-8")
    assert "doğrulanmadı" in t, \
        "doğrulanmamış DOI'ler kaynakçada işaretsiz basılıyor"
    assert "doğrulanmadı" in kayit["_kisit"] or "dogrulanmadi" in kayit["_kisit"]


def test_HER_KUNYE_YIL_ve_KAYNAK_TASIYOR(kayit):
    """Künye eksikse kaynakça işlevsizdir; bu ucuz bir yapı denetimidir."""
    for k in kayit["kaynaklar"]:
        assert re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", k["kunye"]), \
            f"{k['anahtar']}: künyede yıl yok"
        assert len(k["kunye"]) > 40, f"{k['anahtar']}: künye fazla kısa"
        assert k.get("nerede"), f"{k['anahtar']}: nerede kullanıldığı yazılmamış"


def test_URETICI_DOCSTRINGI_ile_CIKTISI_AYRISMIYOR():
    """`kaynakca.py` docstring'i metodoloji kaynaklarını sayıyordu ama
    üretici onları basmıyordu --- iddia ile çıktı ayrışmıştı."""
    src = (KOK / "experiments" / "kaynakca.py").read_text(encoding="utf-8")
    assert "_metodoloji" in src, "üretici metodoloji künyelerini hiç okumuyor"
    assert "metodoloji_kaynaklari.json" in src
