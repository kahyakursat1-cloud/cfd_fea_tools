"""Gerilme-temelli 2D TO — adjoint duyarlılık FD-kontrolü (gerilme-TO'nun kalbi) +
OC sağlık testi. Saf-NumPy/SciPy, ccx/CFD yok."""
import numpy as np

from stress_topopt2d import StressTopo2D


def _cantilever(nelx=5, nely=4):
    fixed = ([2 * (j * (nelx + 1)) for j in range(nely + 1)]
             + [2 * (j * (nelx + 1)) + 1 for j in range(nely + 1)])
    load = [2 * nelx + 1]                       # sağ-alt düğüm düşey
    return StressTopo2D(nelx, nely, fixed, load, [-1.0], rmin=1.5)


def test_compliance_gradient_matches_fd():
    t = _cantilever()
    x = 0.5 + 0.3 * np.random.default_rng(0).random(t.ne)
    rho = t.filt(x); u, _ = t.solve(rho)
    _, dc = t.compliance(rho, u); g = t._chain_filter(dc)
    h = 1e-6
    for e in (0, 7, 12, 18):
        xp = x.copy(); xp[e] += h; xm = x.copy(); xm[e] -= h
        fp = t.compliance(t.filt(xp), t.solve(t.filt(xp))[0])[0]
        fm = t.compliance(t.filt(xm), t.solve(t.filt(xm))[0])[0]
        fd = (fp - fm) / (2 * h)
        assert abs(g[e] - fd) / (abs(fd) + 1e-30) < 1e-4


def test_pnorm_stress_gradient_matches_fd():
    # KRİTİK: adjoint gerilme duyarlılığı doğru mu (gerilme-TO'nun en sık hata yeri)
    t = _cantilever()
    x = 0.5 + 0.3 * np.random.default_rng(1).random(t.ne)
    rho = t.filt(x); u, K = t.solve(rho)
    _, ds = t.pnorm_sens(rho, u, K); g = t._chain_filter(ds)
    h = 1e-6
    def spn(xv):
        r = t.filt(xv); uu, _ = t.solve(r)
        return t.pnorm_stress(r, uu)[0]
    for e in (0, 7, 12, 18):
        xp = x.copy(); xp[e] += h; xm = x.copy(); xm[e] -= h
        fd = (spn(xp) - spn(xm)) / (2 * h)
        assert abs(g[e] - fd) / (abs(fd) + 1e-30) < 1e-4


def test_oc_respects_volume_and_runs():
    t = _cantilever(8, 6)
    rho, hist = t.optimize(0.4, "stress", max_iter=12)
    assert abs(rho.mean() - 0.4) < 0.05          # hacim kısıtı tutuldu
    assert np.isfinite(hist[-1]["peak_vm"])       # nan yok (relaks-floor çalışıyor)
    assert rho.min() >= 1e-3 - 1e-9 and rho.max() <= 1.0 + 1e-9
