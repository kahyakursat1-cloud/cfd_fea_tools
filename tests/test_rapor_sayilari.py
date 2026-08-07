"""Raporun sayıları KANITLA tutarlı mı — tek kaynak kuralı.

HAKEM İNCELEMESİ BULDU: model-form hücre sayısı raporun dört ayrı yerinde elle
yazılıydı ve birbirini tutmuyordu (2/7, 3/7, 1/4). Dahası taban da yanlıştı —
`attached_2d` rejimi eklendiğinde toplam yediden sekize çıkmış ama hiçbir metin
güncellenmemişti.

Bu, raporun kendi savunduğu ilkeye aykırıdır ve tam olarak avladığı kusur
sınıfıdır: sabit metin, değişen veri. Metni koddan üretmek en temizi olurdu ama
rapor LaTeX ve elle yazılıyor; o yüzden kural TESTLE bağlanır — `.tex` içindeki
her hücre-sayısı ifadesi `model_form_bandi.json`'daki özetle uyuşmalı.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

TEX = KOK / "docs" / "teknik_rapor.tex"
KANIT = KOK / "model_form_bandi.json"


@pytest.fixture(scope="module")
def ozet():
    if not KANIT.exists():
        pytest.skip("model_form_bandi.json yok (python experiments/model_form_bandi.py)")
    d = json.loads(KANIT.read_text(encoding="utf-8"))
    if "ozet" not in d:
        pytest.skip("kanıt eski sürüm — özet alanı yok")
    return d["ozet"]


@pytest.fixture(scope="module")
def tex():
    if not TEX.exists():
        pytest.skip("teknik_rapor.tex yok")
    return TEX.read_text(encoding="utf-8")


def test_ozet_kendi_icinde_TUTARLI(ozet):
    """Çapalı + öncül = toplam. Tutmuyorsa bir hücre iki kez ya da hiç
    sayılmıştır ve rapordaki her tekrar o hatayı taşır."""
    assert ozet["tutarli"], ozet
    assert ozet["capali"] + ozet["oncul"] == ozet["toplam_hucre"]
    assert ozet["olcum"] + ozet["ust_sinir"] == ozet["capali"]


def test_olcum_ve_UST_SINIR_ayri_sayiliyor(ozet):
    """İkisi aynı şey değildir: üst sınır, model hatasının GÖRÜLEMEDİĞİ
    hücredir ve muhafazakâr yönde alınır. Tek sayıda toplamak, ölçülmemiş
    bir kesinlik yayımlamaktır."""
    assert set(ozet["olcum_hucreleri"]) & set(ozet["ust_sinir_hucreleri"]) == set()
    assert sorted(ozet["olcum_hucreleri"] + ozet["ust_sinir_hucreleri"]) \
        == ozet["capali_hucreler"]


def test_raporda_ESKI_taban_sayisi_gecmiyor(tex, ozet):
    """`attached_2d` eklendiğinde toplam 7'den 8'e çıktı; 'yedi hücre' diyen
    her cümle artık yanlıştır."""
    n = ozet["toplam_hucre"]
    yanlis = [k for k in ("yedi hücre", "yedi hücresinden", "dört hücresinden")
              if k in tex]
    assert not yanlis, (f"model-form tablosu {n} hücreli ama raporda hâlâ "
                        f"eski taban geçiyor: {yanlis}")


def test_raporda_capali_orani_KANITLA_uyusuyor(tex, ozet):
    """`N/M hücre çapalı` biçimindeki her ifade özetle aynı sayıları vermeli."""
    bulunan = re.findall(r"(\d+)\s*/\s*(\d+)\s*hücre çapalı", tex)
    assert bulunan, "rapor çapalı-oran ifadesi taşımıyor (bölüm kaldırıldı mı?)"
    for capali, toplam in bulunan:
        assert int(toplam) == ozet["toplam_hucre"], \
            f"raporda /{toplam} yazıyor, kanıtta {ozet['toplam_hucre']}"
        assert int(capali) == ozet["capali"], \
            f"raporda {capali} çapalı yazıyor, kanıtta {ozet['capali']}"


def test_sozel_tekrarlar_da_AYNI_sayiyi_soyluyor(tex, ozet):
    """Sayı rakamla değil yazıyla geçtiğinde de aynı olmalı; hakem çelişkiyi
    tam olarak bu tekrarlarda buldu."""
    yazi = {8: "sekiz", 7: "yedi", 5: "beş", 4: "dört", 3: "üç", 2: "iki"}
    top, cap = yazi[ozet["toplam_hucre"]], yazi[ozet["capali"]]
    kaliplar = re.findall(r"(\w+) hücrenin \\textbf\{(\w+)\}ü", tex)
    for bulunan_top, bulunan_cap in kaliplar:
        assert bulunan_top == top, f"'{bulunan_top} hücrenin' — beklenen '{top}'"
        assert bulunan_cap == cap, f"'{bulunan_cap}ü' — beklenen '{cap}'"


def test_ozet_cumlesi_UCUNU_de_ayirt_ediyor(ozet):
    c = ozet["cumle"]
    assert "ölçüm" in c and "üst sınır" in c and "öncül" in c
    assert str(ozet["toplam_hucre"]) in c


# ── Raporun KENDİ HAKKINDA yazdığı sayılar ──────────────────────────────────

SAYILAR = KOK / "rapor_sayilari.json"


@pytest.fixture(scope="module")
def olcum():
    if not SAYILAR.exists():
        pytest.skip("rapor_sayilari.json yok (python experiments/rapor_sayilari.py)")
    return json.loads(SAYILAR.read_text(encoding="utf-8"))


def _satir_sayilari(tex: str) -> list[int]:
    """Raporda geçen 'kod satırı' değerlerinin tümü (nokta binlik ayracı)."""
    ham = re.findall(r"(\d{2}\.\d{3}) satır Python", tex)
    ham += re.findall(r"analysis/\}\) & (\d{2}\.\d{3}) &", tex)
    return [int(x.replace(".", "")) for x in ham]


def test_kod_satiri_raporda_TEK_deger(tex):
    """Hakem bulgusu: kapakta 31.322, kalite tablosunda 31.307 yazıyordu.
    On beş satırlık fark önemsiz; AYRIŞMANIN KENDİSİ önemli, çünkü rapor tam
    da bunu avlayan bir sistemi anlatıyor."""
    d = _satir_sayilari(tex)
    assert len(d) >= 2, f"kod satırı ifadesi bulunamadı ({d})"
    assert len(set(d)) == 1, f"rapor farklı satır sayıları söylüyor: {sorted(set(d))}"


def test_kod_satiri_OLCUMDEN_sapmiyor(tex, olcum):
    """Tolerans var (rapor her commit'te derlenmiyor) ama sapma büyürse söyle."""
    d = _satir_sayilari(tex)
    gercek = olcum["kod_satiri"]
    sapma = abs(d[0] - gercek) / gercek * 100
    assert sapma < 3.0, (f"rapor {d[0]} satır diyor, ölçüm {gercek} "
                         f"(%{sapma:.1f} sapma) — `python experiments/"
                         "rapor_sayilari.py` ile güncelleyin")


def test_test_dosyasi_sayisi_OLCUMLE_uyusuyor(tex, olcum):
    m = re.search(r"Test dosyası & (\d+) &", tex)
    assert m, "kalite tablosunda test dosyası satırı yok"
    assert int(m.group(1)) == olcum["test_dosyasi"], (
        f"rapor {m.group(1)}, ölçüm {olcum['test_dosyasi']} test dosyası")


def test_ELLE_yazilmis_bolum_atfi_KALMADI(tex):
    r"""Bölüm numaraları eklendikçe kayar; elle yazılan atıf sessizce yanlışa
    döner. Hakem incelemesinde beş atıftan DÖRDÜ yanlıştı: \S7 topoloji yerine
    ASME'yi, \S6B mentor yerine zarfı, \S2--\S5 yanlış aralığı, \S2.4 yanlış
    alt bölümü gösteriyordu. Atıflar artık \ref ile bağlı ve derleyici
    çözülmemiş atıfı kendisi söyler."""
    elle = re.findall(r"\\S\s*\d", tex)
    assert not elle, f"elle yazılmış bölüm atfı: {elle} — \\ref kullanın"
