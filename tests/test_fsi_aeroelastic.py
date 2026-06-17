"""Statik aeroelastik FSI — burulma diverjansı, kapalı-form doğrulama (saf-NumPy)."""
import numpy as np

from fsi_aeroelastic import TorsionalDivergence


def test_fe_divergence_matches_analytic():
    # Partisyonlu FE'nin diverjans eşiği kapalı-formu yakalar (q_div=(π/2L)²GJ/(c·e·CLα))
    m = TorsionalDivergence(n=40)
    assert abs(m.q_div_fe() - m.q_div_analytic) / m.q_div_analytic < 0.01


def test_fsi_matches_direct_and_analytic_below_divergence():
    m = TorsionalDivergence(n=40)
    q = 0.5 * m.q_div_analytic
    th_f, _, conv, _ = m.solve_fsi(q)
    th_d = m.solve_direct(q)
    assert conv
    # partisyonlu FSI ↔ doğrudan kuple çözüm
    assert np.allclose(th_f, th_d, rtol=1e-4, atol=1e-9)
    # ↔ analitik uç-burulma (sec büyütme)
    assert abs(th_f[-1] - m.tip_twist_analytic(q)) / abs(m.tip_twist_analytic(q)) < 0.01


def test_fsi_diverges_above_qdiv():
    # FSI iterasyonu q>q_div'de ıraksar (aeroelastik diverjans yakalanır)
    m = TorsionalDivergence(n=40)
    _, _, conv_below, _ = m.solve_fsi(0.9 * m.q_div_analytic)
    _, _, conv_above, _ = m.solve_fsi(1.1 * m.q_div_analytic)
    assert conv_below and not conv_above


def test_tip_twist_amplifies_toward_divergence():
    # Uç burulması q→q_div'de monoton artar (sec asimptotu)
    m = TorsionalDivergence(n=30)
    tips = [m.tip_twist_analytic(r * m.q_div_analytic) for r in (0.2, 0.5, 0.8, 0.95)]
    assert all(np.diff(tips) > 0) and tips[-1] > 5 * tips[0]
