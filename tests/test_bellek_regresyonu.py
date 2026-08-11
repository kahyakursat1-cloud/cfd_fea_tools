"""Bellek katsayısı ORAN'dan değil EĞİM'den gelmeli.

Oran (artış/hücre) modeli sabit yükü (WSL2 VM, çözücü ikilileri, decomposePar
kopyaları) hücreye dağıtır ve küçük koşularda katsayıyı şişirir — ölçüldü:
18.462 hücrede 9,75 kB/hücre, 96.280 hücrede 1,66. Doğrusal model tabanı ayırır.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "experiments"))
sys.path.insert(0, str(KOK))

KANIT = KOK / "bellek_katsayisi.json"


def _kayit(cells, artis, kosu="olcum/x"):
    return {"kosu": kosu, "cells": cells, "artis_gb": artis,
            "kb_hucre": artis * 1e6 / cells}


def test_regresyon_sabit_yuku_egimden_AYIRIR():
    """Sentetik: taban 0,2 GB + 1,0 kB/hücre. Eğim tabanı içermemeli."""
    import bellek_katsayisi as bk
    kayit = [_kayit(n, 0.2 + n * 1.0 / 1e6) for n in (100_000, 400_000, 900_000)]
    r = bk.regresyon(kayit)
    assert r["kb_hucre"] == pytest.approx(1.0, rel=1e-3)
    assert r["sabit_yuk_gb"] == pytest.approx(0.2, abs=1e-3)
    assert r["r2"] > 0.999


def test_oran_modeli_ayni_veride_YANILIR():
    """Aynı sentetik veride oran-medyanı gerçek katsayının çok üstünde."""
    import statistics
    kayit = [_kayit(n, 0.2 + n * 1.0 / 1e6) for n in (100_000, 400_000, 900_000)]
    medyan = statistics.median(k["kb_hucre"] for k in kayit)
    assert medyan > 1.4, "oran modeli tabanı hücreye dağıtmıyor mu?"


def test_uc_noktadan_azinda_regresyon_yok():
    import bellek_katsayisi as bk
    assert bk.regresyon([_kayit(1000, 0.1), _kayit(2000, 0.2)]) is None


def test_ayni_hucre_sayisinda_egim_hesaplanmaz():
    """Hücre sayısı değişmiyorsa eğim tanımsızdır — sıfıra bölme değil None."""
    import bellek_katsayisi as bk
    assert bk.regresyon([_kayit(1000, 0.1), _kayit(1000, 0.2),
                         _kayit(1000, 0.3)]) is None


@pytest.fixture(scope="module")
def kanit() -> dict:
    if not KANIT.exists():
        pytest.skip("bellek_katsayisi.json yok")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_katsayi_olculdu_ve_kume_KONTROLLU(kanit):
    if kanit.get("kb_hucre") is None:
        pytest.skip("katsayı henüz ölçülmedi — ret gerekçesi kayıtlı")
    reg = kanit["regresyon"]
    assert reg["r2"] >= 0.90
    assert "kontrollü" in reg["kume"], reg["kume"]
    assert kanit["kb_hucre"] == reg["kb_hucre"], "yayımlanan sayı eğim değil"


def test_mutlak_artis_kucukse_UST_SINIR_denir(kanit):
    """Uyum iyi olsa bile artışlar gürültü eşiğinin altındaysa bu yazılmalı."""
    if kanit.get("kb_hucre") is None:
        pytest.skip("katsayı ölçülmedi")
    import bellek_katsayisi as bk
    kume = [k for k in kanit["kosular"] if str(k["kosu"]).startswith("olcum/")]
    if kume and max(k["artis_gb"] for k in kume) < bk.EN_AZ_ARTIS_GB:
        assert "UST SINIR" in kanit["verdikt"]


def test_kapi_olculen_katsayiyi_KULLANIR(kanit):
    if kanit.get("kb_hucre") is None:
        pytest.skip("katsayı ölçülmedi")
    import bellek_kapisi as bk
    k = bk.katsayi()
    assert k["olculdu"] is True
    assert k["kb_hucre"] == kanit["kb_hucre"]
    assert k["kb_hucre"] != bk.ONCUL_KB_HUCRE


def test_raporlanan_iki_sayi_birbiriyle_TUTARLI():
    """gereken_gb, RAPORLANAN ham_gb'den türetilebilmeli — yuvarlama kaçağı yok."""
    import bellek_kapisi as bk
    for n in (50_000, 365_608, 1_000_000, 5_000_000):
        t = bk.tahmini_gb(n)
        assert t["gereken_gb"] == pytest.approx(t["ham_gb"] * bk.GUVENLIK_PAYI,
                                                rel=1e-3), n
