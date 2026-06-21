"""Gerilme-farkında 3D topoloji optimizasyonu (stress-aware SIMP) — kendi-içinde, doğrulanabilir.

stress_topopt2d'nin 3D ikizi. Üretim vehicle_topopt ccx-tabanlı + SADECE kompliyans →
yüksek-gerilme (akma aşan) tasarım üretebilir. Bu modül adjoint P-norm von Mises stress-TO'yu
3D'ye taşır: H8 (8-düğüm hex) yapısal grid, Python'da assemble (ccx kara-kutusu adjoint'e izin
vermez), P-norm vM (6 bileşen), qp-relaks, ADJOINT duyarlılık. Doğrulama: adjoint gradyanı
sonlu-farkla uyumlu (gerilme-TO'nun en kritik testi) — tests/test_stress_topopt3d.py.

Çekirdek: 3D izotropik H8, E=1 normalize. SIMP: E_e=Emin+ρ^p(1-Emin). Gerilme (qp-relaks):
η_e=ρ_e^q·σ_vm(D0·B·u_e). P-norm: σ_PN=(Σ η_e^P)^(1/P). OC döngüsü.
Referans: Le et al. 2010; Bruggi 2008 (qp); 3D SIMP (Liu & Tovar 2014, top3d).
"""
from __future__ import annotations

import numpy as np

