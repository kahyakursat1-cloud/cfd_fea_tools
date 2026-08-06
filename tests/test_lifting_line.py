"""Taşıyıcı-çizgi hakemi — indüklenen direncin KAYNAĞI burası oldu.

NEDEN: birleştirici indüklenen direnci VSPAERO'dan alıyordu ve ölçüldü ki
VSPAERO'nun İKİ CDi çıktısı da kuramdan sapıyor (AR=5, α=4):
    taper   kuram   yakın-alan      Trefftz
     1.00   0.963   0.807 (−16%)   1.032  (+7%)
     0.70   0.982   0.792 (−19%)   1.268 (+29%)
     0.50   0.991   0.787 (−21%)   1.601 (+62%)
İkisi arasından seçim keyfî olurdu. Bu modül hakemdir; hakemin kendisi de
doğrulanmak zorunda.
"""
import math

import lifting_line as ll


def test_ELIPTIK_planformda_e_TAM_BIR():
    """Munk: eliptik yükleme indüklenen direnci minimize eder, e=1.0 TAM.
    Çözücü bunu vermiyorsa hiçbir ölçümünde kullanılamaz."""
    for ar in (4.0, 5.0, 6.0, 8.0, 12.0):
        e = ll.span_verimi(ar, 1.0, eliptik=True)
        assert abs(e - 1.0) < 1e-4, (ar, e)


def test_e_HER_ZAMAN_sinirin_altinda():
    """Düzlemsel kanatta e≤1 matematiksel sınırdır."""
    for ar in (4.0, 5.0, 8.0):
        for taper in (1.0, 0.85, 0.7, 0.5, 0.35):
            assert ll.span_verimi(ar, taper) <= 1.0 + 1e-9


def test_taper_egilimi_KURAMSAL():
    """Sivriltme yüklemeyi eliptiğe yaklaştırır: e ARTAR ve en iyi nokta
    taper ~0.3-0.4 civarındadır (ders kitabı davranışı)."""
    e = {t: ll.span_verimi(5.0, t) for t in (1.0, 0.85, 0.7, 0.5, 0.4, 0.3)}
    assert e[1.0] < e[0.85] < e[0.7] < e[0.5]
    assert e[0.4] > e[0.3], "en iyi nokta 0.3'ün altına kaymamalı"
    assert e[0.4] > e[1.0]


def test_tasima_egimi_PRANDTL_ile_TUTARLI():
    """1/a_3B = 1/a_2B + (1+τ)/(π·AR); eliptikte τ=0, yani a=2π·AR/(AR+2)."""
    for ar in (5.0, 8.0):
        beklenen = 2 * math.pi * ar / (ar + 2)
        assert abs(ll.tasima_egimi(ar, 1.0, eliptik=True) - beklenen) / beklenen < 2e-3


def test_terim_sayisina_YAKINSAMIS():
    """Sayı, çözücünün ayrıklaştırmasına takılı kalmamalı."""
    a = ll.span_verimi(5.0, 0.7, n_terim=20)
    b = ll.span_verimi(5.0, 0.7, n_terim=60)
    assert abs(a - b) < 1e-3, (a, b)


def test_induklenen_direnc_TANIMI():
    cl, ar, taper = 0.4, 5.0, 0.7
    e = ll.span_verimi(ar, taper)
    assert abs(ll.induklenen_direnc(cl, ar, taper)
               - cl ** 2 / (math.pi * ar * e)) < 1e-12


class TestGecerlilik:
    """Kuramın nerede kullanılamayacağı ÇAĞIRANA BIRAKILMAZ."""

    def test_dusuk_AR_REDDEDILIYOR(self):
        assert ll.gecerli_mi(3.0)

    def test_buyuk_ok_acisi_REDDEDILIYOR(self):
        assert ll.gecerli_mi(6.0, 30.0)

    def test_minihawk_planformu_GECERLI(self):
        # AR=5.0, ok açısı 2° — taşıyıcı-çizgi burada kullanılabilir
        assert ll.gecerli_mi(5.0, 2.0) is None

    def test_ret_GEREKCELI(self):
        assert "AR" in ll.gecerli_mi(3.0)
        assert "ok açısı" in ll.gecerli_mi(6.0, 30.0)
