"""FEA doğrulama #5 — termal gerilme (engellenmiş genleşme), kapalı-forma karşı.
İki-ucu eksenel-sabit çubuk, üniform ΔT: yanal serbest → tek-eksenli σ = E·α·ΔT (ısınınca
basınç). ÜRETİMin TERMAL yolunu doğrular: *EXPANSION (α) + *TEMPERATURE (CalculiX termo-
elastik strain). Kuvvet/basınç/gövde yüklerinden sonra DÖRDÜNCÜ yük-mekanizması (termal).
Kullanım: python experiments/fea_validation_thermal.py
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.frd_parser import parse_frd  # noqa: E402

L, A = 1.0, 0.05
nx, ny, nz = 24, 4, 4
E, NU, ALPHA, DT = 70e9, 0.3, 23e-6, 50.0          # alüminyum, ΔT=50 K
SIG_AN = E * ALPHA * DT                              # Pa — engellenmiş genleşme gerilmesi


def _nid(ix, iy, iz):
    return ix * (ny + 1) * (nz + 1) + iy * (nz + 1) + iz + 1


def write_inp(path: Path):
    nodes, elems = [], []
    for ix in range(nx + 1):
        for iy in range(ny + 1):
            for iz in range(nz + 1):
                nodes.append((_nid(ix, iy, iz), ix * L / nx, iy * A / ny, iz * A / nz))
    eid = 0
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                eid += 1
                c = [_nid(ix, iy, iz), _nid(ix + 1, iy, iz), _nid(ix + 1, iy + 1, iz),
                     _nid(ix, iy + 1, iz), _nid(ix, iy, iz + 1), _nid(ix + 1, iy, iz + 1),
                     _nid(ix + 1, iy + 1, iz + 1), _nid(ix, iy + 1, iz + 1)]
                elems.append((eid, c))
    nx0 = [_nid(0, iy, iz) for iy in range(ny + 1) for iz in range(nz + 1)]
    nxl = [_nid(nx, iy, iz) for iy in range(ny + 1) for iz in range(nz + 1)]
    nall = [n for n, *_ in nodes]
    Ln = ["*HEADING", "Termal gerilme dogrulama (C3D8I, engellenmis genlesme)", "*NODE"]
    Ln += [f"{n}, {x:.6e}, {y:.6e}, {z:.6e}" for n, x, y, z in nodes]
    Ln += ["*ELEMENT, TYPE=C3D8I, ELSET=EALL"]
    Ln += [f"{e}, " + ", ".join(map(str, c)) for e, c in elems]
    Ln += ["*NSET, NSET=NX0"] + [f"{n}," for n in nx0]
    Ln += ["*NSET, NSET=NXL"] + [f"{n}," for n in nxl]
    Ln += ["*NSET, NSET=NALL, GENERATE", f"1, {len(nodes)}, 1"]
    Ln += ["*MATERIAL, NAME=MAT", "*ELASTIC", f"{E:.6e}, {NU}",
           "*EXPANSION, ZERO=0", f"{ALPHA:.6e}",
           "*SOLID SECTION, ELSET=EALL, MATERIAL=MAT",
           "*INITIAL CONDITIONS, TYPE=TEMPERATURE", "NALL, 0.0",
           "*STEP", "*STATIC",
           "*BOUNDARY", "NX0, 1, 1, 0.0", "NXL, 1, 1, 0.0",   # iki uç eksenel sabit
           f"{nx0[0]}, 2, 3, 0.0",                            # 1 düğüm y,z → rijit-cisim
           "*TEMPERATURE", f"NALL, {DT}",                     # üniform ΔT
           "*NODE FILE", "U", "*EL FILE", "S", "*END STEP"]
    path.write_text("\n".join(Ln) + "\n")


def main():
    work = HERE.parent / "_fea_val_thermal"
    work.mkdir(exist_ok=True)
    inp = work / "thermal.inp"
    write_inp(inp)
    print(f"Analitik: sigma = E·α·ΔT = {SIG_AN / 1e6:.2f} MPa (ΔT={DT} K, α={ALPHA:.1e})",
          flush=True)
    ccx = run_ccx(inp, timeout=600)
    if not ccx.success:
        print("CCX FAILED:", (ccx.stderr or ccx.stdout or "")[-400:]); return 1
    vm = parse_frd(ccx.frd_path).von_mises()
    if vm is None:
        print("von Mises okunamadı"); return 1
    # iç bölge (uç-etkilerinden uzak) temsili gerilme
    s_med = float(np.percentile(vm / 1e6, 50))
    err = abs(s_med - SIG_AN / 1e6) / (SIG_AN / 1e6) * 100
    print(f"FEM: sigma_medyan={s_med:.2f} MPa (hata %{err:.1f})", flush=True)
    ok = err < 10
    print("SONUC:", "GECTI (termal gerilme analitik ile uyumlu)" if ok else "tolerans disi",
          flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
