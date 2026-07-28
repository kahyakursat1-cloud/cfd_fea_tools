"""
Construct2D Bridge — yuksek-kaliteli airfoil O-grid -> OpenFOAM
==============================================================
Construct2D (olgun yapisal grid generator) eliptik O-grid uretir:
y+<1 ilk katman + skew~17 deg (elle-yazilan radyal O-grid 82 deg veriyordu).

Akis: airfoil.dat -> construct2d (CGRD/OGRD, ELLP, ypls) -> .p3d (Plot3D 2D)
      -> bu kopru: .p3d oku -> Gmsh .msh (i-periyodik) -> gmshToFoam -> polyMesh.

Bu, OpenVSP/OpenRocket gibi olgun araci entegre etme felsefesi — elle eliptik
cozucu yazmak yerine.
"""

import subprocess
from pathlib import Path

import numpy as np

C2D_DIR = Path(__file__).parent / "Construct2D"
C2D_BIN = C2D_DIR / "construct2d"


def run_construct2d(airfoil_dat: str, work: Path, name: str,
                    jmax=100, ypls=1.0, recd=3.4e6, radi=15.0,
                    nsrf=250, nwke=50, topo="OGRD", slvr="ELLP",
                    stp1=1000, stp2=200) -> Path:
    """Construct2D'yi batch calistir (.nml + GRID/SMTH/QUIT). .p3d dondur."""
    work.mkdir(parents=True, exist_ok=True)
    dat = work / f"{name}.dat"
    dat.write_bytes(Path(airfoil_dat).read_bytes())
    nml = f"""&SOPT
  nsrf = {nsrf}
  radi = {radi}
  nwke = {nwke}
  fdst = 1.0
  fwkl = 1.0
  fwki = 10.0
/
&VOPT
  name = '{name}'
  jmax = {jmax}
  slvr = '{slvr}'
  topo = '{topo}'
  ypls = {ypls}
  recd = {recd}
  stp1 = {stp1}
  stp2 = {stp2}
  funi = 0.20
  asmt = 20
/
&OOPT
  gdim = 2
  npln = 2
  dpln = 0.1
/
"""
    # Construct2D ayarları YALNIZCA 'grid_options.in' dosyasından okur (menu.f90:98);
    # yanlış ad → tüm namelist (radi/topo/jmax) yok sayılır → hep default far-field.
    (work / "grid_options.in").write_text(nml)
    p = str(work.resolve())
    wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92), '/')}"
    binp = "/mnt/" + str(C2D_BIN.resolve())[0].lower() + str(C2D_BIN.resolve())[2:].replace("\\", "/")
    # GRID -> alt-menü; SMTH (smoothed yüzey grid) -> stp1 elliptic smoothing ->
    # "perform more steps (y/n)?" -> n (final smoothing'e geç) -> QUIT.
    # Eski dizi 'GRID SMTH QUIT' idi: "n" cevabı eksik -> prompt QUIT'i reddedip EOF.
    # KESKİN FİRAR KENARI + OGRD: Construct2D "C-grid önerilir, yine de O-grid mi?"
    # diye y/n SORAR ve ilk komut ('GRID') o soruya cevap olarak yutulur; tüm dizi
    # kayardı ("Error: command SMTH not recognized"). NACA0012 hazır .p3d ile
    # koşulduğu için bu yol hiç tetiklenmemişti, NACA2412 ilk kez tetikledi.
    #
    # Cevap KOŞULLU olmalı: CGRD'de böyle bir soru sorulmaz ve fazladan 'y'
    # tanınmayan komut olup süreci düşürür (ölçüldü: log 25 satırda kesildi).
    on_cevap = "y\\n" if topo.upper() == "OGRD" else ""
    cmd = (f'wsl bash -c "cd {wsl} && printf \'{on_cevap}GRID\\nSMTH\\nn\\nQUIT\\n\' | '
           f'{binp} {name}.dat > log.c2d 2>&1"')
    subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    p3d = work / f"{name}.p3d"
    if p3d.exists():
        return p3d
    # IRAKSAMA SESSİZ KALMASIN: eliptik düzleştirici NaN'a gidince .p3d hiç yazılmıyor
    # ve çağıran yalnız "FAILED/construct2d" görüyordu — "Construct2D çalışmadı" ile
    # "grid üretici IRAKSADI" çok farklı iki teşhis.
    log = work / "log.c2d"
    if log.exists() and "NaN" in log.read_text(errors="ignore"):
        print(f"[UYARI] Construct2D {slvr} çözücüsü IRAKSADI (RMS residual NaN) — "
              f"{name}: grid üretilemedi", flush=True)
    return None


