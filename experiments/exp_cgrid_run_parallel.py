"""C-grid PARALEL koşucu (mpirun, hwloc-fix) — overnight drag GCI için.
Seri exp_cgrid_run.py ile aynı 3-aşama (upwind warmup → SST → SSTLM); her foamRun
decomposePar/-parallel/reconstructPar ile sarılır. Aşama-geçişlerinde alan-enjeksiyonu
(gammaInt/ReThetat) case seviyesinde yapılıp yeniden dekompoze edilir.
Kullanım: python exp_cgrid_run_parallel.py LABEL n_air n_wake nj s0 s1 s2 [np]
"""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import exp_transition as T

from cgrid_elliptic import build_cgrid, write_polymesh_cgrid

alpha = 4
rho, V, nu, chord = 1.225, 50.0, 1.48e-5, 1.0
A = sys.argv
lbl = A[1]
na, nw, njj = int(A[2]), int(A[3]), int(A[4])
s0_end, s1_end, s2_end = int(A[5]), int(A[6]), int(A[7])
NP = int(A[8]) if len(A) > 8 else 4

case = Path(f"gci_cgP_{lbl}")
if case.exists():
    shutil.rmtree(case)
(case / "system").mkdir(parents=True, exist_ok=True)
X, Y, I, nj, nwk = build_cgrid(n_air=na, n_wake=nw, nj=njj)
npts, nf, ncell, nint = write_polymesh_cgrid(case, X, Y, I, nj, nwk)
print(f"{lbl}: {ncell} hücre, np={NP}", flush=True)

(case / "system" / "decomposeParDict").write_text(
    "FoamFile{version 2.0;format ascii;class dictionary;object decomposeParDict;}\n"
    f"numberOfSubdomains {NP}; method scotch;")


def setup(case, alpha):
    a = math.radians(alpha)
    Ux, Uy = V * math.cos(a), V * math.sin(a)
    It = 0.0018
    Lt = 0.07
    k0 = 1.5 * (V * It) ** 2
    w0 = math.sqrt(k0) / (0.09 ** 0.25 * Lt)
    nut0 = k0 / w0
    z = case / "0"
    z.mkdir(exist_ok=True)

    def W(n, b):
        (z / n).write_text(b)
    fs_v = (f'farfield{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}} '
            f'outlet{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}}')
    fs_p = ('farfield{type freestreamPressure;freestreamValue uniform 0;} '
            'outlet{type freestreamPressure;freestreamValue uniform 0;}')
    W("U", f'FoamFile{{version 2.0;format ascii;class volVectorField;object U;}} dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} {Uy} 0); boundaryField{{ airfoil{{type noSlip;}} {fs_v} frontAndBack{{type empty;}} }}')
    W("p", f'FoamFile{{version 2.0;format ascii;class volScalarField;object p;}} dimensions [0 2 -2 0 0 0 0]; internalField uniform 0; boundaryField{{ airfoil{{type zeroGradient;}} {fs_p} frontAndBack{{type empty;}} }}')

    def fs_s(v):
        return f'farfield{{type freestream;freestreamValue uniform {v};}} outlet{{type freestream;freestreamValue uniform {v};}}'
    W("k", f'FoamFile{{version 2.0;format ascii;class volScalarField;object k;}} dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e}; boundaryField{{ airfoil{{type kqRWallFunction;value uniform {k0:.6e};}} {fs_s(f"{k0:.6e}")} frontAndBack{{type empty;}} }}')
    W("omega", f'FoamFile{{version 2.0;format ascii;class volScalarField;object omega;}} dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f}; boundaryField{{ airfoil{{type omegaWallFunction;value uniform {w0:.4f};}} {fs_s(f"{w0:.4f}")} frontAndBack{{type empty;}} }}')
    W("nut", f'FoamFile{{version 2.0;format ascii;class volScalarField;object nut;}} dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e}; boundaryField{{ airfoil{{type nutLowReWallFunction;value uniform 0;}} farfield{{type calculated;value uniform {nut0:.6e};}} outlet{{type calculated;value uniform {nut0:.6e};}} frontAndBack{{type empty;}} }}')
    io = 'farfield{type inletOutlet;inletValue uniform %s;value uniform %s;} outlet{type inletOutlet;inletValue uniform %s;value uniform %s;}'
    W("gammaInt", 'FoamFile{version 2.0;format ascii;class volScalarField;object gammaInt;} dimensions [0 0 0 0 0 0 0]; internalField uniform 1; boundaryField{ airfoil{type zeroGradient;} ' + io % ("1", "1", "1", "1") + ' frontAndBack{type empty;} }')
    W("ReThetat", 'FoamFile{version 2.0;format ascii;class volScalarField;object ReThetat;} dimensions [0 0 0 0 0 0 0]; internalField uniform 100; boundaryField{ airfoil{type zeroGradient;} ' + io % ("100", "100", "100", "100") + ' frontAndBack{type empty;} }')
    (case / "constant" / "transportProperties").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object transportProperties;}}\ntransportModel Newtonian; nu {nu};')
    tmp = Path("_cgP_tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "system").mkdir(parents=True)
    (tmp / "constant").mkdir()
    T.setup(tmp, alpha)
    shutil.copy(tmp / "system" / "fvSchemes", case / "system" / "fvSchemes")
    fvsol = (tmp / "system" / "fvSolution").read_text().replace(
        "relaxationFactors{equations{U 0.3;k 0.2;omega 0.2;gammaInt 0.2;ReThetat 0.2;}fields{p 0.15;}}",
        "relaxationFactors{equations{U 0.25;k 0.15;omega 0.15;gammaInt 0.15;ReThetat 0.15;}fields{p 0.1;}}")
    (case / "system" / "fvSolution").write_text(fvsol)
    shutil.rmtree(tmp)


setup(case, alpha)
p = str(case.resolve())
wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92), '/')}"
ENV = "source /opt/openfoam11/etc/bashrc && export HWLOC_COMPONENTS=-gl && unset FOAM_SIGFPE"


