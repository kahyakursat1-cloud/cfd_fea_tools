"""Stress-temelli TO doğrulaması — L-bracket benchmark (kanonik).
Kompliyans-min vs gerilme-min aynı hacimde. Beklenen (literatür, Le 2010): gerilme-min
reentrant köşedeki tepe von Mises'i DÜŞÜRÜR ve köşeyi yuvarlar (kompliyans-min sivri köşe
+ yüksek konsantrasyon bırakır). Doğrulama: peak_vm(stress) < peak_vm(compliance).
Kullanım: python experiments/stress_topopt_lbracket.py
"""
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from stress_topopt2d import StressTopo2D  # noqa: E402

N = 48
VF = 0.40


def build_lbracket():
    nelx = nely = N
    h = N // 2
    # Pasif boşluk: sağ-üst çeyrek (i>=h ve j>=h)
    passive = np.zeros(nelx * nely, bool)
    for j in range(nely):
        for i in range(nelx):
            if i >= h and j >= h:
                passive[j * nelx + i] = True
    # Ankastre: üst kenar, sol kol (y=N, x<=N/2)
    fixed = []
    jtop = nely
    for i in range(h + 1):
        n = jtop * (nelx + 1) + i
        fixed += [2 * n, 2 * n + 1]
    # Yük: alt-sağ kolun ucu (x=N, y=N/2) düşey aşağı
    nload = h * (nelx + 1) + nelx
    return StressTopo2D(nelx, nely, fixed, [2 * nload + 1], [-1.0],
                        rmin=2.0, passive_void=passive), passive


def peak_and_field(t, rho):
    u, _ = t.solve(rho)
    _, vm = t.elem_stress(u)
    eta = rho ** t.q * vm
    return float(eta.max()), eta


def main():
    t, passive = build_lbracket()
    print(f"L-bracket {N}x{N}, hacim={VF}, P={t.P}, pasif boşluk={passive.sum()} eleman",
          flush=True)

    rho_c, hist_c = t.optimize(VF, "compliance", max_iter=70)
    peak_c, _ = peak_and_field(t, rho_c)
    print(f"Kompliyans-min: peak η_vm={peak_c:.4f}, iter={len(hist_c)}", flush=True)

    rho_s, hist_s = t.optimize(VF, "stress", max_iter=70)
    peak_s, _ = peak_and_field(t, rho_s)
    print(f"Gerilme-min:    peak η_vm={peak_s:.4f}, iter={len(hist_s)}", flush=True)

    redux = (peak_c - peak_s) / peak_c * 100
    print(f"Tepe-gerilme azalması: %{redux:.1f}", flush=True)

    # Figür: iki yoğunluk alanı yan yana
    fig, ax = plt.subplots(1, 2, figsize=(9, 4.5))
    for a, rho, ttl, pk in ((ax[0], rho_c, "Kompliyans-min", peak_c),
                            (ax[1], rho_s, "Gerilme-min", peak_s)):
        img = rho.reshape(N, N)
        img = np.ma.masked_where(passive.reshape(N, N), img)
        a.imshow(img, cmap="gray_r", origin="lower", vmin=0, vmax=1)
        a.set_title(f"{ttl}\npeak η_vm={pk:.3f}"); a.axis("off")
    fig.suptitle(f"L-bracket stress-aware TO — tepe-gerilme %{redux:.0f} düştü")
    fig.tight_layout()
    out_png = HERE.parent / "stress_topopt_lbracket.png"
    fig.savefig(out_png, dpi=150); plt.close(fig)

    rec = {
        "vaka": "L-bracket stress-temelli TO (kompliyans-min vs gerilme-min, aynı hacim)",
        "yontem": f"2D plane-stress Q4 SIMP, P-norm(P={t.P}) von Mises, qp-relaks(q={t.q}), "
                  "adjoint duyarlılık (FD-kontrollü), OC. ccx/CFD YOK — kendi-içinde.",
        "grid": N, "volfrac": VF,
        "peak_eta_vm_compliance": round(peak_c, 4),
        "peak_eta_vm_stress": round(peak_s, 4),
        "tepe_azalma_pct": round(redux, 1),
        "sonuc": ("GECTI — gerilme-min tepe von Mises'i düşürdü (reentrant köşe yuvarlandı)."
                  if redux > 5 else "BEKLENMEDIK — gerilme-min azaltmadı (incele)"),
        "_not": ("Doğrulama #1 (adjoint gradyanı FD ile ~1e-7): test_stress_topopt2d. "
                 "Üretim: python experiments/stress_topopt_lbracket.py. Figür: "
                 "stress_topopt_lbracket.png"),
    }
    (HERE.parent / "stress_topopt_lbracket.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print("SONUC:", rec["sonuc"], flush=True)
    return 0 if redux > 5 else 2


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
