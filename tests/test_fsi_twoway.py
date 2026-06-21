"""2-way partitioned FSI çekirdeği — kapalı-form sabit-nokta + Aitken'in ıraksak
kuplajı yakınsatması + çok-DOF. Saf-NumPy (CFD/FEA yok)."""
import numpy as np

from fsi_twoway import linear_fsi_exact, linear_fsi_map, partitioned_fsi


def test_converges_to_closed_form():
    """Zayıf kuplaj (b/k_s=0.5): hem Aitken hem sabit-ω kapalı-forma yakınsar."""
    a, b, k_s = 1.0, 0.5, 1.0
    x_exact = linear_fsi_exact(a, b, k_s)            # = 2.0
    x, info = partitioned_fsi(linear_fsi_map(a, b, k_s), x0=0.0)
    assert info["converged"] and abs(x.item() - x_exact) < 1e-7


def test_aitken_converges_where_fixed_diverges():
    """Salınımlı/güçlü kuplaj (b/k_s=−1.5): naif sabit-ω=1 IRAKSAR; Aitken YAKINSAR."""
    a, b, k_s = 1.0, -1.5, 1.0
    x_exact = linear_fsi_exact(a, b, k_s)            # = 0.4
    m = linear_fsi_map(a, b, k_s)
    x_ait, ia = partitioned_fsi(m, x0=0.0, aitken=True, max_iter=100)
    assert ia["converged"] and abs(x_ait.item() - x_exact) < 1e-7
    _, ifx = partitioned_fsi(m, x0=0.0, aitken=False, omega_fixed=1.0, max_iter=100)
    assert not ifx["converged"]                       # sabit-ω=1 ıraksar
    assert ia["iters"] < 15                            # Aitken hızlı (lineer → ~birkaç tur)


def test_vector_multidof():
    """Çok-DOF (vektör) arayüz: bağımsız iki mod, her biri kendi kapalı-formuna."""
    bs, ks = np.array([0.5, -1.2]), np.array([1.0, 1.0])
    a = np.array([1.0, 2.0])
    def m(x):
        return (a + bs * np.asarray(x)) / ks
    x_exact = a / (ks - bs)
    x, info = partitioned_fsi(m, x0=np.zeros(2), aitken=True)
    assert info["converged"]
    assert np.allclose(x, x_exact, atol=1e-7)


def test_residual_history_monotone_tail():
    """Aitken: artık geçmişi sonunda tol altına iner (yakınsama kaydı)."""
    a, b, k_s = 3.0, 0.8, 1.0
    _, info = partitioned_fsi(linear_fsi_map(a, b, k_s), x0=0.0)
    assert info["res_history"][-1] < 1e-9
    assert len(info["omega_history"]) >= 1
