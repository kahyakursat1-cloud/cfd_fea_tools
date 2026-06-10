"""C-grid DUZELTILMIS mesh yazici: node paylasimi YOK -> gecerli hex'ler;
wake-cut iki cakisik patch (wakeUp/wakeDown) -> stitchMesh ile internal.
Grid geometrisi cgrid_generator'dan (saglam), sadece yazma/stitch duzeltildi.
"""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import numpy as np

from cgrid_generator import _min_case, build_cgrid

alpha = int(sys.argv[1]) if len(sys.argv) > 1 else 4
R_far = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
case = Path("cgrid_fixed")
if case.exists(): shutil.rmtree(case)
(case/"constant"/"polyMesh").mkdir(parents=True, exist_ok=True)
_min_case(case)

# --- 1) Saglam 2D grid'i al (cgrid_generator), P'yi geri kur ---
nodes, nid, dims, te = build_cgrid("0012", n_half=130, nw=80, nj=120,
                                   first_cell=8e-6, R_far=R_far, wake_len=R_far*0.6)
I, nj = dims; i_te1, i_te2 = te
P = np.zeros((I+1, nj+1, 2))
for i in range(I+1):
    for j in range(nj+1):
        P[i, j] = nodes[nid[(i, j, 0)]-1][:2]

# --- 2) TEMIZ gmsh: her (i,j,k) benzersiz node, wake iki patch ---
span = 0.1
def gid(i, j, k): return 1 + k*(I+1)*(nj+1) + i*(nj+1) + j   # benzersiz, 1-based
L = ["$MeshFormat\n2.2 0 8\n$EndMeshFormat\n",
     "$PhysicalNames\n6\n",
     '2 1 "airfoil"\n2 2 "farfield"\n2 3 "frontAndBack"\n2 5 "outlet"\n2 6 "wakeUp"\n2 7 "wakeDown"\n',
     "$EndPhysicalNames\n", f"$Nodes\n{2*(I+1)*(nj+1)}\n"]
for k, z in enumerate((0.0, span)):
    for i in range(I+1):
        for j in range(nj+1):
            L.append(f"{gid(i,j,k)} {P[i,j,0]:.9g} {P[i,j,1]:.9g} {z:.9g}\n")
L.append("$EndNodes\n")

elems = []; eid = 0
def E(typ, phys, ns):
    global eid; eid += 1
    elems.append(f"{eid} {typ} 2 {phys} {phys} " + " ".join(map(str, ns)) + "\n")
co = {}
for k, z in enumerate((0.0, span)):
    for i in range(I+1):
        for j in range(nj+1):
            co[gid(i,j,k)] = np.array([P[i,j,0], P[i,j,1], z])
def svol(ns):
    p = [co[n] for n in ns]
    return np.dot(np.cross(p[1]-p[0], p[3]-p[0]), p[4]-p[0])
# hexler
for i in range(I):
    for j in range(nj):
        h = [gid(i,j,0), gid(i+1,j,0), gid(i+1,j+1,0), gid(i,j+1,0),
             gid(i,j,1), gid(i+1,j,1), gid(i+1,j+1,1), gid(i,j+1,1)]
        if svol(h) < 0:
            h = [h[0],h[3],h[2],h[1], h[4],h[7],h[6],h[5]]
        E(5, 4, h)
# airfoil (j=0, te araligi)
for i in range(i_te1, i_te2):
    E(3, 1, [gid(i,0,0), gid(i+1,0,0), gid(i+1,0,1), gid(i,0,1)])
# wakeDown (alt iz: j=0, i<i_te1) / wakeUp (ust iz: j=0, i>=i_te2)
for i in range(0, i_te1):
    E(3, 7, [gid(i,0,0), gid(i+1,0,0), gid(i+1,0,1), gid(i,0,1)])
for i in range(i_te2, I):
    E(3, 6, [gid(i,0,0), gid(i+1,0,0), gid(i+1,0,1), gid(i,0,1)])
