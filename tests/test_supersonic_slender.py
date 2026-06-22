"""Slender-body süpersonik Cd — V&V testleri.
Çekirdek doğrulama: Fourier alan-kuralı dalga-drag, Sears-Haack analitik kapalı-formuna
karşı. Ek: roket STL üzerinde fiziksellik + bileşen ölçeklemeleri."""
import math
from pathlib import Path

import numpy as np
import pytest

from supersonic_slender import (
    _sears_haack_cd_analytic,
    base_drag_cd,
    slender_body_cd,
    wave_drag_cd,
)

ROOT = Path(__file__).resolve().parent.parent


def test_wave_drag_matches_sears_haack():
    """von Kármán Fourier dalga-drag = Sears-Haack kapalı-form (%2 içinde)."""
    R, L = 0.1, 2.0
    th = np.linspace(0, math.pi, 600)
    x = 0.5 * L * (1 - np.cos(th))
    S = math.pi * R ** 2 * np.sin(th) ** 3
    s_max = math.pi * R ** 2
    cd_num = wave_drag_cd(x, S, L, s_max, n_modes=8)
    cd_ref = _sears_haack_cd_analytic(R, L)
    assert cd_num == pytest.approx(cd_ref, rel=0.02)


def test_sears_haack_scales_with_slenderness():
    """C_Dwave ∝ (R/L)²: inceliği 2× artırınca (R yarı) drag 4× düşer."""
    assert _sears_haack_cd_analytic(0.05, 2.0) == pytest.approx(
        _sears_haack_cd_analytic(0.1, 2.0) / 4.0, rel=1e-6)


def test_base_drag_mach_scaling():
    """Ampirik taban-drag ∝ 1/M² (Cpb≈-1/M²)."""
    cd_m2 = base_drag_cd(2.0, 1.0, 1.0)
    cd_m3 = base_drag_cd(3.0, 1.0, 1.0)
    assert cd_m2 == pytest.approx(0.25, rel=1e-6)
    assert cd_m3 / cd_m2 == pytest.approx((2.0 / 3.0) ** 2, rel=1e-6)
    assert base_drag_cd(0.8, 1.0, 1.0) == 0.0      # subsonik → 0


@pytest.mark.skipif(not (ROOT / "rockets" / "rocket.stl").exists(),
                    reason="rocket.stl yok")
def test_rocket_cd_physical():
    """Roket STL: tüm bileşenler pozitif, dalga-drag fiziksel bantta, fineness slender."""
    res = slender_body_cd(ROOT / "rockets" / "rocket.stl", mach=2.0)
    assert res["cd_wave"] > 0 and res["cd_wave"] < 0.5      # despike sonrası fiziksel
    assert res["cd_friction"] > 0
    assert res["cd_base"] > 0
    assert res["fineness"] > 8                               # slender rejim
    # dalga-drag projenin inviscid CFD'siyle (≈0.066) aynı mertebede
    assert res["cd_wave"] == pytest.approx(0.066, abs=0.03)


@pytest.mark.skipif(not (ROOT / "rockets" / "rocket.stl").exists(),
                    reason="rocket.stl yok")
def test_rocket_cd_total_decreases_with_mach():
    """Toplam Cd M ile azalır (taban+sürtünme düşer; dalga slender-teoride M-bağımsız)."""
    cds = [slender_body_cd(ROOT / "rockets" / "rocket.stl", mach=m)["cd_total"]
           for m in (1.5, 2.0, 3.0)]
    assert cds[0] > cds[1] > cds[2]
