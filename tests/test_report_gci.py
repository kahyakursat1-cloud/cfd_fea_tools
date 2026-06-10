"""report_generator GCI cekirdegi: Richardson + ASME V&V 20 verdikt mantigi."""
import pytest

from report_generator import GCI_PASS_PCT, compute_gci, gci_verdict


def _ideal_levels(p=2.0, f_exact=0.010, c=0.05, r=1.3):
    h_fine, h_med, h_coarse = 0.001, 0.001 * r, 0.001 * r * r
    def f(h): return f_exact + c * h**p
    return h_coarse, h_med, h_fine, f(h_coarse), f(h_med), f(h_fine)


def test_ideal_second_order_recovers_p_and_fexact():
    gci = compute_gci(*_ideal_levels(p=2.0))
    assert gci["monotonic"]
    assert gci["p"] == pytest.approx(2.0, abs=0.01)
    assert gci["f_exact"] == pytest.approx(0.010, rel=1e-3)
    assert gci["p_in_range"]


def test_ideal_case_passes_verdict():
    gci = compute_gci(*_ideal_levels(p=2.0))
    assert gci_verdict(gci).startswith("✅")


def test_sublinear_p_flagged():
    # Bes-seviye O-grid calismasindaki gercek davranis: e32 ~ e21 -> p ~ 0.2
    gci = compute_gci(0.00544, 0.00415, 0.00321, 0.00639, 0.00868, 0.01085)
    assert gci["p"] < 0.5
    assert not gci["p_in_range"]
    v = gci_verdict(gci)
    assert v.startswith("⚠️")
    assert "p=" in v


def test_superconvergent_p_flagged():
    # Eski MiniHawk raporundaki p=4.14 vakasi: GCI kucuk olsa da yesil verilmez
    gci = compute_gci(0.025, 0.012, 0.006, 0.0286, 0.0233, 0.0230)
    assert gci["p"] > 3.0
    assert gci_verdict(gci).startswith("⚠️")


def test_oscillatory_sequence_flagged():
    gci = compute_gci(*_ideal_levels(p=2.0)[:3], 0.0102, 0.0098, 0.0101)
    assert not gci["monotonic"]
    assert "salinimli" in gci_verdict(gci)


def test_large_gci_flagged_even_if_monotone_and_p_ok():
    h3, h2, h1, f3, f2, f1 = _ideal_levels(p=2.0, c=50.0)
    gci = compute_gci(h3, h2, h1, f3, f2, f1)
    if gci["gci_fine_pct"] >= GCI_PASS_PCT:
        assert gci_verdict(gci).startswith("⚠️")


def test_identical_values_returns_none():
    assert compute_gci(0.004, 0.003, 0.002, 0.01, 0.01, 0.01) is None
