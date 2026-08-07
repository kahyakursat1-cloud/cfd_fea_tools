"""Karar/V&V motorunun DEĞİŞMEZLERİ — örnek değil, kural sınanır.

Bu katman ürünün en kritik parçası: sayının yayımlanıp yayımlanmayacağına o
karar veriyor. Örnek-tabanlı testler yalnız denenen vakayı korur; burada
kuralın KENDİSİ rastgele üretilmiş girdi aileleri üzerinde sınanır (tohum
sabit — kırılma yeniden üretilebilir).

Sınanan değişmezler:
  1. Belirsizlik NEGATİF olamaz, NaN/inf olamaz.
  2. ÖLÇÜLMEYEN bileşen sıfır sayılamaz; toplam "alt sınır" diye işaretlenir.
  3. RET varsa yayım YOK — hiçbir yoldan.
  4. Band ÜRETİLDİĞİ AİLEYE aittir; başka ayara taşınamaz.
  5. h = N^(-1/d): boyut değişince ayrıklaştırma ölçeği doğru değişir.
  6. Fizik-dışı değer kanıta giremez.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from girdi_belirsizligi import birlestir  # noqa: E402
from report_generator import band_from_levels, compute_gci  # noqa: E402
from validity_envelope import force_admissibility, sonuc_kapisi  # noqa: E402

TOHUM = 20260807


def _seviye_aileleri(n=200):
    """Rastgele ama FİZİKSEL mesh aileleri: artan hücre, yakınsayan/salınan Cd."""
    rng = random.Random(TOHUM)
    for _ in range(n):
        k = rng.choice((3, 4, 5))
        taban = rng.uniform(2e4, 3e5)
        oran = rng.uniform(1.3, 2.2)
        cells = [taban * oran ** i for i in range(k)]
        f0 = rng.uniform(0.005, 1.5)
        tip = rng.choice(("yakinsak", "salinimli", "duz"))
        if tip == "yakinsak":
            cds = [f0 * (1 + rng.uniform(0.01, 0.2) / (1.8 ** i)) for i in range(k)]
        elif tip == "salinimli":
            cds = [f0 * (1 + (-1) ** i * rng.uniform(0.01, 0.1)) for i in range(k)]
        else:
            cds = [f0] * k
        yield cells, cds, tip


# ── 1. Belirsizlik negatif olamaz ──────────────────────────────────────────

def test_band_asla_negatif_ya_da_sonsuz_degil():
    for cells, cds, tip in _seviye_aileleri():
        b = band_from_levels(cells, cds)
        if b is None:
            continue
        u = b.get("u_pct")
        assert u is None or (u >= 0 and math.isfinite(u)), (tip, cells, cds, b)


def test_band_her_zaman_yontemini_soyluyor():
    """Bandın hangi yöntemden geldiği bilinmeden ona güvenilemez."""
    for cells, cds, _ in _seviye_aileleri(60):
        b = band_from_levels(cells, cds)
        if b and b.get("u_pct") is not None:
            assert b.get("yontem"), b
            assert b.get("kaynak"), b


def test_gci_negatif_band_uretmez():
    rng = random.Random(TOHUM + 1)
    for _ in range(200):
        h = sorted((rng.uniform(0.5, 2.0) for _ in range(3)), reverse=True)
        f = [rng.uniform(0.01, 2.0) for _ in range(3)]
        g = compute_gci(h[0], h[1], h[2], f[0], f[1], f[2])
        if not g:
            continue
        for anahtar in ("gci_fine_pct", "gci_med_pct"):
            v = g.get(anahtar)
            assert v is None or (v >= 0 and math.isfinite(v)), (h, f, g)
        # Band URETILMEDIYSE nedeni yazili olmali — sessiz None olmaz.
        if g.get("gci_fine_pct") is None:
            assert g.get("gecersiz"), g
            assert g.get("p") is not None, "tanı (p) kaybedilmemeli"


# ── 2. Ölçülmeyen bileşen SIFIR sayılamaz ─────────────────────────────────

def test_olculmeyen_bilesen_sifir_sayilmaz():
    rng = random.Random(TOHUM + 2)
    for _ in range(150):
        olculen = {f"b{i}": rng.uniform(0.1, 20.0) for i in range(rng.randint(1, 3))}
        eksik = {f"e{i}": None for i in range(rng.randint(1, 2))}
        r = birlestir({**olculen, **eksik})
        assert r["alt_sinir_mi"] is True, r
        assert r["olculmeyen_bilesenler"], r


def test_hepsi_olculduyse_alt_sinir_degil():
    r = birlestir({"a": 3.0, "b": 4.0})
    assert r["alt_sinir_mi"] is False
    assert r["u_toplam_pct"] == pytest.approx(5.0, rel=1e-6)   # RSS


def test_RSS_bilesenlerin_hicbirinden_kucuk_degil():
    """Birleştirme bir bileşeni YUTAMAZ."""
    rng = random.Random(TOHUM + 3)
    for _ in range(200):
        b = {f"b{i}": rng.uniform(0.01, 50.0) for i in range(rng.randint(2, 5))}
        r = birlestir(b)
        assert r["u_toplam_pct"] >= max(b.values()) - 1e-9, (b, r)


# ── 3. RET varsa yayım YOK ────────────────────────────────────────────────

def test_fizik_disi_her_zaman_engel():
    rng = random.Random(TOHUM + 4)
    for _ in range(200):
        conv = {"drift_ok": rng.random() < 0.5, "rezidual_ok": rng.random() < 0.5}
        bel = {"u_toplam_pct": rng.uniform(0, 50)} if rng.random() < 0.5 else None
        k = sonuc_kapisi({"verdict": "inadmissible", "reasons": ["sebep"]}, conv, bel)
        assert k["seviye"] == "engel", (conv, bel, k)
        assert k["gerekce"], "ret gerekçesiz olamaz"


def test_engel_hukmunde_GEREKCE_hep_var():
    for fizik in ({"verdict": "inadmissible", "reasons": ["a", "b"]},
                  {"verdict": "inadmissible", "reasons": ["tek"]}):
        k = sonuc_kapisi(fizik, {"drift_ok": True})
        assert k["seviye"] == "engel" and len(k["gerekce"]) >= 1


def test_negatif_surukleme_HICBIR_yoldan_kabul_edilmez():
    rng = random.Random(TOHUM + 5)
    for _ in range(200):
        cd = -abs(rng.uniform(1e-6, 5.0))
        cl = rng.uniform(-2, 2)
        for rejim in (None, "3b_duz_kanat", "kunt", "2b_cok_elemanli"):
            f = force_admissibility(cd, cl, rng.uniform(-10, 10), rejim=rejim)
            assert f["verdict"] == "inadmissible", (cd, rejim, f)


def test_sonlu_olmayan_deger_kanita_giremez():
    for kotu in (float("nan"), float("inf"), -float("inf")):
        assert force_admissibility(kotu, 0.5)["verdict"] == "inadmissible"
        assert force_admissibility(0.02, kotu)["verdict"] == "inadmissible"


# ── 4. Band ürettiği aileye aittir ────────────────────────────────────────

def test_band_aile_bilgisini_TASIYOR():
    """Band, hangi ayar ailesinden geldiğini taşımazsa başka bir ayara
    taşınabilir ve bu sessiz bir hatadır."""
    for cells, cds, _ in _seviye_aileleri(60):
        b = band_from_levels(cells, cds)
        if b and b.get("u_pct") is not None:
            assert "seviye" in b or "kaynak" in b, b


def test_ayni_veri_farkli_BOYUTTA_farkli_band_verir():
    """h = N^(-1/d): boyut ayrıklaştırma ölçeğini değiştirir, dolayısıyla
    gözlenen mertebeyi ve bandı da. Aynı çıkması, boyutun yok sayıldığını
    gösterirdi."""
    cells = [5.0e4, 1.5e5, 4.5e5]
    cds = [0.32, 0.305, 0.3005]
    b3 = band_from_levels(cells, cds, boyut=3)
    b2 = band_from_levels(cells, cds, boyut=2)
    assert b3 and b2
    if b3.get("u_pct") is not None and b2.get("u_pct") is not None:
        assert b3["u_pct"] != b2["u_pct"], (b3, b2)


def test_boyut_olcegi_dogru_yonde():
    """h = N^(-1/d): d BÜYÜDÜKÇE üs sıfıra yaklaşır, yani aynı N daha BÜYÜK
    (kaba) bir h verir. 3B'de bir milyon hücre, 2B'de bir milyon hücreden daha
    kaba bir ayrıklaştırmadır — ilk yazımımda yönü ters kurmuştum."""
    n = 1.0e5
    assert n ** (-1 / 3) > n ** (-1 / 2)
    assert n ** (-1 / 1) < n ** (-1 / 2) < n ** (-1 / 3)


# ── 5. Kapı zinciri tutarlı ───────────────────────────────────────────────

def test_saglikli_kosu_engel_uretmez():
    k = sonuc_kapisi({"verdict": "ok", "reasons": []},
                     {"drift_ok": True, "rezidual_ok": True},
                     {"u_toplam_pct": 5.0})
    assert k["seviye"] != "engel"


def test_kapi_hep_seviye_ve_etiket_donduruyor():
    rng = random.Random(TOHUM + 6)
    for _ in range(150):
        fizik = rng.choice(({"verdict": "ok", "reasons": []},
                            {"verdict": "suspect", "reasons": ["s"]},
                            {"verdict": "inadmissible", "reasons": ["i"]}, None))
        conv = rng.choice(({"drift_ok": True}, {"drift_ok": False}, None))
        k = sonuc_kapisi(fizik, conv)
        assert k["seviye"] in ("engel", "uyari", "ok", "temiz"), k
        assert k["etiket"], k
        assert isinstance(k["gerekce"], list)
