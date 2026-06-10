"""Valid O-grid + kOmegaSSTLM gecis modeli (2-asamali). Free-transition fizigi."""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ogrid_elliptic import build_ogrid, write_polymesh

alphas=[int(x) for x in sys.argv[1:]] or [0,4,8]
R=40.0; V,nu,rho,chord=50.0,1.48e-5,1.225,1.0
base=Path("tr_mesh")
if base.exists(): shutil.rmtree(base)
(base/"system").mkdir(parents=True, exist_ok=True)
X,Y,I,nj=build_ogrid(R=R,n_around=260,nj=130,first_cell=8e-6)
write_polymesh(base,X,Y,I,nj)

def setup(case,alpha):
    a=math.radians(alpha); Ux,Uy=V*math.cos(a),V*math.sin(a)
    It=0.0018; Lt=0.07; k0=1.5*(V*It)**2; w0=math.sqrt(k0)/(0.09**0.25*Lt); nut0=k0/w0
    z=case/"0"; z.mkdir(exist_ok=True)
    def W(n,b):(z/n).write_text(b)
    W("U",f'FoamFile{{version 2.0;format ascii;class volVectorField;object U;}} dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} {Uy} 0); boundaryField{{ airfoil{{type noSlip;}} farfield{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}} frontAndBack{{type empty;}} }}')
    W("p",'FoamFile{version 2.0;format ascii;class volScalarField;object p;} dimensions [0 2 -2 0 0 0 0]; internalField uniform 0; boundaryField{ airfoil{type zeroGradient;} farfield{type freestreamPressure;freestreamValue uniform 0;} frontAndBack{type empty;} }')
    W("k",f'FoamFile{{version 2.0;format ascii;class volScalarField;object k;}} dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e}; boundaryField{{ airfoil{{type kqRWallFunction;value uniform {k0:.6e};}} farfield{{type freestream;freestreamValue uniform {k0:.6e};}} frontAndBack{{type empty;}} }}')
    W("omega",f'FoamFile{{version 2.0;format ascii;class volScalarField;object omega;}} dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f}; boundaryField{{ airfoil{{type omegaWallFunction;value uniform {w0:.4f};}} farfield{{type freestream;freestreamValue uniform {w0:.4f};}} frontAndBack{{type empty;}} }}')
    W("nut",f'FoamFile{{version 2.0;format ascii;class volScalarField;object nut;}} dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e}; boundaryField{{ airfoil{{type nutLowReWallFunction;value uniform 0;}} farfield{{type calculated;value uniform {nut0:.6e};}} frontAndBack{{type empty;}} }}')
    W("gammaInt",'FoamFile{version 2.0;format ascii;class volScalarField;object gammaInt;} dimensions [0 0 0 0 0 0 0]; internalField uniform 1; boundaryField{ airfoil{type zeroGradient;} farfield{type inletOutlet;inletValue uniform 1;value uniform 1;} frontAndBack{type empty;} }')
    W("ReThetat",'FoamFile{version 2.0;format ascii;class volScalarField;object ReThetat;} dimensions [0 0 0 0 0 0 0]; internalField uniform 100; boundaryField{ airfoil{type zeroGradient;} farfield{type inletOutlet;inletValue uniform 100;value uniform 100;} frontAndBack{type empty;} }')
    (case/"constant"/"transportProperties").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object transportProperties;}}\ntransportModel Newtonian; nu {nu};')
    (case/"system"/"fvSchemes").write_text('FoamFile{version 2.0;format ascii;class dictionary;object fvSchemes;}\nddtSchemes{default steadyState;} gradSchemes{default cellLimited Gauss linear 1;} divSchemes{default none; div(phi,U) bounded Gauss linearUpwindV grad(U); div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind; div(phi,gammaInt) bounded Gauss upwind; div(phi,ReThetat) bounded Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear;} laplacianSchemes{default Gauss linear limited corrected 0.33;} interpolationSchemes{default linear;} snGradSchemes{default limited corrected 0.33;} wallDist{method meshWave;}')
    (case/"system"/"fvSolution").write_text('FoamFile{version 2.0;format ascii;class dictionary;object fvSolution;}\nsolvers{ p{solver GAMG;tolerance 1e-7;relTol 0.05;smoother DICGaussSeidel;nCellsInCoarsestLevel 20;} Phi{solver GAMG;tolerance 1e-6;relTol 0.01;smoother DICGaussSeidel;nCellsInCoarsestLevel 20;} "(U|k|omega|gammaInt|ReThetat)"{solver smoothSolver;smoother symGaussSeidel;tolerance 1e-8;relTol 0.05;nSweeps 2;} }\nSIMPLE{nNonOrthogonalCorrectors 6;consistent yes;residualControl{p 1e-6;U 1e-6;}} potentialFlow{nNonOrthogonalCorrectors 8;} relaxationFactors{equations{U 0.3;k 0.2;omega 0.2;gammaInt 0.2;ReThetat 0.2;}fields{p 0.15;}}')

