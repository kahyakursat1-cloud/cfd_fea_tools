"""Taşıma sınırı REJİME BAĞLI — tek eşik iki yönde de yanlıştı.

|Cl| ≤ 3.0'lık evrensel eşik, çok-elemanlı yüksek-taşıma kesitini (CLmax 3.5–4.5)
haksız reddederken, AR≈6 düz bir kanadın fiziksel tavanı ~1.5 iken 2× yanlış bir
sayıyı sessizce geçiriyordu. Sınır artık rejimden gelir; rejim beyan edilmezse
kapı GEVŞER ve gevşediğini çıktısında söyler.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from validity_envelope import (  # noqa: E402
    CL_MAX_PLAUSIBLE,
    CL_MAX_REJIM,
    cl_siniri,
    force_admissibility,
    rejim_arac_tipinden,
)


def test_evrensel_sinir_rejimlerin_en_gevsegi():
    """Beyan edilmemiş rejimde daha SIKI bir sınır uygulamak, hangi rejimde
    olduğunu bilmediğimiz geçerli sonucu reddetmek olurdu."""
    assert max(CL_MAX_REJIM.values()) == CL_MAX_PLAUSIBLE


@pytest.mark.parametrize("rejim,cl,kabul", [
    ("3b_duz_kanat", 1.5, True),
    ("3b_duz_kanat", 2.5, False),      # eski 3.0 esigi bunu GECIRIYORDU
    ("2b_tek_elemanli", 1.9, True),
    ("2b_tek_elemanli", 2.6, False),
    ("2b_cok_elemanli", 4.0, True),    # eski 3.0 esigi bunu REDDEDIYORDU
    ("kunt", 0.5, True),
    ("kunt", 1.2, False),
])
def test_rejim_basina_sinir(rejim, cl, kabul):
    f = force_admissibility(0.02, cl, 4.0, rejim=rejim)
    assert (f["verdict"] != "inadmissible") == kabul, f


def test_rejim_beyan_edilmezse_kapinin_zayifligi_yazilir():
    f = force_admissibility(0.02, 2.5, 4.0)
    assert f["verdict"] == "ok"
    assert f["cl_kapisi"]["beyan_edildi"] is False
    assert "REJİM BEYAN EDİLMEDİ" in f["cl_kapisi"]["kaynak"]
    # ayni sayi, rejim beyan edilince REDDEDILIR
    assert force_admissibility(0.02, 2.5, 4.0,
                               rejim="3b_duz_kanat")["verdict"] == "inadmissible"


def test_taninmayan_rejim_sessizce_bir_rejime_atanmaz():
    sinir, kaynak = cl_siniri("kanat_gibi_bir_sey")
    assert sinir == CL_MAX_PLAUSIBLE
    assert "BEYAN EDİLMEDİ" in kaynak


def test_arac_tipi_esleme():
    assert rejim_arac_tipinden("ucak") == "3b_duz_kanat"
    assert rejim_arac_tipinden("araba") == "kunt"
    assert rejim_arac_tipinden("bilinmeyen") is None
    assert rejim_arac_tipinden(None) is None


def test_cl_kapisi_yalniz_Cl_varken_raporlanir():
    assert "cl_kapisi" not in force_admissibility(0.02)
    assert "cl_kapisi" in force_admissibility(0.02, 0.4)


def test_diger_hukumler_bozulmadi():
    assert force_admissibility(float("nan"), 0.4)["verdict"] == "inadmissible"
    assert force_admissibility(-0.01, 0.4)["verdict"] == "inadmissible"
    assert force_admissibility(0.02, -0.4, 6.0)["verdict"] == "suspect"


def test_uretim_cagri_yerleri_rejim_beyan_ediyor():
    """Sınırı rejime bağlamak, çağıranlar beyan etmezse hiçbir şey değiştirmez."""
    for dosya, beklenen in (("xfoil_kesit.py", 'rejim="2b_tek_elemanli"'),
                            ("transition_polar.py", 'rejim="2b_tek_elemanli"'),
                            ("report_generator.py", 'rejim="2b_tek_elemanli"'),
                            ("vehicle_pipeline.py", "rejim_arac_tipinden(vehicle_type)"),
                            ("vehicle_polar.py", "rejim_arac_tipinden(vehicle_type)")):
        assert beklenen in (KOK / dosya).read_text(encoding="utf-8"), dosya
