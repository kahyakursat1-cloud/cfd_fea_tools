"""İki-yönlü (2-way) partitioned FSI çekirdeği — Aitken dinamik-relaksasyonlu sabit-nokta.

1-way coupling (coupling_fsi) basıncı tek seferde FEA'ya aktarır; 2-way'de yapı deformasyonu
akışı, akış basıncı yapıyı GÜNCELLER → akışkan↔yapı sabit-nokta iterasyonu. Güçlü kuplajda
(yapı esnek / dinamik-basınç yüksek) naif sabit-nokta IRAKSAR; **Aitken Δ² dinamik
relaksasyon** (Küttler & Wall 2008) yakınsatır — production FSI (preCICE, ANSYS) çekirdeği.

Bu modül GENEL iterasyon motorunu sağlar (map_fn: x → akışkan→yapı→yeni-x) ve kanonik
kapalı-form benchmark'ta doğrular. Ağır CFD↔FEA-geometri döngüsü ileride bu motora sarılır;
şimdilik algoritma + relaksasyon V&V'li. Statik aeroelastik diverjans eşi: fsi_aeroelastic.
Referans: Küttler & Wall (2008), *Fixed-point fluid–structure interaction solvers with
dynamic relaxation*, Comput. Mech. 43.
"""
from __future__ import annotations

import numpy as np


def partitioned_fsi(map_fn, x0, omega0=0.5, tol=1e-9, max_iter=200,
                    aitken=True, omega_fixed=None):
    """Partitioned sabit-nokta FSI: x* = map_fn(x*). map_fn bir kuplaj turudur
    (yapı-arayüzü x → akışkan çözümü → yapı çözümü → yeni arayüz x).

    Artık r_n = map_fn(x_n) − x_n. Güncelleme x_{n+1} = x_n + ω_n·r_n.
      aitken=True: ω_n Aitken Δ² ile dinamik (Küttler-Wall); güçlü kuplajda da yakınsar.
      aitken=False: sabit ω (omega_fixed veya omega0) — under-relaxation; büyük kuplajda ıraksar.
    Döner: (x*, {iters, converged, res_history, omega_history}).
    """
    x = np.atleast_1d(np.asarray(x0, float)).copy()
    omega = float(omega0)
    r_prev = None
    res_hist, om_hist = [], []
    converged = False
    for it in range(1, max_iter + 1):
        r = np.atleast_1d(np.asarray(map_fn(x), float)) - x
        rn = float(np.linalg.norm(r))
        res_hist.append(rn)
        if rn < tol:
            converged = True
            break
        if aitken and r_prev is not None:
            dr = r - r_prev
            denom = float(dr @ dr)
            if denom > 1e-30:
                omega = -omega * float(r_prev @ dr) / denom    # Aitken Δ²
            omega = float(np.clip(omega, -2.0, 2.0))            # güvenlik kemeri
        elif not aitken:
            omega = float(omega_fixed if omega_fixed is not None else omega0)
        om_hist.append(omega)
        x = x + omega * r
        r_prev = r
    return x, {"iters": it, "converged": converged,
               "res_history": res_hist, "omega_history": om_hist}


def linear_fsi_map(a, b, k_s):
    """Kanonik 1-DOF 2-way FSI kuplajı (kapalı-formlu doğrulama):
    aero kuvvet F(x)=a+b·x (deformasyona lineer bağlı — taşıma deflekte oldukça artar),
    yapı x=F/k_s. Kuplaj turu map(x)=(a+b·x)/k_s. Sabit nokta x*=a/(k_s−b).
    b/k_s→1 (güçlü kuplaj) naif sabit-noktayı ıraksatır; Aitken yakınsatır."""
    return lambda x: (a + b * np.asarray(x, float)) / k_s


def linear_fsi_exact(a, b, k_s):
    """Kapalı-form sabit nokta x* = a/(k_s − b) (k_s>b stabil yapı)."""
    return a / (k_s - b)