def read_p3d_2d(p3d: Path):
    """Plot3D 2D single-block oku. Donduru: X,Y (ni,nj) i-fastest."""
    toks = p3d.read_text().split()
    ni, nj = int(toks[0]), int(toks[1])
    vals = np.array(toks[2:2 + 2*ni*nj], dtype=float)
    X = vals[:ni*nj].reshape(nj, ni).T        # (ni,nj)
    Y = vals[ni*nj:2*ni*nj].reshape(nj, ni).T
    return X, Y, ni, nj


def write_ogrid_gmsh(path, X, Y, ni, nj, span=0.1):
    """O-grid (i-periyodik) -> Gmsh MSH 2.2. j=0 airfoil, j=nj-1 farfield."""
    # seam tespiti: i=0 ile i=ni-1 cakisik mi?
    seam_dup = (abs(X[0, 0]-X[ni-1, 0]) < 1e-9 and abs(Y[0, 0]-Y[ni-1, 0]) < 1e-9)
    ni_u = ni-1 if seam_dup else ni            # benzersiz i sutun sayisi
    def IM(i): return i % ni_u                  # i-periyodik

    nodes = []
    nid = {}
    def add(x, y, z):
        nodes.append((x, y, z)); return len(nodes)
    for k, z in enumerate((0.0, span)):
        for i in range(ni_u):
            for j in range(nj):
                nid[(i, j, k)] = add(X[i, j], Y[i, j], z)

    coord = {v: np.array(p) for p, v in zip(nodes, range(1, len(nodes)+1))}
    def svol(ns):
        p = [coord[n] for n in ns]
        return np.dot(np.cross(p[1]-p[0], p[3]-p[0]), p[4]-p[0])

    L = ["$MeshFormat\n2.2 0 8\n$EndMeshFormat\n",
         "$PhysicalNames\n3\n",
         '2 1 "airfoil"\n2 2 "farfield"\n2 3 "frontAndBack"\n$EndPhysicalNames\n',
         f"$Nodes\n{len(nodes)}\n"]
    for n, (x, y, z) in enumerate(nodes, 1):
        L.append(f"{n} {x:.9g} {y:.9g} {z:.9g}\n")
    L.append("$EndNodes\n")
    elems = []; eid = [0]
    def E(typ, phys, ns):
        eid[0] += 1
        elems.append(f"{eid[0]} {typ} 2 {phys} {phys} " + " ".join(map(str, ns)) + "\n")

    for i in range(ni_u):
        ip = IM(i+1)
        for j in range(nj-1):
            n0 = nid[(i, j, 0)]; n1 = nid[(ip, j, 0)]
            n2 = nid[(ip, j+1, 0)]; n3 = nid[(i, j+1, 0)]
            m0 = nid[(i, j, 1)]; m1 = nid[(ip, j, 1)]
            m2 = nid[(ip, j+1, 1)]; m3 = nid[(i, j+1, 1)]
            h = [n0, n1, n2, n3, m0, m1, m2, m3]
            if svol(h) < 0:
                h = [n0, n3, n2, n1, m0, m3, m2, m1]
            E(5, 0, h)
    # airfoil j=0
    for i in range(ni_u):
        ip = IM(i+1)
        E(3, 1, [nid[(i, 0, 0)], nid[(ip, 0, 0)], nid[(ip, 0, 1)], nid[(i, 0, 1)]])
    # farfield j=nj-1
    for i in range(ni_u):
        ip = IM(i+1)
        E(3, 2, [nid[(i, nj-1, 0)], nid[(ip, nj-1, 0)], nid[(ip, nj-1, 1)], nid[(i, nj-1, 1)]])
    # front/back
    for kk in (0, 1):
        for i in range(ni_u):
            ip = IM(i+1)
            for j in range(nj-1):
                E(3, 3, [nid[(i, j, kk)], nid[(ip, j, kk)], nid[(ip, j+1, kk)], nid[(i, j+1, kk)]])

    L.append(f"$Elements\n{len(elems)}\n"); L.extend(elems); L.append("$EndElements\n")
    Path(path).write_text("".join(L))
    return seam_dup, ni_u


def _min_case(case):
    sysd = case/"system"; sysd.mkdir(parents=True, exist_ok=True)
    (sysd/"controlDict").write_text(
        "FoamFile{ version 2.0; format ascii; class dictionary; object controlDict; }\n"
        "application foamRun; startFrom startTime; startTime 0; stopAt endTime; endTime 1;\n"
        "deltaT 1; writeControl timeStep; writeInterval 1; writeFrequency 1; writeFormat ascii;\n")
    (sysd/"fvSchemes").write_text(
        "FoamFile{ version 2.0; format ascii; class dictionary; object fvSchemes; }\n"
        "ddtSchemes{default steadyState;} gradSchemes{default Gauss linear;}\n"
        "divSchemes{default none;} laplacianSchemes{default Gauss linear corrected;}\n"
        "interpolationSchemes{default linear;} snGradSchemes{default corrected;}\n")
    (sysd/"fvSolution").write_text(
        "FoamFile{ version 2.0; format ascii; class dictionary; object fvSolution; }\nsolvers{} SIMPLE{}\n")


