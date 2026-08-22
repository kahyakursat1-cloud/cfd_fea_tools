"""Rapor ana metin / EK ayrımı — iddia DOĞRULANIYOR, beyan edilmiyor.

Hakem incelemesi (#20): 38 sayfa tek gövde; yöntem/sonuç ile süreç/hata-tarihi
iç içe. Ayrıldı (2026-08-22): Bölüm 1--13 yöntem ve ölçülen sonuç, EK-A--C
süreç. Ön sayfada şu cümle duruyor:

    "ana metnin hiçbir hükmü onlara dayanmaz"

Bu bir YOKLUK İDDİASIDIR ve elle doğrulanmış bir yokluk iddiası, sonraki
düzenlemede sessizce yanlışa döner: ana metne eklenecek tek bir
\\ref{sec:kalite} onu çürütür ve kimse fark etmez.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
TEX = KOK / "docs" / "teknik_rapor.tex"


@pytest.fixture(scope="module")
def parcalar():
    if not TEX.exists():
        pytest.skip("teknik_rapor.tex yok")
    t = TEX.read_text(encoding="utf-8")
    if "\\appendix" not in t:
        pytest.skip("rapor ek bölümüne ayrılmamış")
    i = t.index("\\appendix")
    return t[:i], t[i:]


def test_EKLER_gercekten_var_ve_UCU(parcalar):
    _, ek = parcalar
    basliklar = re.findall(r"^\\section\{(.+?)\}", ek, re.M)
    assert len(basliklar) == 3, f"EK sayısı değişti: {basliklar}"
    assert "\\renewcommand{\\thesection}{EK-\\Alph{section}}" in ek


def test_ANA_METIN_ekteki_hicbir_etikete_atif_yapmiyor(parcalar):
    """Yokluk iddiası ÖLÇÜLÜYOR: ana metinden eke giden \\ref var mı?"""
    ana, ek = parcalar
    ek_etiketleri = set(re.findall(r"\\label\{([^}]+)\}", ek))
    ana_atiflar = set(re.findall(r"\\(?:ref|autoref|pageref)\{([^}]+)\}", ana))
    sizinti = sorted(ek_etiketleri & ana_atiflar)
    assert not sizinti, (
        f"ana metin EK'teki etikete atıf yapıyor: {sizinti} — ön sayfadaki "
        f"'ana metnin hiçbir hükmü onlara dayanmaz' cümlesi ARTIK YANLIŞ")


def test_iddia_cumlesi_ON_SAYFADA_duruyor(parcalar):
    """Cümle düşerse test de anlamsızlaşır; ikisi birlikte durmalı."""
    ana, _ = parcalar
    assert "ana metnin hiçbir hükmü onlara dayanmaz" in ana


def test_OKUNUS_notundaki_bolum_araligi_gercek_bolum_sayisiyla_ayni(parcalar):
    """`Bölüm 1--13` elle yazılı; bölüm eklenince sessizce eskirdi."""
    ana, _ = parcalar
    n = len(re.findall(r"^\\section\{", ana, re.M))
    m = re.search(r"Bölüm 1--(\d+) yöntemi", ana)
    assert m, "okunuş notu raporda yok"
    assert int(m.group(1)) == n, (
        f"not 'Bölüm 1--{m.group(1)}' diyor, ana metinde {n} bölüm var")


def test_ICINDEKILER_var(parcalar):
    """38 sayfalık belgede gezinme yoktu — hakemin asıl şikâyeti."""
    ana, _ = parcalar
    assert "\\tableofcontents" in ana
    assert "tocloft" in ana, "EK-A/B/C numara kutusu genişletilmezse başlığa taşar"


def test_YENIDEN_URETILEBILIRLIK_zinciri_EKE_kacmadi(parcalar):
    """EK'e taşınan bölümler yeniden-üretilebilirliği GÖTÜRMEMELİ.

    Ana metin kendi sayılarının üreticisini ve kanıt dosyalarını kendi içinde
    göstermeli; aksi halde hakem V&V zincirini ana metinden izleyemez ve ön
    sayfadaki iddia biçimsel olarak doğru ama pratikte yanlış olur.

    ÖLÇÜT MUTLAK SAYI DEĞİL ORANDIR: "en az beş komut" gibi bir eşik keyfîdir
    ve rapor kısaldığında yanlış alarm verir. Kural şu: zincirin ağırlığı ana
    metinde kalmalı.
    """
    ana, ek = parcalar
    komut = re.compile(r"texttt\{(?:python|Üretim|experiments/)")
    kanit = re.compile(r"[A-Za-z0-9_\\]+\.json")
    a_k, e_k = len(komut.findall(ana)), len(komut.findall(ek))
    a_j, e_j = len(set(kanit.findall(ana))), len(set(kanit.findall(ek)))
    assert a_k >= e_k, f"üretim komutlarının ağırlığı EK'e kaymış ({a_k} ana / {e_k} ek)"
    assert a_j > e_j, f"kanıt dosyalarının ağırlığı EK'e kaymış ({a_j} ana / {e_j} ek)"