_G = 1.0 / np.sqrt(3.0)
# H8 köşe doğal-koordinatları (düğüm sırası 1-8: alt yüz CCW, üst yüz CCW)
_NODES = np.array([(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                   (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], float)
_GP = [(x, y, z) for z in (-_G, _G) for y in (-_G, _G) for x in (-_G, _G)]

# 3D von Mises matrisi (s=[xx,yy,zz,xy,yz,zx]): σvm²=s^T V s
_VM = np.array([[1, -0.5, -0.5, 0, 0, 0], [-0.5, 1, -0.5, 0, 0, 0],
                [-0.5, -0.5, 1, 0, 0, 0], [0, 0, 0, 3, 0, 0],
                [0, 0, 0, 0, 3, 0], [0, 0, 0, 0, 0, 3]], float)


def _D0(nu: float) -> np.ndarray:
    c = 1.0 / ((1 + nu) * (1 - 2 * nu))
    g = (1 - 2 * nu) / 2
    return c * np.array([[1 - nu, nu, nu, 0, 0, 0], [nu, 1 - nu, nu, 0, 0, 0],
                         [nu, nu, 1 - nu, 0, 0, 0], [0, 0, 0, g, 0, 0],
                         [0, 0, 0, 0, g, 0], [0, 0, 0, 0, 0, g]])


def _B(xi, eta, zeta):
    """Birim-küp H8 strain-displacement (6×24). J=diag(1/2) → dN/dx=2 dN/dξ, detJ=1/8."""
    x0, y0, z0 = _NODES[:, 0], _NODES[:, 1], _NODES[:, 2]
    dNxi = x0 * (1 + eta * y0) * (1 + zeta * z0) / 8
    dNeta = y0 * (1 + xi * x0) * (1 + zeta * z0) / 8
    dNzeta = z0 * (1 + xi * x0) * (1 + eta * y0) / 8
    dNx, dNy, dNz = 2 * dNxi, 2 * dNeta, 2 * dNzeta
    B = np.zeros((6, 24))
    B[0, 0::3] = dNx
    B[1, 1::3] = dNy
    B[2, 2::3] = dNz
    B[3, 0::3] = dNy; B[3, 1::3] = dNx
    B[4, 1::3] = dNz; B[4, 2::3] = dNy
    B[5, 0::3] = dNz; B[5, 2::3] = dNx
    return B


def _KE(nu):
    D = _D0(nu)
    KE = np.zeros((24, 24))
    for xi, eta, zeta in _GP:                      # 2x2x2 Gauss, w=1, detJ=1/8
        B = _B(xi, eta, zeta)
        KE += B.T @ D @ B * 0.125
    return KE


class StressTopo3D:
    """3D yapısal grid (nelx×nely×nelz H8); OC ile kompliyans- veya gerilme-min."""

    def __init__(self, nelx, nely, nelz, fixed_dofs, load_dofs, load_vals,
                 nu=0.3, penal=3.0, q=0.5, rmin=1.5, emin=1e-6, pnorm=8.0,
                 passive_void=None):
        self.nelx, self.nely, self.nelz, self.nu = nelx, nely, nelz, nu
        self.penal, self.q, self.emin, self.P = penal, q, emin, pnorm
        self.ne = nelx * nely * nelz
        self.nn = (nelx + 1) * (nely + 1) * (nelz + 1)
        self.ndof = 3 * self.nn
        self.KE = _KE(nu)
        self.DB = _D0(nu) @ _B(0.0, 0.0, 0.0)      # 6×24 merkez gerilme geri-kazanımı
        self.edof = self._edof()
        self.fixed = np.asarray(fixed_dofs, int)
        self.free = np.setdiff1d(np.arange(self.ndof), self.fixed)
        self.f = np.zeros(self.ndof)
        self.f[np.asarray(load_dofs, int)] = load_vals
        self.passive = (np.zeros(self.ne, bool) if passive_void is None
                        else np.asarray(passive_void, bool))
        self._build_filter(rmin)

    def _nid(self, i, j, k):
        return k * (self.nelx + 1) * (self.nely + 1) + j * (self.nelx + 1) + i

    def _eid(self, i, j, k):
        return k * self.nelx * self.nely + j * self.nelx + i

    def _edof(self):
        ed = np.zeros((self.ne, 24), int)
        for k in range(self.nelz):
            for j in range(self.nely):
                for i in range(self.nelx):
                    n = [self._nid(i, j, k), self._nid(i + 1, j, k),
                         self._nid(i + 1, j + 1, k), self._nid(i, j + 1, k),
                         self._nid(i, j, k + 1), self._nid(i + 1, j, k + 1),
                         self._nid(i + 1, j + 1, k + 1), self._nid(i, j + 1, k + 1)]
                    dofs = []
                    for nn in n:
                        dofs += [3 * nn, 3 * nn + 1, 3 * nn + 2]
                    ed[self._eid(i, j, k)] = dofs
        return ed

    def _build_filter(self, rmin):
        from scipy.sparse import csr_matrix
        from scipy.spatial import cKDTree
        coords = np.array([[i + 0.5, j + 0.5, k + 0.5]
                           for k in range(self.nelz) for j in range(self.nely)
                           for i in range(self.nelx)])
        tree = cKDTree(coords)
        rows, cols, vals = [], [], []
        for e, nb in enumerate(tree.query_ball_point(coords, rmin)):
            for nn in nb:
                w = rmin - np.linalg.norm(coords[e] - coords[nn])
                if w > 0:
                    rows.append(e); cols.append(nn); vals.append(w)
        self.H = csr_matrix((vals, (rows, cols)), shape=(self.ne, self.ne))
        self.Hs = np.asarray(self.H.sum(axis=1)).ravel()

    def filt(self, x):
        return (self.H @ x) / self.Hs

    def _assemble(self, rho):
        from scipy.sparse import csr_matrix
        E = self.emin + rho ** self.penal * (1.0 - self.emin)
        ne576 = self.ne * 576
        I = np.zeros(ne576, int); J = np.zeros(ne576, int); V = np.zeros(ne576)
        ke = self.KE.ravel()
        for e in range(self.ne):
            ed = self.edof[e]
            idx = slice(e * 576, e * 576 + 576)
            I[idx] = np.repeat(ed, 24)
            J[idx] = np.tile(ed, 24)
            V[idx] = ke * E[e]
        return csr_matrix((V, (I, J)), shape=(self.ndof, self.ndof))

    def _lin_solve(self, Kff, rhs):
        """SPD K_ff için CG (Jacobi ön-koşullu). 3D doğrudan-çözücü (SuperLU) fill-in
        malloc'undan kaçınır; bellek-hafif, büyük 3D'ye ölçeklenir. rtol≈machine → adjoint
        gradyanı sonlu-farkla uyumlu kalır (test_stress_topopt3d doğrular)."""
        from scipy.sparse.linalg import LinearOperator, cg
        d = Kff.diagonal().copy()
        d[d == 0] = 1.0
        M = LinearOperator(Kff.shape, matvec=lambda v: v / d)
        x, _ = cg(Kff, rhs, rtol=1e-11, atol=0.0, M=M, maxiter=50000)
        return x

    def solve(self, rho):
        K = self._assemble(rho)
        u = np.zeros(self.ndof)
        u[self.free] = self._lin_solve(K[self.free][:, self.free].tocsr(), self.f[self.free])
        return u, K

    def elem_stress(self, u):
        s = u[self.edof] @ self.DB.T                # (ne,6) = D0 B u_e (merkez)
        vm = np.sqrt(np.einsum("ei,ij,ej->e", s, _VM, s) + 1e-30)
        return s, vm

    def pnorm_stress(self, rho, u):
        _, vm = self.elem_stress(u)
        eta = rho ** self.q * vm
        return (np.sum(eta ** self.P)) ** (1.0 / self.P), vm, eta

    def compliance(self, rho, u):
        ce = np.einsum("ei,ij,ej->e", u[self.edof], self.KE, u[self.edof])
        E = self.emin + rho ** self.penal * (1 - self.emin)
        c = float(E @ ce)
        dc = -self.penal * rho ** (self.penal - 1) * (1 - self.emin) * ce
        return c, dc

    def pnorm_sens(self, rho, u, K):
        """dσ_PN/dρ (filtrelenmiş ρ uzayı) — adjoint (Le 2010 türevi, 3D)."""
        s, vm = self.elem_stress(u)
        eta = rho ** self.q * vm
        spn = (np.sum(eta ** self.P)) ** (1.0 / self.P)
        dpn_deta = spn ** (1 - self.P) * eta ** (self.P - 1)
        rho_s = np.maximum(rho, 1e-3)
        dexpl = dpn_deta * self.q * rho_s ** (self.q - 1) * vm
        dpn_dvm = dpn_deta * rho ** self.q
        coef = dpn_dvm / vm
        VMs = s @ _VM.T                              # (ne,6) = VM s
        due = (VMs @ self.DB) * coef[:, None]        # (ne,24) ∂σ_PN/∂u_e
        dPN_du = np.zeros(self.ndof)
        np.add.at(dPN_du, self.edof, due)
        lam = np.zeros(self.ndof)
        lam[self.free] = self._lin_solve(K[self.free][:, self.free].tocsr(), dPN_du[self.free])
        Ue, Le = u[self.edof], lam[self.edof]
        dKu = self.penal * rho ** (self.penal - 1) * (1 - self.emin)
        dimpl = -dKu * np.einsum("ei,ij,ej->e", Le, self.KE, Ue)
        return spn, dexpl + dimpl

    def _chain_filter(self, dobj_drho):
        return self.H.T @ (dobj_drho / self.Hs)

    def optimize(self, volfrac, objective="stress", max_iter=60, move=0.2, tol=0.01,
                 x0=None):
        # x0: warm-start (Le 2010 — stress-min kompliyans-tasarımdan başlar; OC stress'te
        # tek-başına kararsız/salınımlı, iyi topoloji başlangıcı şart).
        x = np.full(self.ne, volfrac) if x0 is None else np.clip(x0.copy(), 1e-3, 1.0)
        x[self.passive] = self.emin
        hist = []
        for it in range(1, max_iter + 1):
            rho = self.filt(x)
            rho[self.passive] = self.emin
            u, K = self.solve(rho)
            if objective == "compliance":
                obj, drho = self.compliance(rho, u)
            else:
                obj, drho = self.pnorm_sens(rho, u, K)
            _, vm = self.elem_stress(u)
            peak_vm = float((rho ** self.q * vm).max())
            xnew = self._oc_step(x, self._chain_filter(drho), volfrac, move)
            ch = float(np.abs(xnew - x).max())
            x = xnew
            hist.append({"it": it, "obj": float(obj), "peak_vm": peak_vm, "ch": ch})
            if ch < tol and it > 5:
                break
        rho = self.filt(x); rho[self.passive] = self.emin
        return rho, hist

    def _oc_step(self, x, dx, volfrac, move):
        l1, l2 = 1e-9, 1e9
        act = ~self.passive
        target = volfrac * self.ne
        xn = x.copy()
        while (l2 - l1) / (l1 + l2) > 1e-3:
            lmid = 0.5 * (l1 + l2)
            be = np.maximum(-dx, 0) / lmid
            cand = np.clip(x * np.sqrt(be), np.maximum(x - move, 1e-3),
                           np.minimum(x + move, 1.0))
            cand[self.passive] = self.emin
            if cand[act].sum() > target:
                l1 = lmid
            else:
                l2 = lmid
            xn = cand
        return xn
