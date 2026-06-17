"""Gerilme-temelli 2D topoloji optimizasyonu (stress-aware SIMP) — kendi-içinde, doğrulanabilir.

Mevcut vehicle_topopt SADECE kompliyans minimize eder → tasarım yüksek gerilme
konsantrasyonu içerebilir (akma aşar, kırılır). Bu modül gerilme-FARKINDA TO'yu
gösterir + doğrular: P-norm von Mises agregasyonu, qp-relaksasyon (tekillik önleme),
ADJOINT duyarlılık. Doğrulama: (1) adjoint gradyanı sonlu-fark ile uyumlu (sensitivity
check — gerilme-TO'nun en kritik doğrulaması), (2) L-bracket benchmark'ında stress-min
tepe-gerilmeyi kompliyans-min'e göre düşürür ve reentrant köşeyi yuvarlar (literatür).

Çekirdek: 2D plane-stress Q4, E=1 normalize. SIMP: E_e=Emin+ρ^p(1-Emin). Gerilme
(qp-relaks): η_e = ρ_e^q · σ_vm(D0·B·u_e). P-norm: σ_PN=(Σ η_e^P)^(1/P). OC döngüsü.
Referans: Le et al. 2010 (Struct Multidisc Optim); Bruggi 2008 (qp-relaksasyon).
"""
from __future__ import annotations

import numpy as np

# ── Eleman çekirdeği (birim-kare Q4, plane-stress, E=1) ──────────────────────
_GP = [(-1 / np.sqrt(3), -1 / np.sqrt(3)), (1 / np.sqrt(3), -1 / np.sqrt(3)),
       (1 / np.sqrt(3), 1 / np.sqrt(3)), (-1 / np.sqrt(3), 1 / np.sqrt(3))]


def _D0(nu: float) -> np.ndarray:
    return 1.0 / (1 - nu ** 2) * np.array(
        [[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])


def _B(xi: float, eta: float) -> np.ndarray:
    # dN/dnatural; phys = unit square, dN/dx = 2 dN/dxi
    dNxi = np.array([-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)]) / 4
    dNeta = np.array([-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)]) / 4
    dNx, dNy = 2 * dNxi, 2 * dNeta            # detJ=1/4, J=diag(1/2)
    B = np.zeros((3, 8))
    B[0, 0::2] = dNx
    B[1, 1::2] = dNy
    B[2, 0::2] = dNy
    B[2, 1::2] = dNx
    return B


def _KE(nu: float) -> np.ndarray:
    D = _D0(nu)
    KE = np.zeros((8, 8))
    for xi, eta in _GP:                        # 2x2 Gauss, w=1, detJ=1/4
        B = _B(xi, eta)
        KE += B.T @ D @ B * 0.25
    return KE


_VM = np.array([[1.0, -0.5, 0], [-0.5, 1.0, 0], [0, 0, 3.0]])   # von Mises matrisi


