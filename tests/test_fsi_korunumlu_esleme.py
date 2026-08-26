"""Korunumlu eşleme gerçekten korunumlu mu — ve bedeli ölçülüyor mu?

ÖLÇÜLEN KUSUR: mevcut şema basıncı taşıyıp kuvveti FEA ağında YENİDEN
İNTEGRE ediyor; alanlar farklıysa toplam kuvvet de farklı çıkıyor
(24 vakada %0,07--%72,04, hata ALAN FARKINI izliyor).

KORUNUM BİR KİMLİKTİR, BULGU DEĞİL: ağırlıklar 1'e toplandığı için toplam
kuvvet zaten korunur. Bu testlerin işi kimliğin GERÇEKTEN sağlandığını ve
bedelin ÖLÇÜLDÜĞÜNÜ doğrulamak.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from fsi_korunumlu_esleme import baryentrik, korunumlu_dagit  # noqa: E402


def test_agirliklar_BIRE_toplaniyor():
    r = np.random.default_rng(7)
    a, b, c = r.normal(size=(3, 40, 3))
    p = (a + b + c) / 3 + r.normal(scale=0.4, size=(40, 3))
    w = baryentrik(p, a, b, c)
    assert np.allclose(w.sum(axis=1), 1.0, atol=1e-12)
    assert (w >= 0).all(), "negatif ağırlık: bir düğüme ters kuvvet binerdi"


def test_koseler_ve_merkez_DOGRU():
    a = np.array([[0.0, 0, 0]]); b = np.array([[1.0, 0, 0]])
    c = np.array([[0.0, 1, 0]])
    assert np.allclose(baryentrik(a, a, b, c), [[1, 0, 0]], atol=1e-9)
    assert np.allclose(baryentrik((a + b + c) / 3, a, b, c), [[1 / 3] * 3], atol=1e-9)


def test_DEJENERE_ucgen_sifira_bolmuyor():
    a = np.array([[0.0, 0, 0]]); b = a.copy(); c = a.copy()
    w = baryentrik(np.array([[1.0, 1, 1]]), a, b, c)
    assert np.isfinite(w).all() and np.isclose(w.sum(), 1.0)


def test_TOPLAM_KUVVET_makine_hassasiyetinde_korunuyor():
    """Şemanın var oluş sebebi. Alanlar KASITLI olarak uyumsuz seçildi."""
    r = np.random.default_rng(3)
    dugum = r.normal(size=(60, 3))
    faces = np.array([[i, (i + 1) % 60, (i + 2) % 60] for i in range(58)])
    f_merkez = dugum[faces].mean(axis=1)
    cfd_merkez = r.normal(scale=1.7, size=(400, 3))     # BASKA bir bulut
    dF = r.normal(size=(400, 3))
    kuvvet, tani = korunumlu_dagit(dF, cfd_merkez, dugum, faces, f_merkez)
    fark = np.linalg.norm(kuvvet.sum(axis=0) - dF.sum(axis=0))
    olcek = np.linalg.norm(dF, axis=1).sum()
    assert fark / olcek < 1e-12, f"kuvvet korunmuyor: {fark / olcek:.2e}"
    assert tani["n_cfd_yuz"] == 400


def test_BEDEL_olculuyor_ve_gizlenmiyor():
    """Kuvvet korunuyor diye bedel yokmuş gibi davranmak, bu çalışmanın
    reddettiği şey. Tanı sözlüğü kaymayı ve kırpmayı taşımalı."""
    r = np.random.default_rng(11)
    dugum = r.normal(size=(30, 3))
    faces = np.array([[i, (i + 1) % 30, (i + 2) % 30] for i in range(28)])
    _, tani = korunumlu_dagit(r.normal(size=(50, 3)), r.normal(size=(50, 3)),
                              dugum, faces, dugum[faces].mean(axis=1))
    for anahtar in ("kayma_ort_m", "kayma_max_m", "kayma_ort_govde_orani",
                    "kirpilan_izdusum_orani_pct"):
        assert anahtar in tani, f"bedel ölçüsü eksik: {anahtar}"
    assert 0.0 <= tani["kirpilan_izdusum_orani_pct"] <= 100.0


def test_kiyas_kaniti_IKI_SEMAYI_AYNI_olcutle_kiyasliyor():
    """Mevcut şemanın 1e-17'lik moment hatası FEA yüzü→düğüm adımını ölçer ve
    YAPI GEREĞİ kesindir. İki şemayı o sayıyla kıyaslamak, yeni şemayı haksız
    yere kötü gösterirdi."""
    import json
    y = KOK / "fsi_esleme_kiyasi.json"
    if not y.exists():
        pytest.skip("kıyas üretilmemiş")
    d = json.loads(y.read_text(encoding="utf-8"))
    for k in d["vakalar"]:
        assert "mevcut_moment_hatasi_pct" in k, "mevcut şema aynı ölçütle ölçülmemiş"
    # KUVVET KORUNUMU HER VAKADA
    assert all(k["korunumlu_aktarim_hatasi_pct"] < 1e-3 for k in d["vakalar"])
    # KIMLIK OLDUGU SOYLENIYOR MU
    assert "KİMLİK" in d["verdikt"]
    # SEMA HENUZ DEGISTIRILMEDI — karar yapisal yanita bagli
    assert "DEĞİŞTİRİLMEDİ" in d["verdikt"]


def test_uretim_yolu_HENUZ_degismedi():
    """Ölçmeden değiştirmek bu çalışmanın reddettiği şey. Üretim yolu
    (`coupling_fsi`) hâlâ mevcut şemayı kullanmalı; değişirse bu test
    kasıtlı olarak düşer ve karar kayda geçmiş olur."""
    src = (KOK / "coupling_fsi.py").read_text(encoding="utf-8")
    assert "korunumlu_dagit" not in src, (
        "üretim yolu korunumlu şemaya geçmiş — yapısal yanıt kıyası yapıldı mı? "
        "Yapıldıysa bu testi gerekçesiyle güncelleyin.")
