"""Eşleşik karşılaştırma ρ=1 varsayıyor — varsayım ÖLÇÜLDÜ ve yük taşıdığında söyleniyor.

`_ayirt_edilebilirlik` eşleşik dalda ortak model-form hatasını farkta TAMAMEN
götürüyor. Bu ρ=1 demektir ve ölçülmemişti. Ölçüldü (2026-08-22): bluff.
wall_function hücresindeki üç çapa da AYNI yöne sapıyor (+3,38 / +1,79 /
+9,31) — ortak bias gerçek. Ama saçılma sıfır değil ve ρ=1 onu sıfır sayıyor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from eslesik_korelasyon import artik_model_bandi, rho_kestir  # noqa: E402

from kosu_gecmisi import _ayirt_edilebilirlik  # noqa: E402


def test_ISARET_sart_zit_yonlu_sapmalar_rho_yu_SISIRMEZ():
    """Mutlak değerle çalışsaydı zıt yöne sapan iki çapa aynı yönde görünürdü.

    Eşleştirmenin TÜM dayanağı sapmaların aynı yönde olmasıdır: ortak bias
    ancak o zaman farkta götürülür.
    """
    ayni = rho_kestir([3.38, 1.79, 9.31])
    zit = rho_kestir([3.38, -1.79, 9.31])

    assert ayni["ayni_yonde_mi"] is True
    assert zit["ayni_yonde_mi"] is False
    assert zit["rho"] < ayni["rho"], "yön karışıkken ρ DÜŞMELİ"
    # mutlak deger kullanilsaydi ikisi ozdes cikardi — kusurun imzasi
    assert rho_kestir([3.38, 1.79, 9.31])["rho"] != pytest.approx(zit["rho"])


def test_rho_UC_NOKTALARI_mevcut_ikili_varsayimla_ortusuyor():
    """Bugünkü ikili dal, tek formülün iki ucu: ρ=1 → 0, ρ=0 → u_m·√2."""
    assert artik_model_bandi(9.31, 1.0) == pytest.approx(0.0)
    assert artik_model_bandi(9.31, 0.0) == pytest.approx(9.31 * 2 ** 0.5)
    # ara deger ikisinin ARASINDA
    ara = artik_model_bandi(9.31, 0.69)
    assert 0.0 < ara < 9.31 * 2 ** 0.5


def test_tek_capadan_rho_KESTIRILMEZ():
    r = rho_kestir([4.2])
    assert r["rho"] is None
    assert "KESTİRİLMEDİ" in r["gerekce"]


def test_SACILMA_sayisal_banddan_kucukse_UST_SINIR_denir():
    """Ölçülen σ (3,23) çapaların sayısal bandından (~5) küçük.

    O halde vakaya özgü model saçılması sayısal gürültüden AYRILAMAZ ve
    ölçülen σ bir kestirim değil ÜST SINIRDIR. Kanıt dosyası bunu yazmalı;
    yazmazsa ayırt edilemeyen bir sayı ölçülmüş gibi kullanılır.
    """
    p = KOK / "eslesik_korelasyon.json"
    if not p.exists():
        pytest.skip("eslesik_korelasyon.json üretilmemiş")
    h = json.loads(p.read_text(encoding="utf-8"))["hucreler"]["bluff.wall_function"]
    assert h["sacilma_sayisaldan_ayrilabilir_mi"] is False
    assert "ÜST" in h["_yorum"] and "SINIR" in h["_yorum"]
    assert h["ayni_yonde_mi"] is True, "ortak bias eşleştirmenin dayanağı"


def _kosu(cd: float, **k):
    return {"cd": cd, "tip": "araba", "duvar_cozunur": False,
            "u_sayisal_pct": 4.0, "u_model_pct": 9.31, "u_pct": 10.1, **k}


def test_varsayim_YUK_TASIDIGINDA_hukumde_soyleniyor():
    """Fark bandın hemen dışındaysa hüküm ρ=1'e yaslanır — bu görünmeli."""
    if not (KOK / "eslesik_korelasyon.json").exists():
        pytest.skip("eslesik_korelasyon.json üretilmemiş")
    r = _ayirt_edilebilirlik(_kosu(0.300), _kosu(0.300 * 1.06), [])
    assert r["varsayim_yuk_tasiyor"] is True
    assert "ρ=1 varsayımına yaslanıyor" in r["hukum"]
    assert r["genisletilmis_band_pct"] > r["band_rss_pct"]


@pytest.mark.parametrize("carpan", [1.03, 1.12])
def test_varsayim_yuk_TASIMADIGINDA_susuyor(carpan):
    """İçeride ve rahatça dışarıda: varsayım hükmü çevirmiyor, uyarı da yok.

    Uyarıyı her hükme basmak, uyarıyı okunmaz yapardı.
    """
    if not (KOK / "eslesik_korelasyon.json").exists():
        pytest.skip("eslesik_korelasyon.json üretilmemiş")
    r = _ayirt_edilebilirlik(_kosu(0.300), _kosu(0.300 * carpan), [])
    assert "varsayim_yuk_tasiyor" not in r
    assert "ρ=1" not in r["hukum"]


def test_ESLESMEMIS_dalda_rho_notu_YOK():
    """Eşleşmemişte model zaten banda dahil — ρ notu anlamsız olurdu."""
    a, b = _kosu(0.300), _kosu(0.330, duvar_cozunur=True)
    r = _ayirt_edilebilirlik(a, b, [])
    assert r["band_tipi"].startswith("eşleşmemiş")
    assert "varsayim_yuk_tasiyor" not in r


def test_rho_BASKA_hucreye_tasinmiyor():
    """Bir hücrede ölçülen ρ, u_model'i tutmayan koşuya UYGULANMAZ."""
    if not (KOK / "eslesik_korelasyon.json").exists():
        pytest.skip("eslesik_korelasyon.json üretilmemiş")
    # u_model 20.0 -> olculen hicbir hucreyle eslesmez
    a, b = _kosu(0.300, u_model_pct=20.0), _kosu(0.318, u_model_pct=20.0)
    r = _ayirt_edilebilirlik(a, b, [])
    assert "varsayim_yuk_tasiyor" not in r


def test_iki_kosunun_u_model_i_FARKLIYSA_iddia_yok():
    from kosu_gecmisi import _hucre_esle
    kayit = {"hucreler": {"x.y": {"rho": 0.69, "artik_model_bandi_pct": 7.33,
                                  "u_model_pct": 9.31}}}
    assert _hucre_esle(kayit, 9.31, 9.31) is not None
    assert _hucre_esle(kayit, 9.31, 12.0) is None
    assert _hucre_esle(kayit, None, 9.31) is None
