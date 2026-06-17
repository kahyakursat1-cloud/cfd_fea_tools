"""Statik aeroelastik FSI — burulma diverjansı (kendi-içinde, analitik-doğrulanabilir).

Tam OpenFOAM-FSI ağır + canlı CFD ister; bu modül PARTİSYONLU FSI metodolojisini
(akışkan↔yapı sabit-nokta iterasyonu) kanonik bir benchmark'ta gösterir + doğrular:
üniform kanat BURULMA DİVERJANSI. Kapalı-form: q_div = (π/2L)²·GJ/(c·e·CLα).

Yapı: 1B burulma FE (GJ), kök ankastre. Akışkan (indirgenmiş, quasi-steady thin-airfoil):
EA etrafında dağıtık moment t(y) = q·c·e·CLα·(α0+θ(y)) — pozitif geri-besleme → diverjans.
Kuple sistem: (K − q·k·M)θ = q·k·α0·f,  k=c·e·CLα. FSI iterasyonu q<q_div'de yakınsar,
q>q_div'de ıraksar (ρ(K⁻¹·qkM)<1 ⟺ q<q_div). Doğrulama: FE q_div ↔ analitik; iteratif
çözüm ↔ doğrudan ↔ analitik sec-büyütme; ıraksama eşiği ↔ q_div.
Referans: Bisplinghoff & Ashley, *Aeroelasticity*; Fung, *An Introduction to Aeroelasticity*.
"""
from __future__ import annotations

import numpy as np


class TorsionalDivergence:
    """Üniform kanat burulma diverjansı — 1B FE + partisyonlu FSI."""

    def __init__(self, GJ=1.0e4, L=2.0, c=1.0, e=0.1, CLalpha=2 * np.pi,
                 alpha0_deg=2.0, n=40):
        self.GJ, self.L, self.c, self.e, self.CLa = GJ, L, c, e, CLalpha
        self.alpha0 = np.radians(alpha0_deg)
        self.n = n
        self.k = c * e * CLalpha                 # aero kuplaj katsayısı
        self.le = L / n
        self.K, self.M, self.f = self._assemble()   # serbest DOF (kök hariç)

    @property
    def q_div_analytic(self) -> float:
        return (np.pi / (2 * self.L)) ** 2 * self.GJ / self.k

    def _assemble(self):
        n = self.n
        Kf = np.zeros((n + 1, n + 1)); Mf = np.zeros((n + 1, n + 1))
        ff = np.zeros(n + 1)
        ke = self.GJ / self.le * np.array([[1.0, -1], [-1, 1]])
        me = self.le / 6 * np.array([[2.0, 1], [1, 2]])
        for i in range(n):
            sl = slice(i, i + 2)
            Kf[sl, sl] += ke
            Mf[sl, sl] += me
            ff[i] += self.le / 2
            ff[i + 1] += self.le / 2
        free = slice(1, n + 1)                    # kök düğüm 0 ankastre (θ=0)
        return Kf[free, free], Mf[free, free], ff[free]

    def q_div_fe(self) -> float:
        from scipy.linalg import eigh
        w = eigh(self.K, self.M, eigvals_only=True)
        return float(w.min()) / self.k           # μ_min/k

    def solve_direct(self, q: float) -> np.ndarray:
        """θ(y) doğrudan: (K − q k M)θ = q k α0 f."""
        A = self.K - q * self.k * self.M
        return np.linalg.solve(A, q * self.k * self.alpha0 * self.f)

    def solve_fsi(self, q: float, omega=0.6, tol=1e-9, max_iter=2000):
        """PARTİSYONLU FSI sabit-nokta: θ⁺ = (1−ω)θ + ω K⁻¹[qk(Mθ + α0 f)].
        Döndür: (θ, iterasyon, yakınsadı_mı, tip_twist_tarihçesi)."""
        Kinv_rhs = np.linalg.solve  # closure
        theta = np.zeros(self.n)
        hist = []
        diverged = False
        for it in range(1, max_iter + 1):
            load = q * self.k * (self.M @ theta + self.alpha0 * self.f)   # AKIŞKAN
            theta_struct = Kinv_rhs(self.K, load)                          # YAPI
            theta_new = (1 - omega) * theta + omega * theta_struct
            tip = float(theta_new[-1])
            hist.append(tip)
            if not np.isfinite(tip) or abs(tip) > 1e6:
                diverged = True; break
            if np.max(np.abs(theta_new - theta)) < tol:
                theta = theta_new; break
            theta = theta_new
        converged = (not diverged) and it < max_iter
        return theta, it, converged, hist

    def tip_twist_analytic(self, q: float) -> float:
        """Analitik uç-burulması: θ_tip = α0 (sec(λL) − 1), λL=(π/2)√(q/q_div)."""
        lamL = (np.pi / 2) * np.sqrt(q / self.q_div_analytic)
        return self.alpha0 * (1.0 / np.cos(lamL) - 1.0)