def sh(cmd, t=43200):    # 12h/çağrı — fine mesh aşama-2 paralel ~5-6h sürebilir
    return subprocess.run(f'wsl bash -c "{ENV} && cd {wsl} && {cmd}"',
                          shell=True, capture_output=True, text=True, timeout=t)


def latest_time():
    return max((d for d in case.iterdir() if d.is_dir() and d.name != "0"
                and d.name.replace(".", "", 1).isdigit()),
               key=lambda d: float(d.name), default=None)


def set_startfrom(latest: bool):
    cd = (case / "system" / "controlDict").read_text()
    cd = cd.replace("startFrom startTime", "startFrom latestTime") if latest else cd
    (case / "system" / "controlDict").write_text(cd)


def parse_cd_cl(fdat):
    ll = [line for line in fdat.read_text().splitlines() if line.strip() and not line.startswith("#")]
    nums = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
    Fx = float(nums[1]) + float(nums[4])
    Fy = float(nums[2]) + float(nums[5])
    a = math.radians(alpha)
    q = 0.5 * rho * V ** 2
    S = chord * 0.1
    return (Fx * math.cos(a) + Fy * math.sin(a)) / (q * S), (-Fx * math.sin(a) + Fy * math.cos(a)) / (q * S)


def forces_cd_cl():
    ff = sorted((case / "postProcessing" / "forces").glob("*/forces.dat"),
                key=lambda f: float(f.parent.name))
    return parse_cd_cl(ff[-1])


out = {"topology": "C-grid PARALEL (wake-kumelemeli)", "mesh": f"n_air={na} n_wake={nw} nj={njj}",
       "cells": ncell, "np": NP, "s0_end": s0_end, "s1_end": s1_end, "s2_end": s2_end}

# ── Aşama 0: 1.-mertebe upwind warmup (potentialFoam init), kOmegaSST ──
fvs_ho = (case / "system" / "fvSchemes").read_text()
fvs_fo = fvs_ho.replace("div(phi,U) bounded Gauss linearUpwindV grad(U)",
                        "div(phi,U) bounded Gauss upwind")
(case / "system" / "fvSchemes").write_text(fvs_fo)
T.ctrl(case, "kOmegaSST", s0_end)
sh("decomposePar -force >log.decomp0 2>&1")
sh(f"mpirun --oversubscribe -np {NP} potentialFoam -initialiseUBCs -writep -parallel >log.pot 2>&1")
r0 = sh(f"mpirun --oversubscribe -np {NP} foamRun -solver incompressibleFluid -parallel >log.s0 2>&1")
sh("reconstructPar -latestTime >log.recon0 2>&1")

if latest_time() is None:
    out["status"] = "stage0_failed"
else:
    # ── Aşama 1: yüksek-mertebe şema, kaldığı yerden ──
    (case / "system" / "fvSchemes").write_text(fvs_ho)
    T.ctrl(case, "kOmegaSST", s1_end)
    set_startfrom(latest=True)
    sh("decomposePar -force -latestTime >log.decomp1 2>&1")
    sh(f"mpirun --oversubscribe -np {NP} foamRun -solver incompressibleFluid -parallel >log.s1 2>&1")
    sh("reconstructPar -latestTime >log.recon1 2>&1")
    lt = latest_time()
    if lt is None:
        out["status"] = "stage1_failed"
    else:
        cd1, cl1 = forces_cd_cl()
        out["SST"] = {"Cd": round(cd1, 5), "Cl": round(cl1, 4)}
        print(f"{lbl} SST: Cd={cd1:.5f} Cl={cl1:.4f}", flush=True)
        # ── Aşama 2: gammaInt/ReThetat enjekte et, kOmegaSSTLM ──
        for fld in ("gammaInt", "ReThetat"):
            shutil.copy(case / "0" / fld, lt / fld)
        T.ctrl(case, "kOmegaSSTLM", s2_end)
        set_startfrom(latest=True)
        sh("decomposePar -force -latestTime >log.decomp2 2>&1")
        sh(f"mpirun --oversubscribe -np {NP} foamRun -solver incompressibleFluid -parallel >log.s2 2>&1")
        s2 = (case / "log.s2").read_text(errors="ignore")
        # Paralel foamRun "End" + "Finalising parallel run" ile biter (seri yalnız "End").
        done = "Finalising parallel run" in s2 or s2.rstrip().endswith("End")
        if "FOAM FATAL" in s2 or not done:
            out["status"] = "stage2_failed"
            print(f"{lbl}: STAGE2 FATAL/CRASH", flush=True)
        else:
            cd2, cl2 = forces_cd_cl()
            out["LM"] = {"Cd": round(cd2, 5), "Cl": round(cl2, 4)}
            out["status"] = "ok"
            print(f"{lbl} LM:  Cd={cd2:.5f} Cl={cl2:.4f}", flush=True)

# Cikti adi hesaplaniyor; literal ad kaynakta gecmedigi icin kanit denetimi
# bunu "uretici kod depoda YOK" saniyordu. Komut kanita YAZILIYOR.
out["_uretim"] = ("Üretim: python experiments/exp_cgrid_run_parallel.py "
                  + " ".join(sys.argv[1:]))
Path(f"gci_cgridP_{lbl}.json").write_text(json.dumps(out, indent=2))
print("YAZILDI gci_cgridP_" + lbl + ".json", flush=True)
