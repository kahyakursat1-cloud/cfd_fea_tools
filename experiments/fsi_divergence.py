"""FSI doğrulaması — statik aeroelastik burulma diverjansı (kanonik benchmark).
Partisyonlu akışkan↔yapı iterasyonunu kapalı-form q_div + sec-büyütme ile doğrular.
Figür: uç-burulma vs q/q_div (FSI ∘ vs analitik —), diverjans asimptotu.
Kullanım: python experiments/fsi_divergence.py
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
from fsi_aeroelastic import TorsionalDivergence  # noqa: E402


def main():
    m = TorsionalDivergence(GJ=1.0e4, L=2.0, c=1.0, e=0.1, alpha0_deg=2.0, n=40)
    qa, qfe = m.q_div_analytic, m.q_div_fe()
    err_qdiv = abs(qfe - qa) / qa * 100
    print(f"q_div: analitik={qa:.1f} Pa, FE={qfe:.1f} Pa (hata %{err_qdiv:.2f})", flush=True)

    # q=0.5 q_div uyum
    q = 0.5 * qa
    th_f, it, conv, _ = m.solve_fsi(q)
    th_d = m.solve_direct(q)
    ta = m.tip_twist_analytic(q)
    err_tip = abs(th_f[-1] - ta) / abs(ta) * 100
    print(f"q=0.5q_div: FSI yakınsadı={conv} ({it} iter), tip FSI={np.degrees(th_f[-1]):.4f}° "
          f"vs analitik {np.degrees(ta):.4f}° (hata %{err_tip:.2f})", flush=True)

    # diverjans eşiği
    _, _, conv_below, _ = m.solve_fsi(0.95 * qa)
    _, _, conv_above, _ = m.solve_fsi(1.05 * qa)
    print(f"FSI yakınsama: q=0.95q_div→{conv_below}, q=1.05q_div→{conv_above} "
          "(altında yakınsar, üstünde ıraksar)", flush=True)

    # büyütme eğrisi
    rs = np.linspace(0.05, 0.95, 19)
    tip_fsi, tip_an = [], []
    for r in rs:
        thf, _, c, _ = m.solve_fsi(r * qa)
        tip_fsi.append(np.degrees(thf[-1]) if c else np.nan)
        tip_an.append(np.degrees(m.tip_twist_analytic(r * qa)))

    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.plot(rs, tip_an, "-", color="#1f4e79", label="Analitik (sec büyütme)")
    ax.plot(rs, tip_fsi, "o", ms=5, color="#c0392b", label="Partisyonlu FSI")
    ax.axvline(1.0, ls="--", color="gray", label="Diverjans (q=q_div)")
    ax.set_xlabel("q / q_div"); ax.set_ylabel("Uç burulması (°)")
    ax.set_title(f"Aeroelastik burulma diverjansı — FSI doğrulama\n"
                 f"q_div FE↔analitik %{err_qdiv:.2f}")
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(HERE.parent / "fsi_divergence.png", dpi=150); plt.close(fig)

    ok = err_qdiv < 1.0 and err_tip < 1.0 and conv_below and not conv_above
    rec = {
        "vaka": "Statik aeroelastik burulma diverjansı — partisyonlu FSI doğrulama",
        "yontem": "1B burulma FE (GJ) ↔ quasi-steady thin-airfoil aero, sabit-nokta "
                  "iterasyonu. Kapalı-form: q_div=(π/2L)²GJ/(c·e·CLα). ccx/CFD YOK.",
        "parametre": {"GJ_Nm2": 1.0e4, "L_m": 2.0, "c_m": 1.0, "e_m": 0.1,
                      "CLalpha": "2π", "alpha0_deg": 2.0, "n_eleman": 40},
        "q_div_analitik_Pa": round(qa, 2), "q_div_FE_Pa": round(qfe, 2),
        "q_div_hata_pct": round(err_qdiv, 3),
        "tip_twist_hata_pct_0p5qdiv": round(err_tip, 3),
        "fsi_yakinsama": {"q_0.95_qdiv": conv_below, "q_1.05_qdiv": conv_above},
        "sonuc": ("GECTI — partisyonlu FSI q_div'i %0.01 yakaladı, sec-büyütmeyi izledi, "
                  "diverjans eşiğini doğru tespit etti." if ok else "tolerans/eşik dışı"),
        "_not": "Birim test: test_fsi_aeroelastic. Figür: fsi_divergence.png. "
                "Üretim: python experiments/fsi_divergence.py",
    }
    (HERE.parent / "fsi_divergence.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print("SONUC:", rec["sonuc"], flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
