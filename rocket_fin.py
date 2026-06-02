"""
Roket Fin Yapisal Analizi
=========================
1) Flutter hizi (NACA TN 4197 / Martin) — roketin baskın yapısal kriteri.
   Fin flutter ucus hizini asarsa kanat catlamadan once titresip kopar.
2) Fin statik FEA (CalculiX) — max-q aerodinamik yuk altinda kantilever plaka.

Fin geometrisi .ork'tan (rocket_cfd ile ayni):
  rootchord=tipchord=0.0508m, span=0.030m, thick=0.002m, 3 fin.
"""

import math
import subprocess
import numpy as np
from pathlib import Path

# Fin geometrisi
FIN_ROOT  = 0.0508
FIN_TIP   = 0.0508
FIN_SPAN  = 0.030
FIN_THICK = 0.002

# Fin malzemeleri (G = kayma modulu Pa, E, yield Pa, rho)
FIN_MATERIALS = {
    "balsa":      {"E": 3.5e9,  "G": 0.2e9,  "yield": 15e6,  "rho": 160,  "nu": 0.30},
    "plywood":    {"E": 8.0e9,  "G": 0.6e9,  "yield": 30e6,  "rho": 600,  "nu": 0.30},
    "fiberglass": {"E": 25e9,   "G": 4.0e9,  "yield": 250e6, "rho": 1800, "nu": 0.20},
    "g10":        {"E": 18e9,   "G": 7.0e9,  "yield": 310e6, "rho": 1850, "nu": 0.12},
}

A_SOUND = 340.0      # ses hizi (m/s, deniz seviyesi)
P_ATM   = 101325.0   # Pa
RHO_AIR = 1.225


def flutter_velocity(material: str = "balsa", altitude_P: float = P_ATM) -> dict:
    """NACA TN 4197 fin flutter hizi.
    Vf = a * sqrt( G / ( 1.337 * AR^3 * P * (lambda+1) / (2*(AR+2)*(t/c)^3) ) )
    """
    mat = FIN_MATERIALS[material]
    G = mat["G"]
    area = 0.5 * (FIN_ROOT + FIN_TIP) * FIN_SPAN     # fin planform alani
    AR = FIN_SPAN**2 / area                           # semi-span^2 / area
    lam = FIN_TIP / FIN_ROOT
    tc = FIN_THICK / ((FIN_ROOT + FIN_TIP) / 2)       # ortalama t/c

    denom = 1.337 * AR**3 * altitude_P * (lam + 1) / (2 * (AR + 2) * tc**3)
    Vf = A_SOUND * math.sqrt(G / denom)
    return {
        "material": material,
        "flutter_velocity_ms": round(Vf, 1),
        "flutter_mach": round(Vf / A_SOUND, 3),
        "aspect_ratio": round(AR, 3),
        "taper": round(lam, 2),
        "thickness_ratio": round(tc, 4),
        "shear_modulus_GPa": G / 1e9,
    }


