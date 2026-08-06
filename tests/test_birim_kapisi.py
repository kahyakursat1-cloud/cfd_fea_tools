"""Birim kapısı — üç katmanlı birim karmaşasını çalışma zamanında yakalar.

Bu depoda `youngs_modulus` adı üç yerde üç farklı birim: material_database GPa,
fea_runner MPa, analysis/calculix_writer Pa. Yanlış katmandan gelen sayı CalculiX
tarafından reddedilmez — sonuç 10³ ya da 10⁹ kat kayar ve "geçerli görünür".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from analysis.birim_kapisi import (  # noqa: E402
    malzeme_denetle,
    olasi_birim,
    pa_dogrula,
)

AL = {"e_gpa": 69.0, "rho": 2700.0, "sy_mpa": 275.0}


def test_dogru_birimler_gecer():
    assert malzeme_denetle("Al", AL["e_gpa"], "GPa", AL["rho"],
                           sigma_y=AL["sy_mpa"], nu=0.33) == []
    assert malzeme_denetle("Al", 69000.0, "MPa", AL["rho"],
                           sigma_y=AL["sy_mpa"], nu=0.33) == []
    assert malzeme_denetle("Al", 69e9, "Pa", AL["rho"],
                           sigma_y=275e6, birim_sigma="Pa") == []


def test_E_ve_sigma_farkli_birimde_olabilir():
    """materials.json E'yi GPa, σ_y'yi MPa tutar — bu ŞEMA, hata değil.
    Kapının ilk sürümü tam bunu hatalı sanmıştı."""
    assert malzeme_denetle("Al", 69.0, "GPa", 2700.0, sigma_y=275.0,
                           birim_sigma="MPa") == []


@pytest.mark.parametrize("e,birim", [(69.0, "Pa"), (69.0, "kPa"), (69.0, "MPa"),
                                     (69000.0, "GPa"), (69e9, "GPa")])
def test_yanlis_katmandan_gelen_sayi_reddedilir(e, birim):
    assert malzeme_denetle("Al", e, birim, 2700.0, sigma_y=275.0) != []


def test_dogru_birim_ONERILIR_ama_uygulanmaz():
    ihlal = malzeme_denetle("Al", 69.0, "Pa", 2700.0, sigma_y=275.0)
    assert any("GPa olarak tutarlı olurdu" in x for x in ihlal)
    # oneri bir DUZELTME degil: fonksiyon deger dondurmuyor, yalniz metin
    assert olasi_birim(69.0, 2700.0, 275e6) == ["GPa"]


def test_hicbir_birimde_tutarli_olmayan_veri():
    assert olasi_birim(1e-30) == []
    assert any("hiçbir birimde" in x
               for x in malzeme_denetle("saçma", 1e-30, "Pa", 2700.0))


def test_yogunluk_g_cm3_yakalanir():
    ihlal = malzeme_denetle("Al", 69.0, "GPa", 2.7, sigma_y=275.0)
    assert any("g/cm³" in x for x in ihlal)


def test_poisson_termodinamik_sinir():
    assert malzeme_denetle("x", 69.0, "GPa", 2700.0, nu=0.6) != []
    assert malzeme_denetle("x", 69.0, "GPa", 2700.0, nu=0.5) != []
    assert malzeme_denetle("x", 69.0, "GPa", 2700.0, nu=0.49) == []


def test_taninmayan_birim_sessizce_gecmez():
    assert malzeme_denetle("x", 69.0, "psi", 2700.0) != []
    assert malzeme_denetle("x", 69e9, "Pa", 2700.0, sigma_y=275, birim_sigma="ksi") != []


# ── kapının bağlandığı yer: Pa bekleyen katman ──────────────────────────────

def test_pa_dogrula_gecerliyi_gecirir():
    pa_dogrula("Al", 69e9, 2700.0, 275e6)


def test_pa_dogrula_gpa_degerini_reddeder():
    with pytest.raises(ValueError, match="BİRİM KAPISI"):
        pa_dogrula("Al", 69.0, 2700.0, 275e6)


def test_FEAMaterial_kapiyi_tasiyor():
    from analysis.calculix_writer import FEAMaterial
    FEAMaterial("Al", 69e9, 0.33, 2700.0, yield_strength_pa=275e6)
    with pytest.raises(ValueError, match="BİRİM KAPISI"):
        FEAMaterial("Al", 69.0, 0.33, 2700.0)          # GPa sayısı Pa alanına
    with pytest.raises(ValueError, match="BİRİM KAPISI"):
        FEAMaterial("Al", 69000.0, 0.33, 2700.0)       # MPa sayısı Pa alanına
    FEAMaterial.from_gpa("Al", 69.0, 0.33, 2700.0, yield_mpa=275.0)


# ── veri tabanlarının kendisi ────────────────────────────────────────────────

def test_materials_json_birim_tutarli():
    """materials.json elle düzenleniyor (CLAUDE.md: kaynakla birlikte güncelle).
    Bu test, bir düzenlemenin birimi kaydırmasını yakalar."""
    d = json.loads((KOK / "materials.json").read_text(encoding="utf-8"))
    ihlal = [x for ad, v in d.items()
             for x in malzeme_denetle(ad, v["youngs_modulus"], "GPa", v["density"],
                                      sigma_y=v.get("yield_strength"),
                                      nu=v.get("poisson_ratio"))]
    assert ihlal == []
    assert len(d) >= 5


def test_fea_runner_kutuphanesi_MPa_olarak_tutarli():
    from fea_runner import MATERIAL_LIBRARY
    ihlal = [x for m in MATERIAL_LIBRARY.values()
             for x in malzeme_denetle(m.name, m.youngs_modulus, "MPa", m.density,
                                      sigma_y=m.yield_strength, nu=m.poisson_ratio)]
    assert ihlal == []


def test_iki_kutuphane_ayni_ADI_farkli_BIRIMDE_tutuyor():
    """Kapının VAROLUŞ NEDENİ: aynı alan adı iki kütüphanede 1000× farklı.
    Bu bilerek böyle; test onu belgeler ve sessizce değişmesini engeller."""
    from fea_runner import MATERIAL_LIBRARY as FR
    from material_database import MaterialLibrary
    md = MaterialLibrary().get_material("Aluminum 6061")
    fr = FR["aluminum_6061"]
    assert md.youngs_modulus == pytest.approx(fr.youngs_modulus / 1000.0, rel=0.05)
