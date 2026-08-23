"""MMA doğru mu — ve OC'nin attığı bilgiyi gerçekten kullanıyor mu.

NEDEN GEREKLİ: OC adımı `np.maximum(-dx, 0)` ile POZİTİF duyarlılığı sıfırlar.
Kompliyansta duyarlılık hep negatiftir, kayıp yok. P-norm gerilmede değil ---
ölçüldü (L-braket 3B): aktif elemanların %12,8–65,7'si her adımda pozitif
duyarlılık taşıyor ve gradyan BÜYÜKLÜĞÜNÜN atılan payı bir adımda %96,9'a
çıkıyor; amaç tam o adımda 12,95 → 97,54 sıçrıyor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from mma import MMADurum, mma_adim  # noqa: E402


def test_ANALITIK_cozume_oturuyor():
    """min Σ c_j/x_j s.t. Σx ≤ V — Lagrange çözümü kapalı formda bilinir.

    Bir optimizasyon kodunun ilk sınavı bu olmalı: bilinen cevabı veriyor mu.
    """
    n = 20
    rng = np.random.default_rng(7)
    c = rng.uniform(0.5, 2.0, n)
    V = 4.0
    xmin, xmax = np.full(n, 0.01), np.ones(n)

    lam = (np.sum(np.sqrt(c)) / V) ** 2
    x_an = np.clip(np.sqrt(c / lam), 0.01, 1.0)

    x = np.full(n, V / n)
    d = MMADurum()
    for _ in range(60):
        x = mma_adim(x, -c / x ** 2, np.ones(n), float(x.sum() - V), xmin, xmax, d)

    assert np.abs(x - x_an).max() < 1e-6, "MMA analitik çözüme oturmuyor"
    assert x.sum() == pytest.approx(V, rel=1e-6), "hacim kısıtı ihlal"


def test_POZITIF_gradyan_KULLANILIYOR():
    """OC'nin attığı bilgi MMA'da korunuyor mu.

    Yarısı pozitif yarısı negatif gradyanlı doğrusal amaç: pozitif olanlar
    alt sınıra, negatif olanlar hacmin izin verdiğince üst sınıra gitmeli.
    OC bu problemde pozitif yarıyı SIFIR duyarlılık sanardı.
    """
    n = 20
    a = np.concatenate([np.full(n // 2, +1.0), np.full(n // 2, -1.0)])
    xmin, xmax = np.full(n, 0.01), np.ones(n)
    V = 4.0
    x = np.full(n, V / n)
    d = MMADurum()
    for _ in range(80):
        x = mma_adim(x, a, np.ones(n), float(x.sum() - V), xmin, xmax, d)

    assert x[:n // 2].mean() < 0.05, "pozitif gradyanlı elemanlar alt sınıra inmedi"
    assert x[n // 2:].mean() > 0.3, "negatif gradyanlı elemanlar hacmi almadı"


def test_KISIT_saglanandaysa_lambda_SIFIR():
    """Hacim zaten altındaysa kısıt bağlayıcı değildir; λ=0 olmalı."""
    n = 10
    xmin, xmax = np.full(n, 0.01), np.ones(n)
    x = np.full(n, 0.1)                       # toplam 1.0, kısıt 5.0
    d = MMADurum()
    mma_adim(x, -np.ones(n), np.ones(n), float(x.sum() - 5.0), xmin, xmax, d)
    assert d.gecmis[-1]["lambda"] == pytest.approx(0.0, abs=1e-9)


def test_ASIMPTOTLAR_SALINIMDA_yaklasiyor():
    """MMA'nın kararlılığı BELLEKTEN gelir: salınım görülürse adım küçülür.

    OC belleksizdir ve bu yüzden limit çevrimine girer.
    """
    from mma import S_HIZLI, S_YAVAS, _asimptotlar
    assert S_YAVAS < 1.0 < S_HIZLI
    n = 5
    xmin, xmax = np.zeros(n), np.ones(n)
    d = MMADurum(xold1=np.full(n, 0.5), xold2=np.full(n, 0.4),
                 low=np.full(n, 0.0), upp=np.full(n, 1.0), iterasyon=5)
    # x < xold1 < xold2 DEGIL: x=0.4, xold1=0.5, xold2=0.4 -> isaret ters (salinim)
    low_s, upp_s = _asimptotlar(np.full(n, 0.4), xmin, xmax, d)
    # tekduze durum
    d2 = MMADurum(xold1=np.full(n, 0.5), xold2=np.full(n, 0.6),
                  low=np.full(n, 0.0), upp=np.full(n, 1.0), iterasyon=5)
    low_m, upp_m = _asimptotlar(np.full(n, 0.4), xmin, xmax, d2)
    assert (upp_s - low_s).mean() < (upp_m - low_m).mean(), (
        "salınımda asimptotlar YAKLAŞMALI (adım küçülmeli)")


def test_KANIT_SON_DEGERI_tek_basina_sunmuyor():
    """OC daha düşük sayı veriyor ama LİMİT ÇEVRİMİNDE; "daha düşük" ile
    "savunulabilir" farklı şeyler ve kanıt bunu ayırmalı."""
    p = KOK / "mma_vs_oc.json"
    if not p.exists():
        pytest.skip("mma_vs_oc.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "bosa_giden_hareket_pct" in d["oc"]
    assert "durma_noktasi_yayilimi_pct" in d["oc"]
    assert "SON DEĞER TEK BAŞINA YANILTIR" in d["verdikt"]
    # OC'nin bosa giden hareketi MMA'nınkinden BELIRGIN buyuk olmali
    assert d["oc"]["bosa_giden_hareket_pct"] > 3 * d["mma"]["bosa_giden_hareket_pct"]


def test_KIYAS_SOGUK_baslangicta_yapildi():
    """Sınanan şey tam olarak warm-start'a duyulan ihtiyaç; warm-start
    verilseydi soru sorulmamış olurdu."""
    p = KOK / "mma_vs_oc.json"
    if not p.exists():
        pytest.skip("mma_vs_oc.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "SOĞUK" in d["problem"]["baslangic"]
    assert "TEK problem" in d["_kisit"], "tek-problem kısıtı yazılmamış"


def test_MMA_katsayilari_PROBLEME_gore_ayarlanmadi():
    """Ayarlanırsa kıyas adaletsiz olur; Svanberg'in değerleri korunmalı."""
    from mma import ALBEFA, S_HIZLI, S_INIT, S_YAVAS
    assert (S_INIT, S_YAVAS, S_HIZLI, ALBEFA) == (0.5, 0.7, 1.2, 0.1)
