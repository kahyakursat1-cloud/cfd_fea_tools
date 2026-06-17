"""FEA doğrulama (validation) — ankastre kiriş, kapalı-form çözüme karşı.
CalculiX kurulumu + frd-parse + eleman davranışını bilinen analitik sonuçla
doğrular (V&V). Euler-Bernoulli: δ=PL³/3EI, σ_max=M·c/I (kök yüzeyi).
Kullanım: python experiments/fea_validation.py
"""
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.frd_parser import parse_frd  # noqa: E402

# Kiriş: L×b×h, x boyunca ankastre kök (x=0), uçta (x=L) -z toplam P
L, b, h = 1.0, 0.05, 0.05
nx, ny, nz = 24, 4, 4
E, nu, P = 70e9, 0.33, 1000.0
I = b * h ** 3 / 12.0
delta_an = P * L ** 3 / (3 * E * I) * 1000          # mm
sigma_an = (P * L) * (h / 2) / I / 1e6              # MPa (kök yüzey bending)


def _nid(ix, iy, iz):
    return ix * (ny + 1) * (nz + 1) + iy * (nz + 1) + iz + 1


def write_inp(path: Path):
    nodes, elems = [], []
    for ix in range(nx + 1):
        for iy in range(ny + 1):
            for iz in range(nz + 1):
                nodes.append((_nid(ix, iy, iz), ix * L / nx, iy * b / ny, iz * h / nz))
    eid = 0
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                eid += 1
                c = [_nid(ix, iy, iz), _nid(ix + 1, iy, iz), _nid(ix + 1, iy + 1, iz),
                     _nid(ix, iy + 1, iz), _nid(ix, iy, iz + 1), _nid(ix + 1, iy, iz + 1),
                     _nid(ix + 1, iy + 1, iz + 1), _nid(ix, iy + 1, iz + 1)]
                elems.append((eid, c))
    fixed = [_nid(0, iy, iz) for iy in range(ny + 1) for iz in range(nz + 1)]
    tip = [_nid(nx, iy, iz) for iy in range(ny + 1) for iz in range(nz + 1)]
    fz = -P / len(tip)
    L_ = ["*HEADING", "Ankastre kiris dogrulama (C3D8I)", "*NODE"]
    L_ += [f"{n}, {x:.6e}, {y:.6e}, {z:.6e}" for n, x, y, z in nodes]
    L_ += ["*ELEMENT, TYPE=C3D8I, ELSET=EALL"]
    L_ += [f"{e}, " + ", ".join(map(str, c)) for e, c in elems]
    L_ += ["*NSET, NSET=NFIX"] + [f"{n}," for n in fixed]
    L_ += ["*NSET, NSET=NTIP"] + [f"{n}," for n in tip]
    L_ += ["*MATERIAL, NAME=MAT", "*ELASTIC", f"{E:.6e}, {nu}",
           "*SOLID SECTION, ELSET=EALL, MATERIAL=MAT",
           "*STEP", "*STATIC",
           "*BOUNDARY", "NFIX, 1, 3, 0.0",
           "*CLOAD"] + [f"{n}, 3, {fz:.6e}" for n in tip]
    L_ += ["*NODE FILE", "U", "*EL FILE", "S", "*END STEP"]
    path.write_text("\n".join(L_) + "\n")


def main():
    work = HERE.parent / "_fea_val"
    work.mkdir(exist_ok=True)
    inp = work / "cantilever.inp"
    write_inp(inp)
    print(f"Analitik: delta={delta_an:.3f} mm, sigma_kok={sigma_an:.1f} MPa", flush=True)
    ccx = run_ccx(inp, timeout=600)
    if not ccx.success:
        print("CCX FAILED:", (ccx.stderr or "")[-300:]); return 1
    frd = parse_frd(ccx.frd_path)
    disp = frd.displacement_magnitude()
    vm = frd.von_mises()
    d_fem = float(disp.max()) * 1000 if disp is not None else None
    s_fem = float(np.percentile(vm / 1e6, 99)) if vm is not None else None   # tekillik-robust
    s_peak = float(vm.max()) / 1e6 if vm is not None else None
    ed = abs(d_fem - delta_an) / delta_an * 100 if d_fem else None
    es = abs(s_fem - sigma_an) / sigma_an * 100 if s_fem else None
    print(f"FEM:      delta={d_fem:.3f} mm (hata %{ed:.1f}), sigma_temsili={s_fem:.1f} MPa "
          f"(hata %{es:.1f}), sigma_tepe={s_peak:.1f} MPa", flush=True)
    ok = (ed is not None and ed < 8) and (es is not None and es < 15)
    print("SONUC:", "✅ GECTI (analitik ile uyumlu)" if ok else "⚠ tolerans disi", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
