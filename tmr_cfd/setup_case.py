"""TMR NACA0012 OpenFOAM case üreteci — tam-türbülans kOmegaSST, y⁺<1 wall-resolved.
0/ + constant/ + system/ dosyalarını yazar. Mesh (constant/polyMesh) plot3dToFoam+
createPatch'ten gelmeli; patch'ler: airfoil(wall) farfield(patch) frontAndBack(empty).
Birim-kiriş, U=1, ν=1/Re; 2D düzlem X-Z (kiriş X, lift Z, span Y=empty, kalınlık 1).
Kullanım: python setup_case.py <case_dir> <alpha_deg> [Re] [endTime]
"""
import math
import sys
from pathlib import Path

case = Path(sys.argv[1])
alpha = float(sys.argv[2])
Re = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0e6
endTime = int(sys.argv[4]) if len(sys.argv) > 4 else 5000

U = 1.0
nu = U * 1.0 / Re                         # c=1 → Re=U·c/ν
a = math.radians(alpha)
Ux, Uz = U * math.cos(a), U * math.sin(a)   # lift Z yönünde
# düşük freestream türbülans (TMR pratiği): Ti=0.1%, nut/nu≈0.009
k0 = 1.5 * (U * 0.001) ** 2
nutr = 0.009
omega0 = k0 / (nutr * nu)
nut0 = k0 / omega0
# forceCoeffs: drag/lift yönleri α ile döner
dragDir = (math.cos(a), 0.0, math.sin(a))
liftDir = (-math.sin(a), 0.0, math.cos(a))

for d in ("0", "constant", "system"):
    (case / d).mkdir(parents=True, exist_ok=True)


def W(rel, body):
    (case / rel).write_text(body)


def field(obj, dims, internal, bc):
    return (f"FoamFile{{version 2.0;format ascii;class {('volVectorField' if obj=='U' else 'volScalarField')};"
            f"object {obj};}}\ndimensions {dims};\ninternalField uniform {internal};\n"
            f"boundaryField{{\n{bc}\n}}\n")


# ── 0/ alanları ──
W("0/U", field("U", "[0 1 -1 0 0 0 0]", f"({Ux} 0 {Uz})",
    f"  airfoil {{ type noSlip; }}\n"
    f"  farfield {{ type freestreamVelocity; freestreamValue uniform ({Ux} 0 {Uz}); }}\n"
    f"  frontAndBack {{ type empty; }}"))
W("0/p", field("p", "[0 2 -2 0 0 0 0]", "0",
    "  airfoil { type zeroGradient; }\n"
    "  farfield { type freestreamPressure; freestreamValue uniform 0; }\n"
    "  frontAndBack { type empty; }"))
W("0/k", field("k", "[0 2 -2 0 0 0 0]", f"{k0:.6e}",
    f"  airfoil {{ type kLowReWallFunction; value uniform {k0:.6e}; }}\n"
    f"  farfield {{ type freestream; freestreamValue uniform {k0:.6e}; }}\n"
    f"  frontAndBack {{ type empty; }}"))
W("0/omega", field("omega", "[0 0 -1 0 0 0 0]", f"{omega0:.6e}",
    f"  airfoil {{ type omegaWallFunction; value uniform {omega0:.6e}; }}\n"
    f"  farfield {{ type freestream; freestreamValue uniform {omega0:.6e}; }}\n"
    f"  frontAndBack {{ type empty; }}"))
W("0/nut", field("nut", "[0 2 -1 0 0 0 0]", f"{nut0:.6e}",
    "  airfoil { type nutLowReWallFunction; value uniform 0; }\n"
    f"  farfield {{ type calculated; value uniform {nut0:.6e}; }}\n"
    "  frontAndBack { type empty; }"))

# ── constant/ ──
W("constant/transportProperties",
  "FoamFile{version 2.0;format ascii;class dictionary;object transportProperties;}\n"
  f"transportModel Newtonian;\nnu {nu:.8e};\n")
W("constant/momentumTransport",
  "FoamFile{version 2.0;format ascii;class dictionary;location \"constant\";object momentumTransport;}\n"
  "simulationType RAS;\nRAS{ model kOmegaSST; turbulence on; printCoeffs on; }\n")

# ── system/ ──
W("system/controlDict",
  "FoamFile{version 2.0;format ascii;class dictionary;object controlDict;}\n"
  "application foamRun;\nstartFrom latestTime;\nstartTime 0;\nstopAt endTime;\n"
  f"endTime {endTime};\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval {endTime};\n"
  "purgeWrite 1;\nwriteFormat binary;\nrunTimeModifiable yes;\n"
  "functions{\n"
  "  forceCoeffs{ type forceCoeffs; libs (\"libforces.so\"); writeControl timeStep;\n"
  "    writeInterval 50; patches (airfoil); rho rhoInf; rhoInf 1; magUInf 1; lRef 1; Aref 1;\n"
  f"    dragDir ({dragDir[0]:.6f} {dragDir[1]:.1f} {dragDir[2]:.6f});\n"
  f"    liftDir ({liftDir[0]:.6f} {liftDir[1]:.1f} {liftDir[2]:.6f});\n"
  "    CofR (0.25 0 0); pitchAxis (0 1 0); }\n}\n")
W("system/fvSchemes",
  "FoamFile{version 2.0;format ascii;class dictionary;object fvSchemes;}\n"
  "ddtSchemes{ default steadyState; }\n"
  "gradSchemes{ default Gauss linear; }\n"
  "divSchemes{ default none; div(phi,U) bounded Gauss linearUpwindV grad(U);\n"
  "  div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;\n"
  "  div((nuEff*dev2(T(grad(U))))) Gauss linear; }\n"
  "laplacianSchemes{ default Gauss linear corrected; }\n"
  "interpolationSchemes{ default linear; }\n"
  "snGradSchemes{ default corrected; }\nwallDist{ method meshWave; }\n")
W("system/fvSolution",
  "FoamFile{version 2.0;format ascii;class dictionary;object fvSolution;}\n"
  "solvers{\n"
  "  p{ solver GAMG; tolerance 1e-8; relTol 0.01; smoother GaussSeidel; }\n"
  "  \"(U|k|omega)\"{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-9; relTol 0.01; nSweeps 2; }\n"
  "}\n"
  "SIMPLE{ nNonOrthogonalCorrectors 2; consistent yes;\n"
  # residual 1e-7: 1e-6'da KUVVET henüz platoya oturmuyor (özellikle α≥10 stall-yakını);
  # residual-yakınsama ≠ kuvvet-yakınsama. Sıkı eşik kuvveti oturtur (Cl/Cd drift→0).
  "  residualControl{ p 1e-7; U 1e-7; \"(k|omega)\" 1e-7; } }\n"
  "relaxationFactors{ equations{ U 0.7; \"(k|omega)\" 0.7; } fields{ p 0.3; } }\n")

print(f"Case kuruldu: {case} | α={alpha}° Re={Re:.1e} ν={nu:.4e} | "
      f"k0={k0:.3e} omega0={omega0:.1f} | endTime={endTime}")
