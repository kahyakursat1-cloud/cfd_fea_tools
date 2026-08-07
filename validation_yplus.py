"""
y+~1 Duvar-Cozunurlu Validation — NACA0012, Re=3e6
==================================================
Kaba O-grid (y+~400 wall function) drag'i ~%27 fazla tahmin ediyordu.
Bu surum: hedef y+ icin ilk-katman yuksekligini hesaplar, O-grid grading'ini
otomatik cozer, low-Re duvar muamelesi (kOmegaSST resolved) kullanir.
Amac: Cd hatasini arastirma-sinifina (<~%10) indirmek.

Kullanim: python validation_yplus.py [alpha ...]   (varsayilan: 0 4 8)
"""
import json
import math
import sys
from pathlib import Path

from validation_suite import NACA0012_NASA, NACA0012Validation


def first_layer_for_yplus(yplus, V, nu, c=1.0):
    """Duz-levha turbulent Cf tahminiyle hedef y+ icin ilk hucre yuksekligi (m)."""
    Re = V * c / nu
    Cf = 0.058 * Re ** -0.2          # Prandtl duz-levha
    u_tau = V * math.sqrt(Cf / 2.0)
    return yplus * nu / u_tau, u_tau, Re


def grading_for_first_cell(delta1, N, L):
    """simpleGrading orani G (=son/ilk hucre) — N hucre, toplam L, ilk hucre delta1.
    Geometrik seri: delta1*(g^N-1)/(g-1)=L cozulur; G=g^(N-1).
    """
    target = L / delta1
    lo, hi = 1.0001, 1.5
    for _ in range(200):
        g = 0.5 * (lo + hi)
        s = (g**N - 1) / (g - 1)
        if s > target:
            hi = g
        else:
            lo = g
    g = 0.5 * (lo + hi)
    return g ** (N - 1), g


class NACA0012YPlus(NACA0012Validation):
    """y+~1 duvar-cozunurlu O-grid: yuksek grading + low-Re duvar fonksiyonlari."""
    def __init__(self, base_path, target_yplus=1.0, n_norm=140, n_prof=240):
        super().__init__(base_path)
        self.n_prof = n_prof
        self.n_norm = n_norm
        # _write_ogrid_bc bu attribute'lari getattr ile okur -> low-Re muamele
        self.nut_wall = "nutLowReWallFunction"
        self.k_wall   = "kLowReWallFunction"
        # Hedef y+ icin grading'i coz (R=20 _write_ogrid'de sabit; radyal uzunluk ~19.7)
        delta1, u_tau, Re = first_layer_for_yplus(target_yplus, self.V, self.NU, self.C)
        G, g = grading_for_first_cell(delta1, n_norm, L=19.7)
        self.grading = round(G)
        self._meta = {
            "target_yplus": target_yplus, "delta1_um": round(delta1 * 1e6, 3),
            "u_tau": round(u_tau, 4), "grading": self.grading,
            "cell_expansion": round(g, 5), "n_norm": n_norm, "n_prof": n_prof,
        }


def main():
    alphas = [int(a) for a in sys.argv[1:]] or [0, 4, 8]
    base = Path("./validation/yplus")
    base.mkdir(parents=True, exist_ok=True)

    v0 = NACA0012YPlus(str(base / "tmp"))
    print("y+~1 MESH PARAMETRELERI:")
    for k, val in v0._meta.items():
        print(f"  {k:16s}: {val}")
    print()

    results = {"mesh": v0._meta, "cases": {}}
    for a in alphas:
        print(f"=== alpha={a} (y+~1 duvar-cozunurlu) ===")
        v = NACA0012YPlus(str(base / f"alpha_{a:02d}"))
        r = v.run(alpha_deg=a)
        results["cases"][a] = r
        if "Cd_sim" in r:
            print(f"  Cd={r['Cd_sim']} (ref={r.get('Cd_ref')}, err={r.get('Cd_err_pct')}%)  "
                  f"Cl={r['Cl_sim']} (ref={r.get('Cl_ref')}, err={r.get('Cl_err_pct')}%)  "
                  f"-> {r.get('status')}")
        else:
            print(f"  KOSU BASARISIZ: {r}")
        print()

    (base / "yplus_results.json").write_text(json.dumps(results, indent=2, default=str))
    print("=" * 56)
    print("  OZET — y+~1 duvar-cozunurlu")
    print("=" * 56)
    for a, r in results["cases"].items():
        if "Cd_err_pct" in r:
            print(f"  alpha={a:2d}:  Cd_err={r['Cd_err_pct']:5.1f}%   Cl_err={r['Cl_err_pct']:5.1f}%   {r['status']}")
    print(f"\nKaydedildi: {base / 'yplus_results.json'}")


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    main()
