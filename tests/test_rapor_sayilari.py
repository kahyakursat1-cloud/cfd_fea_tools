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


_YAZI = {0: "sıfır", 1: "bir", 2: "iki", 3: "üç", 4: "dört", 5: "beş",
         6: "altı", 7: "yedi", 8: "sekiz"}


def test_olcum_ve_ust_sinir_AYRIMI_da_tutarli(tex, ozet):
    """HAKEM YİNE BULDU: "beşi çapa taşır; üçü ölçüm, biri üst sınır" — toplamı
    DÖRT ediyordu.

    Önceki testler yalnız `N/M hücre çapalı` ve `N hücrenin M'i` kalıplarını
    denetliyordu; ölçüm/üst-sınır AYRIMINI hiç okumuyorlardı. Dipnot ise
    "rapordaki her tekrarı testle bağlıdır" diyordu --- yani rapor kendi
    denetim iddiasını aşan bir alan taşıyordu. Bu test o alanı kapatır.
    """
    # SAYI KELIMESI + TURKCE EK. Ek serbest birakilir ('üçü', 'ikisi'), ama
    # sayinin KENDISI listeden gelmek zorunda — genel \w+ kalibi "kalan is
    # hucre" gibi ilgisiz ifadeleri de yakaliyordu.
    _s = "|".join(_YAZI.values())
    kaliplar = re.findall(
        rf"({_s})\w*\s+ölçüm[,+]\s*(?:\\textbf\{{)?({_s})\w*\s+üst\s*\n?\s*sınır",
        tex)
    kaliplar += re.findall(r"(\d+) ölçüm \+ (\d+) üst sınır", tex)
    assert kaliplar, "rapor ölçüm/üst-sınır ayrımını hiç yazmıyor mu?"
    for a, b in kaliplar:
        _a = str(ozet["olcum"]) if a.isdigit() else _YAZI[ozet["olcum"]]
        _b = str(ozet["ust_sinir"]) if b.isdigit() else _YAZI[ozet["ust_sinir"]]
        assert a == _a, f"'{a} ölçüm' — beklenen '{_a}'"
        assert b == _b, f"'{b} üst sınır' — beklenen '{_b}'"


def test_test_sayilari_AYNI_KOSUDA_olculdu(tex):
    """HAKEM SORDU: "coverage açıkken neden 23 test daha az?"

    Ölçüldü: fark YOKTU. İki sayı farklı zamanlarda ölçülüp yan yana
    konmuştu ve aradaki boşluk gerçek bir olgu gibi görünüyordu --- birlikte
    okunan iki sayı birlikte ölçülmelidir. Betik artık ikisini de tek çağrıda
    ölçüyor; bu test raporun ikisini de o ölçümden aldığını bağlar.
    """
    olcum_dosyasi = KOK / "rapor_sayilari.json"
    if not olcum_dosyasi.exists():
        pytest.skip("rapor_sayilari.json yok")
    d = json.loads(olcum_dosyasi.read_text(encoding="utf-8"))
    if "gecen_test_cov" not in d:
        pytest.skip("test sayıları ölçülmedi (python experiments/rapor_sayilari.py --test)")
    for anahtar in ("gecen_test", "gecen_test_cov"):
        beklenen = f"{d[anahtar]:,}".replace(",", ".")
        assert beklenen in tex, f"{anahtar}={d[anahtar]} raporda geçmiyor"
    # Fark varsa aciklanmali; yoksa "ayni kosuda olculdu" ibaresi durmali.
    if d["gecen_test"] == d["gecen_test_cov"]:
        assert "aynı koşuda" in tex, \
            "iki sayı eşit ama raporda birlikte ölçüldükleri yazmıyor"


def test_ozet_kendi_icinde_TOPLANIYOR(ozet):
    """ölçüm + üst sınır = çapalı; çapalı + öncül = toplam. Kanıtın kendisi
    tutarsızsa raporu ona bağlamanın anlamı kalmaz."""
    assert ozet["olcum"] + ozet["ust_sinir"] == ozet["capali"]
    assert ozet["capali"] + ozet["oncul"] == ozet["toplam_hucre"]


def test_yol_haritasindaki_KALAN_hucre_sayisi_dogru(tex, ozet):
    """v1.3 satırı "kalan beş hücre" diyordu; 8-5=3 olmuştu."""
    kalan = ozet["toplam_hucre"] - ozet["capali"]
    # "kalan is hucre x cekirdek x RAM" gibi ifadeler sayi DEGILDIR; kalip
    # yalniz sayi kelimelerini ve rakamlari kabul eder.
    _s = "|".join(_YAZI.values())
    bulunan = re.findall(rf"kalan\s+({_s}|\d+)\s+hücre", tex, re.IGNORECASE)
    assert bulunan, "yol haritası kalan-hücre ifadesi taşımıyor"
    for b in bulunan:
        assert b.lower() in (_YAZI[kalan], str(kalan)), \
            f"'kalan {b} hücre' — beklenen '{_YAZI[kalan]}' ({kalan})"


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