def build_mesh(airfoil_dat: str, case_dir: str, name="naca", **c2d_kw):
    """Tam akis: construct2d -> p3d -> gmsh -> gmshToFoam. checkMesh dondur."""
    case = Path(case_dir)
    work = case / "c2d"
    p3d = run_construct2d(airfoil_dat, work, name, **c2d_kw)
    if not p3d:
        return {"status": "FAILED", "step": "construct2d"}
    X, Y, ni, nj = read_p3d_2d(p3d)
    _min_case(case)
    msh = case / "mesh.msh"
    seam, ni_u = write_ogrid_gmsh(str(msh), X, Y, ni, nj)
    p = str(case.resolve()); wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
    def of(cmd, t=300):
        return subprocess.run(
            f'wsl bash -c "source /opt/openfoam11/etc/bashrc && cd {wsl} && {cmd}"',
            shell=True, capture_output=True, text=True, timeout=t)
    g = of("gmshToFoam mesh.msh > log.g2f 2>&1")
    of("checkMesh > log.check 2>&1")
    chk = (case/"log.check").read_text(errors="replace")
    out = {"status": "SUCCESS" if g.returncode == 0 else "FAILED",
           "ni": ni, "nj": nj, "seam_dup": seam, "cells": ni_u*(nj-1)}
    for line in chk.splitlines():
        if "non-orthogonality Max" in line:
            out["non_ortho_max"] = line.split("Max:")[1].split("average")[0].strip()
        if "Max skewness" in line:
            out["skewness_max"] = line.split("=")[1].split(",")[0].strip()
        if "Mesh OK" in line:
            out["mesh_ok"] = True
    return out


def _fix_patches(case: Path):
    """frontAndBack -> empty, airfoil -> wall (polyMesh/boundary)."""
    import re
    bf = case/"constant"/"polyMesh"/"boundary"
    t = bf.read_text()
    t = re.sub(r"(frontAndBack\s*\{[^}]*?type\s+)patch", r"\1empty", t, flags=re.DOTALL)
    t = re.sub(r"(\bairfoil\s*\{[^}]*?type\s+)patch", r"\1wall", t, flags=re.DOTALL)
    bf.write_text(t)


def run_validation(case_dir: str, alpha_deg=0.0, V=50.0, nu=1.48e-5,
                   rho=1.225, chord=1.0, end_time=2000):
    """Construct2D O-grid'inde kOmegaSST CFD -> Cd, Cl. NASA ile karsilastir."""
    import math
    import re
    case = Path(case_dir)
    _fix_patches(case)
    a = math.radians(alpha_deg)
    # Construct2D airfoil X-Y duzleminde (Y=lift yonu), span=Z. AoA X-Y'de donmeli.
    Ux, Uy = V*math.cos(a), V*math.sin(a)
    I = 0.0018; Lt = 0.07*chord
    k0 = 1.5*(V*I)**2; w0 = math.sqrt(k0)/(0.09**0.25*Lt); nut0 = k0/w0
    z = case/"0"; z.mkdir(exist_ok=True)

    def fa(name, body): (z/name).write_text(body)
    fa("U", f"""FoamFile{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} {Uy} 0);
boundaryField{{ airfoil{{type noSlip;}} farfield{{type freestreamVelocity; freestreamValue uniform ({Ux} {Uy} 0);}} frontAndBack{{type empty;}} }}""")
    fa("p", """FoamFile{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField{ airfoil{type zeroGradient;} farfield{type freestreamPressure; freestreamValue uniform 0;} frontAndBack{type empty;} }""")
    fa("k", f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e};
boundaryField{{ airfoil{{type kqRWallFunction; value uniform {k0:.6e};}} farfield{{type freestream; freestreamValue uniform {k0:.6e};}} frontAndBack{{type empty;}} }}""")
    fa("omega", f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f};
boundaryField{{ airfoil{{type omegaWallFunction; value uniform {w0:.4f};}} farfield{{type freestream; freestreamValue uniform {w0:.4f};}} frontAndBack{{type empty;}} }}""")
    fa("nut", f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e};