# farfield (j=nj)
for i in range(I):
    E(3, 2, [gid(i,nj,0), gid(i+1,nj,0), gid(i+1,nj,1), gid(i,nj,1)])
# outlet (i=0, i=I)
for iface in (0, I):
    for j in range(nj):
        E(3, 5, [gid(iface,j,0), gid(iface,j+1,0), gid(iface,j+1,1), gid(iface,j,1)])
# frontAndBack
for k in (0, 1):
    for i in range(I):
        for j in range(nj):
            E(3, 3, [gid(i,j,k), gid(i+1,j,k), gid(i+1,j+1,k), gid(i,j+1,k)])
L.append(f"$Elements\n{len(elems)}\n"); L.extend(elems); L.append("$EndElements\n")
(case/"cgrid.msh").write_text("".join(L))
print(f"grid I={I} nj={nj} cells={I*nj} (n yok-paylasim)", flush=True)

p = str(case.resolve()); wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
def of(cmd, t=900):
    return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && cd {wsl} && {cmd}"',
                          shell=True, capture_output=True, text=True, timeout=t)
of("gmshToFoam cgrid.msh > log.g2f 2>&1")
# wake-cut'i stitch et (cakisik wakeUp<->wakeDown -> internal)
of("stitchMesh -perfect -overwrite wakeUp wakeDown > log.stitch 2>&1")
of("checkMesh > log.check 2>&1")
chk = (case/"log.check").read_text(errors="replace")
nonortho=None
for key in ["cells:", "non-orthogonality Max", "negative volume", "zero area", "Mesh OK", "FAILED", "skewness"]:
    for line in chk.splitlines():
        if key in line:
            print("  "+line.strip(), flush=True)
            if "non-orthogonality Max" in line:
                m=re.search(r"Max:\s*([\d.]+)",line); nonortho=float(m.group(1)) if m else None
            break

if nonortho is None or nonortho > 100:
    print("MESH HALA BOZUK — CFD atlandi"); sys.exit(0)

