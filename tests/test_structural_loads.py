"""FlightEnvelope (V-n + gust zarfı) karakterizasyon testleri.

pipeline.py AIRCRAFT_CFG ile aynı MiniHawk İHA konfigini sabitler. Amaç: Faz 3/4
refactor'u sırasında V-n/gust hesabının davranışını dondurmak (FAR-23 fiziği).
"""
import math

import pytest

from structural_loads import CATEGORY_LIMITS, FlightEnvelope


@pytest.fixture
def minihawk() -> FlightEnvelope:
    return FlightEnvelope(
        mass_kg=1.8, wing_area_m2=0.45, wing_span_m=1.5, mac_m=0.30,
        cl_max=1.3, cl_min=-1.04, cl_alpha=5.0, v_cruise_ms=18.0,
        category="normal",
    )


def test_post_init_derived(minihawk):
    assert pytest.approx(1.8 * 9.81) == minihawk.W
    assert pytest.approx(1.8 * 9.81 / 0.45) == minihawk.WS
    assert minihawk.n_max == CATEGORY_LIMITS["normal"]["n_max"]
    assert minihawk.n_min == CATEGORY_LIMITS["normal"]["n_min"]


def test_stall_and_design_speeds(minihawk):
    # Vs1 = sqrt(2W / (rho*S*CLmax))
    expected_vs1 = math.sqrt(2 * minihawk.W / (1.225 * 0.45 * 1.3))
    assert minihawk.Vs1 == pytest.approx(expected_vs1, rel=1e-9)
    # Va = Vs1 * sqrt(n_max)
    assert minihawk.Va == pytest.approx(expected_vs1 * math.sqrt(3.8), rel=1e-9)
    # Vd = 1.40 * Vc  (kodun mevcut FAR-23 katsayısı)
    assert minihawk.Vd == pytest.approx(1.40 * 18.0)
    # Hız sıralaması fiziksel olarak tutarlı
    assert minihawk.Vs1 < minihawk.Va < minihawk.Vc < minihawk.Vd


def test_maneuver_envelope_plateaus_at_limits(minihawk):
    env = minihawk.maneuver_envelope(n_pts=40)
    # En yüksek hızda yük faktörü n_max platosuna oturmalı
    assert env["upper_curve"][-1][1] == pytest.approx(minihawk.n_max)
    assert env["lower_curve"][-1][1] == pytest.approx(minihawk.n_min)
    # Stall eğrisi monoton artan (V büyüdükçe taşınabilir n artar, platoya dek)
    ns = [n for _, n in env["upper_curve"]]
    assert ns == sorted(ns)


def test_gust_dominates_for_light_uav(minihawk):
    """Hafif İHA'da gust yük faktörü manevra n_max'ı aşar — kodun temel iddiası."""
    crit = minihawk.critical_load_cases()
    n_values = [abs(c["n"]) for c in crit]
    assert max(n_values) > minihawk.n_max
    # Tasarım-kritik durum bir gust durumu olmalı
    worst = max(crit, key=lambda c: abs(c["n"]))
    assert "gust" in worst["name"].lower()


def test_summary_is_serializable(minihawk):
    import json
    s = minihawk.summary()
    assert "critical_cases" in s and "speeds_ms" in s
    json.dumps(s, default=str)  # JSON'a yazılabilir olmalı (pipeline gereği)