boundaryField{{ airfoil{{type nutLowReWallFunction; value uniform 0;}} farfield{{type calculated; value uniform {nut0:.6e};}} frontAndBack{{type empty;}} }}""")

    (case/"constant"/"momentumTransport").write_text(
        'FoamFile{ version 2.0; format ascii; class dictionary; location "constant"; object momentumTransport; }\n'
        'simulationType RAS; RAS{ model kOmegaSST; turbulence on; printCoeffs on; }')
    (case/"constant"/"transportProperties").write_text(
        f'FoamFile{{ version 2.0; format ascii; class dictionary; object transportProperties; }}\ntransportModel Newtonian; nu {nu};')
    (case/"system"/"controlDict").write_text(f"""FoamFile{{ version 2.0; format ascii; class dictionary; object controlDict; }}
application foamRun; startFrom startTime; startTime 0; stopAt endTime; endTime {end_time};
deltaT 1; writeControl timeStep; writeInterval {end_time}; writeFrequency {end_time};
purgeWrite 1; writeFormat binary;
functions{{ forces{{ type forces; libs ("libforces.so"); writeControl timeStep; writeInterval 50;
  patches ("airfoil"); rho rhoInf; rhoInf {rho}; pRef 0; CofR (0.25 0 0); }} }}""")
    (case/"system"/"fvSchemes").write_text("""FoamFile{ version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes{ default steadyState; }
gradSchemes{ default cellLimited Gauss linear 1; }
divSchemes{ default none; div(phi,U) bounded Gauss linearUpwindV grad(U);
  div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;
  div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes{ default Gauss linear corrected; }
interpolationSchemes{ default linear; } snGradSchemes{ default corrected; }
wallDist{ method meshWave; }""")
    # Yuksek-aspect (y+<1, AR~10000) mesh icin: potentialFoam init + PCG + guclu relax
    (case/"system"/"fvSolution").write_text("""FoamFile{ version 2.0; format ascii; class dictionary; object fvSolution; }
solvers{
  p{ solver GAMG; tolerance 1e-7; relTol 0.01; smoother DICGaussSeidel;
     nPreSweeps 0; nPostSweeps 2; nFinestSweeps 2; cacheAgglomeration on;
     agglomerator faceAreaPair; nCellsInCoarsestLevel 50; mergeLevels 1; }
  Phi{ solver GAMG; tolerance 1e-6; relTol 0.01; smoother DICGaussSeidel; nCellsInCoarsestLevel 50; }
  "(U|k|omega)"{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.05; nSweeps 2; } }
SIMPLE{ nNonOrthogonalCorrectors 2; consistent yes; residualControl{ p 1e-6; U 1e-6; } }
potentialFlow{ nNonOrthogonalCorrectors 5; }
relaxationFactors{ equations{ U 0.3; k 0.2; omega 0.2; } fields{ p 0.2; } }""")

    p = str(case.resolve()); wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
    # potentialFoam: divergence-free baslangic (startup blow-up'i onler)
    subprocess.run(
        f'wsl bash -c "source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && cd {wsl} && potentialFoam -initialiseUBCs -writep > log.pot 2>&1; foamRun -solver incompressibleFluid > log.run 2>&1"',
        shell=True, capture_output=True, text=True, timeout=7200)

    ff = list((case/"postProcessing"/"forces").glob("*/forces.dat"))
    if not ff:
        return {"status": "FAILED", "step": "forces"}
    lines = [l for l in ff[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
    nums = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', lines[-1])
    # X-Y duzlem: Fx=nums[1]+nums[4], Fy=nums[2]+nums[5]
    Fx = float(nums[1])+float(nums[4]); Fy = float(nums[2])+float(nums[5])
    drag = Fx*math.cos(a)+Fy*math.sin(a); lift = -Fx*math.sin(a)+Fy*math.cos(a)
    q = 0.5*rho*V**2; S = chord*0.1
    return {"status": "SUCCESS", "alpha": alpha_deg,
            "Cd": round(drag/(q*S), 5), "Cl": round(lift/(q*S), 4)}


if __name__ == "__main__":
    import json
    import sys
    af = str(C2D_DIR / "sample_airfoils" / "naca0012.dat")
    mode = sys.argv[1] if len(sys.argv) > 1 else "mesh"
    if mode == "mesh":
        r = build_mesh(af, "cgrid_val", name="naca0012", ypls=1.0, recd=3.4e6)
        print(json.dumps(r, indent=2, default=str))
    elif mode == "val":
        alpha = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
        r = run_validation("cgrid_val", alpha_deg=alpha)
        ref = {0: (0.0, 0.0082), 4: (0.452, 0.0092)}.get(int(alpha))
        if r.get("status") == "SUCCESS" and ref:
            r["Cl_ref"], r["Cd_ref"] = ref
            r["Cd_err_pct"] = round(abs(r["Cd"]-ref[1])/ref[1]*100, 1)
        print(json.dumps(r, indent=2, default=str))