def fin_fea(material: str = "balsa", q_pa: float = None, v_ms: float = 29.0,
            cl_fin: float = 0.5, base_path: str = "./rocket_fin") -> dict:
    """Fin kantilever FEA — kok ankastre, aerodinamik yan-yuk altinda.
    S3 shell, max-q dinamik basinci ile.
    """
    case = Path(base_path)
    case.mkdir(exist_ok=True)
    mat = FIN_MATERIALS[material]

    if q_pa is None:
        q_pa = 0.5 * RHO_AIR * v_ms**2
    # Fin normal kuvveti: N = q * Cl * area ; basinc = N/area = q*Cl
    p_fin = q_pa * cl_fin

    # Mesh: dikdortgen fin, kok x ekseninde, span z ekseninde
    nx, nz = 12, 8
    xs = np.linspace(0, FIN_ROOT, nx + 1)
    zs = np.linspace(0, FIN_SPAN, nz + 1)
    verts, vid = [], {}
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            vid[(i, j)] = len(verts) + 1
            verts.append((x, 0.0, z))
    faces = []
    for i in range(nx):
        for j in range(nz):
            a, b = vid[(i, j)], vid[(i+1, j)]
            c, d = vid[(i+1, j+1)], vid[(i, j+1)]
            faces += [(a, b, c), (a, c, d)]

    root_nodes = [vid[(i, 0)] for i in range(nx + 1)]   # z=0 ankastre

    inp = [f"*HEADING\nRoket fin FEA — {material} q={q_pa:.0f}Pa\n", "*NODE, NSET=NALL\n"]
    for k, (x, y, z) in enumerate(verts, 1):
        inp.append(f"{k}, {x:.6e}, {y:.6e}, {z:.6e}\n")
    inp.append("*ELEMENT, TYPE=S3, ELSET=EALL\n")
    for k, (a, b, c) in enumerate(faces, 1):
        inp.append(f"{k}, {a}, {b}, {c}\n")
    inp.append("*NSET, NSET=NROOT\n")
    for g in range(0, len(root_nodes), 8):
        inp.append(", ".join(map(str, root_nodes[g:g+8])) + "\n")
    inp += [f"*MATERIAL, NAME=FINMAT\n*ELASTIC\n{mat['E']:.4e}, {mat['nu']}\n*DENSITY\n{mat['rho']}\n",
            f"*SHELL SECTION, ELSET=EALL, MATERIAL=FINMAT\n{FIN_THICK:.5f},\n",
            "*BOUNDARY\nNROOT, 1, 6, 0\n",
            "*STEP\n*STATIC\n1.0, 1.0\n",
            f"*DLOAD\nEALL, P, {p_fin:.4f}\n",
            "*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n"]
    (case / "fin.inp").write_text("".join(inp))

    p = str(case.resolve())
    wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92), '/')}"
    subprocess.run(f'wsl bash -c "cd {wsl} && ccx -i fin"', shell=True,
                   capture_output=True, timeout=300, text=True)

    frd = case / "fin.frd"
    if not frd.exists():
        return {"status": "FAILED", "step": "ccx"}

    import re as _re
    # FRD fixed-width: negatif sayilar bitisik (0.0E+00-2.8E-11) -> sci-regex
    _SCI = _re.compile(r'[-+]?\d*\.\d+[eE][-+]?\d+')
    disps, vms = [], []
    block = None
    for line in frd.read_text(errors="replace").splitlines():
        if " -4  DISP" in line: block = "D"; continue
        if " -4  STRESS" in line: block = "S"; continue
        if line.startswith(" -4") or line.startswith(" -3"): block = None
        if block and line.startswith(" -1"):
            v = [float(x) for x in _SCI.findall(line[3:])]   # node sonrasi degerler
            if block == "D" and len(v) >= 3:
                disps.append((v[0]**2+v[1]**2+v[2]**2)**0.5)
            elif block == "S" and len(v) >= 6:
                s = v[:6]
                vms.append(((s[0]-s[1])**2+(s[1]-s[2])**2+(s[2]-s[0])**2
                            + 6*(s[3]**2+s[4]**2+s[5]**2))**0.5/2**0.5)
    if not disps:
        return {"status": "FAILED", "step": "frd"}
    vm_max = max(vms) if vms else 0
    sf = round(mat["yield"]/vm_max, 1) if vm_max > 0 else None
    return {
        "status": "SUCCESS", "material": material, "q_Pa": round(q_pa, 1),
        "fin_pressure_Pa": round(p_fin, 2),
        "tip_deflection_mm": round(max(disps)*1000, 3),
        "max_von_mises_MPa": round(vm_max/1e6, 3),
        "safety_factor": sf, "is_safe": sf > 1.5 if sf else False,
    }


def _isf(s):
    try: float(s); return True
    except: return False


def assess(material: str = "balsa", v_flight_ms: float = 29.3) -> dict:
    """Tam fin degerlendirmesi: flutter + statik FEA."""
    fl = flutter_velocity(material)
    fe = fin_fea(material, v_ms=v_flight_ms)
    fl_margin = fl["flutter_velocity_ms"] / v_flight_ms if v_flight_ms > 0 else None
    return {
        "material": material,
        "v_flight_ms": v_flight_ms,
        "flutter": fl,
        "flutter_margin": round(fl_margin, 1) if fl_margin else None,
        "flutter_safe": fl_margin is not None and fl_margin > 1.5,
        "static_fea": fe,
    }


if __name__ == "__main__":
    import sys, json
    mat = sys.argv[1] if len(sys.argv) > 1 else "balsa"
    v = float(sys.argv[2]) if len(sys.argv) > 2 else 29.3
    r = assess(mat, v)
    print(json.dumps(r, indent=2))
    json.dump(r, open("rocket_fin_result.json", "w"), indent=2)
    print("Kaydedildi: rocket_fin_result.json")
