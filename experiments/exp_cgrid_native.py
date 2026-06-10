"""Native C-grid (cgrid_generator) deneyi — R_far=50 buyuk domain, y+~1, dogru wake topolojisi.
Construct2D'nin domain limitini bypass eder. CFD: kOmegaSST, outlet patch dahil.
"""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from cgrid_generator import generate

alpha = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
case = Path("cgrid_native")
if case.exists():
    shutil.rmtree(case)

# --- 1) Buyuk-domain y+~1 C-grid uret ---
print("C-grid uretiliyor (R_far=50, wake=30, nj=120, first=8um, LE yogun)...", flush=True)
msh, dims = generate(str(case), naca="0012",
                     R_far=50.0, wake_len=30.0, nj=120, first_cell=8e-6,
                     n_half=130, nw=80)
print(f"  dims(I,nj)={dims}", flush=True)

p = str(case.resolve()); wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
def of(cmd, t=900):
    return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && cd {wsl} && {cmd}"',
                          shell=True, capture_output=True, text=True, timeout=t)

of("gmshToFoam cgrid.msh > log.g2f 2>&1")
of("checkMesh > log.check 2>&1")
chk = (case/"log.check").read_text(errors="replace")
nonortho = None
for key in ["cells:", "non-orthogonality Max", "Max skewness", "Max aspect ratio", "Mesh OK", "FAILED"]:
    for line in chk.splitlines():
        if key in line:
            print("  " + line.strip(), flush=True)
            if "non-orthogonality Max" in line:
                m = re.search(r"Max:\s*([\d.]+)", line)
                if m: nonortho = float(m.group(1))
            break

# --- 2) CFD kurulumu (airfoil/farfield/outlet/frontAndBack) ---
V, nu, rho, chord = 50.0, 1.48e-5, 1.225, 1.0
a = math.radians(alpha)
Ux, Uy = V*math.cos(a), V*math.sin(a)
I = 0.0018; Lt = 0.07*chord
k0 = 1.5*(V*I)**2; w0 = math.sqrt(k0)/(0.09**0.25*Lt); nut0 = k0/w0
z = case/"0"; z.mkdir(exist_ok=True)

def fa(name, body): (z/name).write_text(body)
fa("U", f"""FoamFile{{version 2.0; format ascii; class volVectorField; object U;}}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} {Uy} 0);
boundaryField{{ airfoil{{type noSlip;}}
 farfield{{type freestreamVelocity; freestreamValue uniform ({Ux} {Uy} 0);}}
 outlet{{type freestreamVelocity; freestreamValue uniform ({Ux} {Uy} 0);}}
 frontAndBack{{type empty;}} }}""")
fa("p", """FoamFile{version 2.0; format ascii; class volScalarField; object p;}
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField{ airfoil{type zeroGradient;}
 farfield{type freestreamPressure; freestreamValue uniform 0;}
 outlet{type freestreamPressure; freestreamValue uniform 0;}
 frontAndBack{type empty;} }""")
fa("k", f"""FoamFile{{version 2.0; format ascii; class volScalarField; object k;}}
dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e};
boundaryField{{ airfoil{{type kqRWallFunction; value uniform {k0:.6e};}}
 farfield{{type freestream; freestreamValue uniform {k0:.6e};}}
 outlet{{type freestream; freestreamValue uniform {k0:.6e};}}
 frontAndBack{{type empty;}} }}""")
fa("omega", f"""FoamFile{{version 2.0; format ascii; class volScalarField; object omega;}}
dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f};
boundaryField{{ airfoil{{type omegaWallFunction; value uniform {w0:.4f};}}
 farfield{{type freestream; freestreamValue uniform {w0:.4f};}}
 outlet{{type freestream; freestreamValue uniform {w0:.4f};}}
 frontAndBack{{type empty;}} }}""")
fa("nut", f"""FoamFile{{version 2.0; format ascii; class volScalarField; object nut;}}
dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e};
boundaryField{{ airfoil{{type nutLowReWallFunction; value uniform 0;}}
 farfield{{type calculated; value uniform {nut0:.6e};}}
 outlet{{type calculated; value uniform {nut0:.6e};}}
 frontAndBack{{type empty;}} }}""")