# --- 3) CFD ---
V,nu,rho,chord=50.0,1.48e-5,1.225,1.0
a=math.radians(alpha); Ux,Uy=V*math.cos(a),V*math.sin(a)
I_t=0.0018; Lt=0.07; k0=1.5*(V*I_t)**2; w0=math.sqrt(k0)/(0.09**0.25*Lt); nut0=k0/w0
z=case/"0"; z.mkdir(exist_ok=True)
(z/"U").write_text(f'FoamFile{{version 2.0;format ascii;class volVectorField;object U;}} dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} {Uy} 0); boundaryField{{ airfoil{{type noSlip;}} farfield{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}} outlet{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}} frontAndBack{{type empty;}} }}')
(z/"p").write_text('FoamFile{version 2.0;format ascii;class volScalarField;object p;} dimensions [0 2 -2 0 0 0 0]; internalField uniform 0; boundaryField{ airfoil{type zeroGradient;} farfield{type freestreamPressure;freestreamValue uniform 0;} outlet{type freestreamPressure;freestreamValue uniform 0;} frontAndBack{type empty;} }')
(z/"k").write_text(f'FoamFile{{version 2.0;format ascii;class volScalarField;object k;}} dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e}; boundaryField{{ airfoil{{type kqRWallFunction;value uniform {k0:.6e};}} farfield{{type freestream;freestreamValue uniform {k0:.6e};}} outlet{{type freestream;freestreamValue uniform {k0:.6e};}} frontAndBack{{type empty;}} }}')
(z/"omega").write_text(f'FoamFile{{version 2.0;format ascii;class volScalarField;object omega;}} dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f}; boundaryField{{ airfoil{{type omegaWallFunction;value uniform {w0:.4f};}} farfield{{type freestream;freestreamValue uniform {w0:.4f};}} outlet{{type freestream;freestreamValue uniform {w0:.4f};}} frontAndBack{{type empty;}} }}')
(z/"nut").write_text(f'FoamFile{{version 2.0;format ascii;class volScalarField;object nut;}} dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e}; boundaryField{{ airfoil{{type nutLowReWallFunction;value uniform 0;}} farfield{{type calculated;value uniform {nut0:.6e};}} outlet{{type calculated;value uniform {nut0:.6e};}} frontAndBack{{type empty;}} }}')
(case/"constant"/"momentumTransport").write_text('FoamFile{version 2.0;format ascii;class dictionary;location "constant";object momentumTransport;}\nsimulationType RAS; RAS{ model kOmegaSST; turbulence on; printCoeffs on; }')
(case/"constant"/"transportProperties").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object transportProperties;}}\ntransportModel Newtonian; nu {nu};')
(case/"system"/"controlDict").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object controlDict;}}\napplication foamRun; startFrom startTime; startTime 0; stopAt endTime; endTime 3000; deltaT 1; writeControl timeStep; writeInterval 3000; purgeWrite 1; writeFormat binary;\nfunctions{{ forces{{ type forces; libs ("libforces.so"); writeControl timeStep; writeInterval 50; patches ("airfoil"); rho rhoInf; rhoInf {rho}; pRef 0; CofR (0.25 0 0); }} }}')
(case/"system"/"fvSchemes").write_text('FoamFile{version 2.0;format ascii;class dictionary;object fvSchemes;}\nddtSchemes{default steadyState;} gradSchemes{default cellLimited Gauss linear 1;} divSchemes{default none; div(phi,U) bounded Gauss linearUpwindV grad(U); div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear;} laplacianSchemes{default Gauss linear corrected;} interpolationSchemes{default linear;} snGradSchemes{default corrected;} wallDist{method meshWave;}')
(case/"system"/"fvSolution").write_text('FoamFile{version 2.0;format ascii;class dictionary;object fvSolution;}\nsolvers{ p{solver GAMG;tolerance 1e-7;relTol 0.01;smoother DICGaussSeidel;nPreSweeps 0;nPostSweeps 2;nFinestSweeps 2;cacheAgglomeration on;agglomerator faceAreaPair;nCellsInCoarsestLevel 50;mergeLevels 1;} Phi{solver GAMG;tolerance 1e-6;relTol 0.01;smoother DICGaussSeidel;nCellsInCoarsestLevel 50;} "(U|k|omega)"{solver smoothSolver;smoother symGaussSeidel;tolerance 1e-8;relTol 0.05;nSweeps 2;} }\nSIMPLE{nNonOrthogonalCorrectors 2;consistent yes;residualControl{p 1e-6;U 1e-6;}} potentialFlow{nNonOrthogonalCorrectors 5;} relaxationFactors{equations{U 0.3;k 0.2;omega 0.2;}fields{p 0.2;}}')
print(f"CFD alpha={alpha} ...", flush=True)
of("potentialFoam -initialiseUBCs -writep > log.pot 2>&1; foamRun -solver incompressibleFluid > log.run 2>&1", t=3600)
ff=list((case/"postProcessing"/"forces").glob("*/forces.dat"))
if not ff:
    print("FORCES YOK"); sys.exit(1)
ll=[l for l in ff[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
nums=re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
Fx=float(nums[1])+float(nums[4]); Fy=float(nums[2])+float(nums[5])
drag=Fx*math.cos(a)+Fy*math.sin(a); lift=-Fx*math.sin(a)+Fy*math.cos(a)
q=0.5*rho*V**2; S=chord*0.1; Cd,Cl=drag/(q*S),lift/(q*S)
ref={0:(0.0,0.0082),4:(0.452,0.0092),8:(0.862,0.0132)}.get(int(alpha))
out={"alpha":alpha,"R_far":R_far,"nonortho":nonortho,"Cd":round(Cd,5),"Cl":round(Cl,4)}
if ref:
    out["Cl_err_pct"]=round(abs(Cl-ref[0])/(abs(ref[0])+1e-3)*100,1)
    out["Cd_err_pct"]=round(abs(Cd-ref[1])/ref[1]*100,1)
print(json.dumps(out,indent=2))
(case/"result.json").write_text(json.dumps(out,indent=2))
