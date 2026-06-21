"""Gerilme-farkında 3D TO — adjoint duyarlılık FD-kontrolü (gerilme-TO'nun kalbi) +
OC sağlık testi. Saf-NumPy/SciPy, ccx/CFD yok. stress_topopt2d testinin 3D ikizi."""
import numpy as np

from stress_topopt3d import StressTopo3D


def _cantilever(nelx=4, nely=3, nelz=2):
    def nid(i, j, k):
        return k * (nelx + 1) * (nely + 1) + j * (nelx + 1) + i
    fixed = []
    for k in range(nelz + 1):                       # i=0 kök yüzü tam ankastre
        for j in range(nely + 1):
            n = nid(0, j, k)
            fixed += [3 * n, 3 * n + 1, 3 * n + 2]
    tip = nid(nelx, nely, nelz)                      # uç köşe, -z yük
    return StressTopo3D(nelx, nely, nelz, fixed, [3 * tip + 2], [-1.0], rmin=1.5)


def test_compliance_gradient_matches_fd():
    t = _cantilever()
    x = 0.5 + 0.3 * np.random.default_rng(0).random(t.ne)
    rho = t.filt(x); u, _ = t.solve(rho)
    _, dc = t.compliance(rho, u); g = t._chain_filter(dc)
    h = 1e-6
    for e in (0, 5, 11, 17, 23):
        xp = x.copy(); xp[e] += h; xm = x.copy(); xm[e] -= h
        fp = t.compliance(t.filt(xp), t.solve(t.filt(xp))[0])[0]
        fm = t.compliance(t.filt(xm), t.solve(t.filt(xm))[0])[0]
        fd = (fp - fm) / (2 * h)
        assert abs(g[e] - fd) / (abs(fd) + 1e-30) < 1e-4


def test_pnorm_stress_gradient_matches_fd():
    # KRİTİK: 3D adjoint gerilme duyarlılığı doğru mu (gerilme-TO'nun en sık hata yeri)
    t = _cantilever()
    x = 0.5 + 0.3 * np.random.default_rng(1).random(t.ne)
    rho = t.filt(x); u, K = t.solve(rho)
    _, ds = t.pnorm_sens(rho, u, K); g = t._chain_filter(ds)
    h = 1e-6
    def spn(xv):
        r = t.filt(xv); uu, _ = t.solve(r)
        return t.pnorm_stress(r, uu)[0]
    for e in (0, 5, 11, 17, 23):
        xp = x.copy(); xp[e] += h; xm = x.copy(); xm[e] -= h
        fd = (spn(xp) - spn(xm)) / (2 * h)
        assert abs(g[e] - fd) / (abs(fd) + 1e-30) < 1e-4


def test_oc_respects_volume_and_runs():
    t = _cantilever(5, 4, 3)
    rho, hist = t.optimize(0.4, "stress", max_iter=10)
    assert abs(rho.mean() - 0.4) < 0.05
    assert np.isfinite(hist[-1]["peak_vm"])
    assert rho.min() >= 1e-3 - 1e-9 and rho.max() <= 1.0 + 1e-9