class StressTopo2D:
    """Plane-stress dikdörtgen tasarım alanı; OC ile kompliyans- veya gerilme-min."""

    def __init__(self, nelx, nely, fixed_dofs, load_dofs, load_vals,
                 nu=0.3, penal=3.0, q=0.5, rmin=1.5, emin=1e-6, pnorm=8.0,
                 passive_void=None):
        self.nelx, self.nely, self.nu = nelx, nely, nu
        self.penal, self.q, self.emin, self.P = penal, q, emin, pnorm
        self.ne = nelx * nely
        self.ndof = 2 * (nelx + 1) * (nely + 1)
        self.KE = _KE(nu)
        self.D0 = _D0(nu)
        self.Bc = _B(0.0, 0.0)                 # merkez B (gerilme geri-kazanımı)
        self.DB = self.D0 @ self.Bc            # 3x8
        self.edof = self._edof()
        self.fixed = np.asarray(fixed_dofs, int)
        self.free = np.setdiff1d(np.arange(self.ndof), self.fixed)
        self.f = np.zeros(self.ndof)
        self.f[np.asarray(load_dofs, int)] = load_vals
        self.passive = (np.zeros(self.ne, bool) if passive_void is None
                        else np.asarray(passive_void, bool))
        self._build_filter(rmin)

    def _eid(self, i, j):
        return j * self.nelx + i

    def _edof(self):
        ed = np.zeros((self.ne, 8), int)
        for j in range(self.nely):
            for i in range(self.nelx):
                n1 = j * (self.nelx + 1) + i
                n2 = n1 + 1
                n3 = (j + 1) * (self.nelx + 1) + i + 1
                n4 = n3 - 1
                ed[self._eid(i, j)] = [2 * n1, 2 * n1 + 1, 2 * n2, 2 * n2 + 1,
                                       2 * n3, 2 * n3 + 1, 2 * n4, 2 * n4 + 1]
        return ed

    def _build_filter(self, rmin):
        # yoğunluk filtresi (konik ağırlık) — checkerboard + mesh-bağımlılık önleme
        coords = np.array([[i + 0.5, j + 0.5] for j in range(self.nely)
                           for i in range(self.nelx)])
        from scipy.spatial import cKDTree
        tree = cKDTree(coords)
        rows, cols, vals = [], [], []
        for e, nb in enumerate(tree.query_ball_point(coords, rmin)):
            for n in nb:
                w = rmin - np.linalg.norm(coords[e] - coords[n])
                if w > 0:
                    rows.append(e); cols.append(n); vals.append(w)
        from scipy.sparse import csr_matrix
        H = csr_matrix((vals, (rows, cols)), shape=(self.ne, self.ne))
        self.H = H
        self.Hs = np.asarray(H.sum(axis=1)).ravel()

    def filt(self, x):
        return (self.H @ x) / self.Hs

    # ── FE çözümü ────────────────────────────────────────────────────────────
    def _assemble(self, rho):
        from scipy.sparse import csr_matrix
        E = self.emin + rho ** self.penal * (1.0 - self.emin)
        ne8 = self.ne * 64
        I = np.zeros(ne8, int); J = np.zeros(ne8, int); V = np.zeros(ne8)
        ke = self.KE.ravel()
        for e in range(self.ne):
            ed = self.edof[e]
            idx = slice(e * 64, e * 64 + 64)
            I[idx] = np.repeat(ed, 8)
            J[idx] = np.tile(ed, 8)
            V[idx] = ke * E[e]
        K = csr_matrix((V, (I, J)), shape=(self.ndof, self.ndof))
        return K

    def solve(self, rho):
        from scipy.sparse.linalg import spsolve
        K = self._assemble(rho)
        u = np.zeros(self.ndof)
        Kff = K[self.free][:, self.free]
        u[self.free] = spsolve(Kff.tocsc(), self.f[self.free])
        return u, K

    # ── Gerilme (qp-relakse) + P-norm ─────────────────────────────────────────
    def elem_stress(self, u):
        """σ_vm,e (mikroskopik, E0) ve relakse η_e = ρ^q σ_vm. u global."""
        Ue = u[self.edof]                       # (ne,8)
        s = Ue @ self.DB.T                       # (ne,3) = D0 B u_e
        vm = np.sqrt(np.einsum("ei,ij,ej->e", s, _VM, s) + 1e-30)
        return s, vm

    def pnorm_stress(self, rho, u):
        _, vm = self.elem_stress(u)
        eta = rho ** self.q * vm
        return (np.sum(eta ** self.P)) ** (1.0 / self.P), vm, eta

    # ── Hedef + adjoint duyarlılık ────────────────────────────────────────────
    def compliance(self, rho, u):
        ce = np.einsum("ei,ij,ej->e", u[self.edof], self.KE, u[self.edof])
        E = self.emin + rho ** self.penal * (1 - self.emin)
        c = float(E @ ce)
        dc = -self.penal * rho ** (self.penal - 1) * (1 - self.emin) * ce
        return c, dc

    def pnorm_sens(self, rho, u, K):
        """dσ_PN/dρ (filtrelenmiş ρ uzayında) — adjoint. Le 2010 türevi."""
        from scipy.sparse.linalg import spsolve
        s, vm = self.elem_stress(u)
        eta = rho ** self.q * vm
        spn = (np.sum(eta ** self.P)) ** (1.0 / self.P)
        # ∂σ_PN/∂η_e
        dpn_deta = spn ** (1 - self.P) * eta ** (self.P - 1)
        # explicit: ∂η_e/∂ρ_e = q ρ^(q-1) vm  (ρ-floor: q<1'de ρ→0'da ıraksamayı önle)
        rho_s = np.maximum(rho, 1e-3)
        dexpl = dpn_deta * self.q * rho_s ** (self.q - 1) * vm
        # ∂σ_PN/∂u : η_e = ρ^q vm,  ∂vm/∂u_e = (1/vm)(DB)^T VM (DB) u_e
        # ∂σ_PN/∂σ_vm,e = dpn_deta * ρ^q
        dpn_dvm = dpn_deta * rho ** self.q                # (ne,)
        coef = dpn_dvm / vm                                # (ne,)
        VMs = s @ _VM.T                                    # (ne,3) = VM s
        due = (VMs @ self.DB) * coef[:, None]              # (ne,8) ∂σ_PN/∂u_e
        dPN_du = np.zeros(self.ndof)
        np.add.at(dPN_du, self.edof, due)
        # adjoint: K λ = ∂σ_PN/∂u  (sadece serbest dof)
        lam = np.zeros(self.ndof)
        Kff = K[self.free][:, self.free].tocsc()
        lam[self.free] = spsolve(Kff, dPN_du[self.free])
        # implicit: -λ^T (∂K/∂ρ_e) u ; ∂K_e/∂ρ_e = p ρ^(p-1)(1-emin) KE
        Ue = u[self.edof]; Le = lam[self.edof]
        dKu = self.penal * rho ** (self.penal - 1) * (1 - self.emin)
        dimpl = -dKu * np.einsum("ei,ij,ej->e", Le, self.KE, Ue)
        return spn, dexpl + dimpl

    def _chain_filter(self, dobj_drho):
        # ρ = H x / Hs  →  dobj/dx = H^T (dobj/dρ / Hs)
        return self.H.T @ (dobj_drho / self.Hs)

    # ── OC döngüsü ────────────────────────────────────────────────────────────
    def optimize(self, volfrac, objective="stress", max_iter=80, move=0.2, tol=0.01):
        x = np.full(self.ne, volfrac)
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
            dx = self._chain_filter(drho)
            xnew = self._oc_step(x, dx, volfrac, move)
            ch = float(np.abs(xnew - x).max())
            x = xnew
            hist.append({"it": it, "obj": float(obj), "peak_vm": peak_vm, "ch": ch})
            if ch < tol and it > 5:
                break
        rho = self.filt(x); rho[self.passive] = self.emin
        return rho, hist

    def _oc_step(self, x, dx, volfrac, move):
        # OC: min obj s.t. hacim. dx>0 (obj artıyor) → Be<0 olur; max(0,...) ile kırp.
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
