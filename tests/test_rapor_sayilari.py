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