def ctrl(case,model,end):
    (case/"constant"/"momentumTransport").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;location "constant";object momentumTransport;}}\nsimulationType RAS; RAS{{ model {model}; turbulence on; printCoeffs on; }}')
    sf="startTime" if model=="kOmegaSST" else "latestTime"
    (case/"system"/"controlDict").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object controlDict;}}\napplication foamRun; startFrom {sf}; startTime 0; stopAt endTime; endTime {end}; deltaT 1; writeControl timeStep; writeInterval {end}; purgeWrite 1; writeFormat binary;\nfunctions{{ forces{{ type forces; libs ("libforces.so"); writeControl timeStep; writeInterval 100; patches ("airfoil"); rho rhoInf; rhoInf {rho}; pRef 0; CofR (0.25 0 0); }} }}')

ref_free={0:(0.0,0.0055),4:(0.44,0.0064),8:(0.85,0.0095)}
results={}
for alpha in alphas:
    case=Path(f"tr_{alpha}")
    if case.exists(): shutil.rmtree(case)
    shutil.copytree(base,case)
    setup(case,alpha)
    p=str(case.resolve()); wsl=f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
    def of(cmd,t=2400,wsl=wsl): return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && cd {wsl} && {cmd}"',shell=True,capture_output=True,text=True,timeout=t)
    # Asama 1: kOmegaSST (akisi kur)
    ctrl(case,"kOmegaSST",2000)
    of("potentialFoam -initialiseUBCs -writep >log.pot 2>&1; foamRun -solver incompressibleFluid >log.s1 2>&1")
    # Asama 2: kOmegaSSTLM gecis modeli — restart zamaninda gammaInt/ReThetat yok, 0/'dan tasi
    lt=max((d for d in case.iterdir() if d.is_dir() and d.name!="0" and d.name.replace(".","",1).isdigit()),key=lambda d:float(d.name),default=None)
    if lt is None:
        print(f"alpha={alpha}: STAGE1 FAIL",flush=True); results[alpha]={"status":"stage1_failed"}; continue
    for fld in ("gammaInt","ReThetat"): shutil.copy(case/"0"/fld, lt/fld)
    ctrl(case,"kOmegaSSTLM",4000)
    of("foamRun -solver incompressibleFluid >log.s2 2>&1")
    if "FOAM FATAL" in (case/"log.s2").read_text(errors="ignore"):
        print(f"alpha={alpha}: STAGE2 FATAL",flush=True); results[alpha]={"status":"stage2_failed"}; continue
    ff=sorted((case/"postProcessing"/"forces").glob("*/forces.dat"),key=lambda f:float(f.parent.name))
    if not ff:
        print(f"alpha={alpha}: FORCES YOK",flush=True); continue
    ll=[l for l in ff[-1].read_text().splitlines() if l.strip() and not l.startswith("#")]
    nums=re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
    Fx=float(nums[1])+float(nums[4]); Fy=float(nums[2])+float(nums[5])
    a=math.radians(alpha); drag=Fx*math.cos(a)+Fy*math.sin(a); lift=-Fx*math.sin(a)+Fy*math.cos(a)
    q=0.5*rho*V**2; S=chord*0.1; Cd,Cl=drag/(q*S),lift/(q*S)
    if not (math.isfinite(Cd) and abs(Cd)<0.5):
        print(f"alpha={alpha}: DIVERGED Cd={Cd:.3g}",flush=True); results[alpha]={"status":f"diverged Cd={Cd:.3g}"}; continue
    clf,cdf=ref_free[alpha]
    ecl=abs(Cl-clf)/(abs(clf)+1e-3)*100; ecd=abs(Cd-cdf)/cdf*100
    results[alpha]={"Cl":round(Cl,4),"Cd":round(Cd,5),"errCl":round(ecl,1),"errCd":round(ecd,1)}
    print(f"alpha={alpha}: Cd={Cd:.5f} (free-ref {cdf}, err={ecd:.0f}%)  Cl={Cl:.4f} (ref {clf}, err={ecl:.0f}%)",flush=True)
Path("transition_results.json").write_text(json.dumps(results,indent=2))
