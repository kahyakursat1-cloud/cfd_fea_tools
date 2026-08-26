"""Kaynakça üretiliyor mu, ve rapor onu gerçekten içeriyor mu?

Dış inceleme (2026-08-26) yakaladı: rapor onlarca literatür kaynağı
kullanıyordu (Ladson, Driver & Seegmiller, Achenbach, Roshko, Williamson,
Hoerner...) ama ayrı bir kaynakça bölümü YOKTU. Dahili bir geliştirme raporu
için tolere edilebilir; akademik çıktı ya da proje kanıtı olarak kullanılacaksa
şart.

ELLE LİSTE YAZILMADI. Kaynaklar zaten yapısal duruyordu — çapa kayıtlarının
`kaynak` alanlarında ve kod sabitlerinde. Elle yazmak, raporun kendi avladığı
kusuru işlemek olurdu: sabit metin, değişen veri.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

import kaynakca as k  # noqa: E402


def test_SUREC_NOTU_kaynak_sayilmiyor():
    """`kaynak` alanları literatürü de süreç notunu da taşır; ikisi ayrılmalı."""
    assert not k._literatur_mu("--oku: mevcut case'ten okundu, yeniden kurulmadı")
    assert not k._literatur_mu("GCI (Richardson, asimptotik)")
    assert k._literatur_mu("Roshko, J. Fluid Mech. 10 (1961); Norberg 2003")
    assert k._literatur_mu("Ladson, C. L., NASA TM-4074 (1988) — Langley tüneli")


def test_YIL_ve_GOSTERGE_birlikte_araniyor():
    """Yalnız yıl ya da yalnız dergi adı yetmez; ikisi birden gerekir."""
    assert not k._literatur_mu("Bir cümle 1985 yılında yazıldı ve bitti burada")
    assert not k._literatur_mu("J. Fluid Mech. dergisinde yayımlanmış bir yazı")


def test_MUKERRER_kunye_birlestiriliyor():
    """Aynı kaynak iki dosyada farklı yazılmışsa iki kez sayılmamalı."""
    a = k._anahtar("Hoerner 1965, Fluid-Dynamic Drag")
    b = k._anahtar("Hoerner 1965, Fluid-Dynamic Drag; Re>1e4 Re-bagimsiz")
    assert a == b


def test_LATEX_kacisi_UNICODE_de_kapsiyor():
    """Üretilen bir dosyanın derlenmemesi, üretilmemiş olmakla aynı kapıya
    çıkar. İlk sürüm π ve ≈ geçirdi ve pdflatex hata verdi."""
    s = k._kacir("Lz=πD, Cd≈1,33 & %5 hata _alt")
    for yasak in ("π", "≈", "&", "%", "_"):
        assert yasak not in s.replace(r"\&", "").replace(r"\%", "").replace(r"\_", "")


def test_uretilen_kaynakca_RAPORDA():
    tex = KOK / "docs" / "kaynakca.tex"
    if not tex.exists():
        pytest.skip("kaynakca.tex üretilmemiş")
    rapor = (KOK / "docs" / "teknik_rapor.tex").read_text(encoding="utf-8")
    assert r"\input{kaynakca}" in rapor, "rapor kaynakçayı içermiyor"
    assert r"\section*{Kaynaklar}" in rapor
    icerik = tex.read_text(encoding="utf-8")
    assert icerik.count(r"\bibitem") >= 10, "kaynakça beklenenden kısa"


def test_kaynakca_KANITLA_tutarli():
    """Üretilen .tex ile kanıt JSON'u aynı sayıyı söylemeli."""
    j = KOK / "kaynakca.json"
    tex = KOK / "docs" / "kaynakca.tex"
    if not (j.exists() and tex.exists()):
        pytest.skip("kaynakça üretilmemiş")
    d = json.loads(j.read_text(encoding="utf-8"))
    assert d["kaynak_sayisi"] == tex.read_text(encoding="utf-8").count(r"\bibitem")


def test_DOI_uydurulmadigini_SOYLUYOR():
    """Tamamlanmış gibi görünen bir kaynakça, tamamlanmamış olandan
    tehlikelidir — kısıt kayıtta ve raporda yazılı olmalı."""
    j = KOK / "kaynakca.json"
    if not j.exists():
        pytest.skip("kaynakça üretilmemiş")
    d = json.loads(j.read_text(encoding="utf-8"))
    assert "UYDURULMAZ" in d["_kisit"]
    rapor = (KOK / "docs" / "teknik_rapor.tex").read_text(encoding="utf-8")
    assert "birincil kaynaktan" in rapor