(case/"constant"/"momentumTransport").write_text(
    'FoamFile{version 2.0; format ascii; class dictionary; location "constant"; object momentumTransport;}\n'
    'simulationType RAS; RAS{ model kOmegaSST; turbulence on; printCoeffs on; }')
(case/"constant"/"transportProperties").write_text(
    f'FoamFile{{version 2.0; format ascii; class dictionary; object transportProperties;}}\ntransportModel Newtonian; nu {nu};')
(case/"system"/"controlDict").write_text(f"""FoamFile{{version 2.0; format ascii; class dictionary; object controlDict;}}
application foamRun; startFrom startTime; startTime 0; stopAt endTime; endTime 3000;
deltaT 1; writeControl timeStep; writeInterval 3000; purgeWrite 1; writeFormat binary;
functions{{ forces{{ type forces; libs ("libforces.so"); writeControl timeStep; writeInterval 50;
  patches ("airfoil"); rho rhoInf; rhoInf {rho}; pRef 0; CofR (0.25 0 0); }} }}""")
(case/"system"/"fvSchemes").write_text("""FoamFile{version 2.0; format ascii; class dictionary; object fvSchemes;}
ddtSchemes{ default steadyState; } gradSchemes{ default cellLimited Gauss linear 1; }
divSchemes{ default none; div(phi,U) bounded Gauss linearUpwindV grad(U);
 div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;
 div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes{ default Gauss linear corrected; } interpolationSchemes{ default linear; }
snGradSchemes{ default corrected; } wallDist{ method meshWave; }""")
(case/"system"/"fvSolution").write_text("""FoamFile{version 2.0; format ascii; class dictionary; object fvSolution;}
solvers{
 p{ solver GAMG; tolerance 1e-7; relTol 0.01; smoother DICGaussSeidel; nPreSweeps 0; nPostSweeps 2;
    nFinestSweeps 2; cacheAgglomeration on; agglomerator faceAreaPair; nCellsInCoarsestLevel 50; mergeLevels 1; }
 Phi{ solver GAMG; tolerance 1e-6; relTol 0.01; smoother DICGaussSeidel; nCellsInCoarsestLevel 50; }
 "(U|k|omega)"{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.05; nSweeps 2; } }
SIMPLE{ nNonOrthogonalCorrectors 2; consistent yes; residualControl{ p 1e-6; U 1e-6; } }
potentialFlow{ nNonOrthogonalCorrectors 5; }
relaxationFactors{ equations{ U 0.3; k 0.2; omega 0.2; } fields{ p 0.2; } }""")

print(f"CFD alpha={alpha} ...", flush=True)
of("potentialFoam -initialiseUBCs -writep > log.pot 2>&1; foamRun -solver incompressibleFluid > log.run 2>&1", t=3600)

ff = list((case/"postProcessing"/"forces").glob("*/forces.dat"))
if not ff:
    print("FORCES YOK — solver basarisiz olabilir"); print(json.dumps({"nonortho": nonortho})); sys.exit(1)
lines = [l for l in ff[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
nums = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', lines[-1])
Fx = float(nums[1])+float(nums[4]); Fy = float(nums[2])+float(nums[5])
drag = Fx*math.cos(a)+Fy*math.sin(a); lift = -Fx*math.sin(a)+Fy*math.cos(a)
q = 0.5*rho*V**2; S = chord*0.1
Cd, Cl = drag/(q*S), lift/(q*S)
ref = {0:(0.0,0.0082),4:(0.452,0.0092),8:(0.862,0.0132)}.get(int(alpha))
out = {"alpha": alpha, "nonortho": nonortho, "Cd": round(Cd,5), "Cl": round(Cl,4)}
if ref:
    out["Cl_ref"], out["Cd_ref"] = ref
    out["Cl_err_pct"] = round(abs(Cl-ref[0])/(abs(ref[0])+1e-3)*100, 1)
    out["Cd_err_pct"] = round(abs(Cd-ref[1])/ref[1]*100, 1)
print(json.dumps(out, indent=2))
(case/"result.json").write_text(json.dumps(out, indent=2))
