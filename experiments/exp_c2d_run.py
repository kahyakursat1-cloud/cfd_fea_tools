"""Construct2D O-grid (künt-TE) + plain uniform freestream, değişken far-field.
Far-field hipotezini PROFESYONEL grid + ÇALIŞAN BC ile test eder (bespoke C-grid
ve nonuniform-BC çıkmazlarını atlar). SST fully-turbulent (grid-stabil; araştırma
önerisi — geçiş ayrı). Kullanım: python exp_c2d_run.py <radi> [nsrf jmax]
"""
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import exp_transition as T  # noqa: E402

import construct2d_bridge as cb  # noqa: E402
from analysis.backend import linux_run  # noqa: E402

radi = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
nsrf = int(sys.argv[2]) if len(sys.argv) > 2 else 300
jmax = int(sys.argv[3]) if len(sys.argv) > 3 else 150
alpha, rho, V, chord, span = 4, 1.225, 50.0, 1.0, 0.1
case_name = f"c2d_r{int(radi)}"
case = Path(case_name)

mq = cb.build_mesh(str(HERE.parent / "Construct2D/sample_airfoils/naca0012.dat"),
                   case_name, name="n12", radi=radi, jmax=jmax, nsrf=nsrf,
                   nwke=50, topo="OGRD", slvr="ELLP")
print(f"mesh: {mq.get('status')} cells={mq.get('cells')} nonOrtho={mq.get('non_ortho_max')}", flush=True)
if mq.get("status") != "SUCCESS":
    sys.exit(1)

# patch tiplerini düzelt: airfoil→wall (duvar-fonk/wallDist), frontAndBack→empty
# (2B; gmshToFoam ikisini de 'patch' yapar → empty BC ile uyumsuzluk → çökme).
bf = case / "constant" / "polyMesh" / "boundary"
_t = bf.read_text()
_t = re.sub(r"(airfoil\s*\{\s*type\s+)patch", r"\1wall", _t)
_t = re.sub(r"(frontAndBack\s*\{\s*type\s+)patch", r"\1empty", _t)
bf.write_text(_t)

T.setup(case, alpha)
p = str(case.resolve())
wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92), '/')}"


def of(cmd, t=7200):
    import subprocess
    return linux_run(f"source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && cd {wsl} && {cmd}", t)


def cd_cl():
    ff = sorted((case / "postProcessing" / "forces").glob("*/forces.dat"),
                key=lambda f: float(f.parent.name))
    ll = [x for x in ff[-1].read_text().splitlines() if x.strip() and not x.startswith("#")]
    n = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
    Fx, Fy = float(n[1]) + float(n[4]), float(n[2]) + float(n[5])
    a = math.radians(alpha)
    q = 0.5 * rho * V ** 2
    S = chord * span
    return (Fx * math.cos(a) + Fy * math.sin(a)) / (q * S), (-Fx * math.sin(a) + Fy * math.cos(a)) / (q * S)


ho = (case / "system" / "fvSchemes").read_text()
fo = ho.replace("div(phi,U) bounded Gauss linearUpwindV grad(U)",
                "div(phi,U) bounded Gauss upwind")
(case / "system" / "fvSchemes").write_text(fo)              # upwind ısınma
T.ctrl(case, "kOmegaSST", 1500)
of("potentialFoam -initialiseUBCs -writep >log.pot 2>&1; foamRun -solver incompressibleFluid >log.s0 2>&1")
(case / "system" / "fvSchemes").write_text(ho)             # yüksek-mertebe
T.ctrl(case, "kOmegaSST", 5000)
(case / "system" / "controlDict").write_text(
    (case / "system" / "controlDict").read_text().replace("startFrom startTime", "startFrom latestTime"))
of("foamRun -solver incompressibleFluid >log.s1 2>&1")

cd, cl = cd_cl()
out = {"tool": "Construct2D O-grid (künt-TE)", "radi_c": radi, "cells": mq.get("cells"),
       "nonOrtho": mq.get("non_ortho_max"), "SST": {"Cd": round(cd, 5), "Cl": round(cl, 4)},
       "ref": {"Cd_turb": 0.0092, "Cl": 0.44}}
print(f"[radi={radi:.0f}] SST: Cd={cd:.5f} Cl={cl:.4f}  (ref Cd_turb=0.0092 Cl=0.44)", flush=True)
Path(f"c2d_result_r{int(radi)}.json").write_text(json.dumps(out, indent=2))
