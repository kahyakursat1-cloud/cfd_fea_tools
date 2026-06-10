"""Valid O-grid mesh'inde turbulans seeding taramasi -> Cd'yi 0.0092'ye otur."""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ogrid_elliptic import build_ogrid, write_polymesh

alpha=4; R=40.0
# mesh bir kez
base=Path("ts_mesh")
if base.exists(): shutil.rmtree(base)
(base/"system").mkdir(parents=True, exist_ok=True)
X,Y,I,nj=build_ogrid(R=R, n_around=260, nj=130, first_cell=8e-6)
write_polymesh(base, X, Y, I, nj)
V,nu,rho,chord=50.0,1.48e-5,1.225,1.0
a=math.radians(alpha); Ux,Uy=V*math.cos(a),V*math.sin(a)

def run(Ipct, ratio):
    case=Path(f"ts_{Ipct}_{ratio}")
    if case.exists(): shutil.rmtree(case)
    shutil.copytree(base, case)
    # turbulans: I% + eddy-visc ratio (nut/nu) -> omega buradan
    k0=1.5*(V*Ipct/100)**2
    nut0=ratio*nu
    w0=k0/nut0
    z=case/"0"; z.mkdir(exist_ok=True)
    def W(n,b): (z/n).write_text(b)
    W("U",f'FoamFile{{version 2.0;format ascii;class volVectorField;object U;}} dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} {Uy} 0); boundaryField{{ airfoil{{type noSlip;}} farfield{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}} frontAndBack{{type empty;}} }}')
    W("p",'FoamFile{version 2.0;format ascii;class volScalarField;object p;} dimensions [0 2 -2 0 0 0 0]; internalField uniform 0; boundaryField{ airfoil{type zeroGradient;} farfield{type freestreamPressure;freestreamValue uniform 0;} frontAndBack{type empty;} }')
    W("k",f'FoamFile{{version 2.0;format ascii;class volScalarField;object k;}} dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e}; boundaryField{{ airfoil{{type kqRWallFunction;value uniform {k0:.6e};}} farfield{{type freestream;freestreamValue uniform {k0:.6e};}} frontAndBack{{type empty;}} }}')
    W("omega",f'FoamFile{{version 2.0;format ascii;class volScalarField;object omega;}} dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f}; boundaryField{{ airfoil{{type omegaWallFunction;value uniform {w0:.4f};}} farfield{{type freestream;freestreamValue uniform {w0:.4f};}} frontAndBack{{type empty;}} }}')
    W("nut",f'FoamFile{{version 2.0;format ascii;class volScalarField;object nut;}} dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e}; boundaryField{{ airfoil{{type nutLowReWallFunction;value uniform 0;}} farfield{{type calculated;value uniform {nut0:.6e};}} frontAndBack{{type empty;}} }}')
    (case/"constant"/"momentumTransport").write_text('FoamFile{version 2.0;format ascii;class dictionary;location "constant";object momentumTransport;}\nsimulationType RAS; RAS{ model kOmegaSST; turbulence on; printCoeffs on; }')
    (case/"constant"/"transportProperties").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object transportProperties;}}\ntransportModel Newtonian; nu {nu};')
    (case/"system"/"controlDict").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object controlDict;}}\napplication foamRun; startFrom startTime; startTime 0; stopAt endTime; endTime 4000; deltaT 1; writeControl timeStep; writeInterval 4000; purgeWrite 1; writeFormat binary;\nfunctions{{ forces{{ type forces; libs ("libforces.so"); writeControl timeStep; writeInterval 100; patches ("airfoil"); rho rhoInf; rhoInf {rho}; pRef 0; CofR (0.25 0 0); }} }}')
    (case/"system"/"fvSchemes").write_text('FoamFile{version 2.0;format ascii;class dictionary;object fvSchemes;}\nddtSchemes{default steadyState;} gradSchemes{default cellLimited Gauss linear 1;} divSchemes{default none; div(phi,U) bounded Gauss linearUpwindV grad(U); div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear;} laplacianSchemes{default Gauss linear limited corrected 0.5;} interpolationSchemes{default linear;} snGradSchemes{default limited corrected 0.5;} wallDist{method meshWave;}')
    (case/"system"/"fvSolution").write_text('FoamFile{version 2.0;format ascii;class dictionary;object fvSolution;}\nsolvers{ p{solver GAMG;tolerance 1e-7;relTol 0.01;smoother DICGaussSeidel;nPreSweeps 0;nPostSweeps 2;nFinestSweeps 2;cacheAgglomeration on;agglomerator faceAreaPair;nCellsInCoarsestLevel 50;mergeLevels 1;} Phi{solver GAMG;tolerance 1e-6;relTol 0.01;smoother DICGaussSeidel;nCellsInCoarsestLevel 50;} "(U|k|omega)"{solver smoothSolver;smoother symGaussSeidel;tolerance 1e-8;relTol 0.05;nSweeps 2;} }\nSIMPLE{nNonOrthogonalCorrectors 3;consistent yes;residualControl{p 1e-6;U 1e-6;}} potentialFlow{nNonOrthogonalCorrectors 8;} relaxationFactors{equations{U 0.3;k 0.2;omega 0.2;}fields{p 0.2;}}')
    p=str(case.resolve()); wsl=f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
    subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && cd {wsl} && potentialFoam -initialiseUBCs -writep >log.pot 2>&1; foamRun -solver incompressibleFluid >log.run 2>&1"',shell=True,capture_output=True,text=True,timeout=3600)
    ff=list((case/"postProcessing"/"forces").glob("*/forces.dat"))
    if not ff: return None
    ll=[l for l in ff[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
    nums=re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
    Fx=float(nums[1])+float(nums[4]); Fy=float(nums[2])+float(nums[5])
    drag=Fx*math.cos(a)+Fy*math.sin(a); lift=-Fx*math.sin(a)+Fy*math.cos(a)
    q=0.5*rho*V**2; S=chord*0.1
    return drag/(q*S), lift/(q*S)

for Ipct,ratio in [(1.0,10),(3.0,50),(5.0,100)]:
    r=run(Ipct,ratio)
    if r:
        Cd,Cl=r
        print(f"I={Ipct}% ratio={ratio:3d}: Cd={Cd:.5f} (ref 0.0092, err={abs(Cd-0.0092)/0.0092*100:.0f}%)  Cl={Cl:.4f} (err={abs(Cl-0.452)/0.452*100:.0f}%)", flush=True)
    else:
        print(f"I={Ipct}% ratio={ratio}: FAILED", flush=True)
