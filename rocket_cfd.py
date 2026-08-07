"""
Roket CFD — Cd(Mach) yuksek-fidelite dogrulama
==============================================
.ork geometrisinden roket STL (ogive burun + govde + 3 fin) uretir,
OpenFOAM ile Cd hesaplar, OpenRocket Barrowman Cd'siyle capraz-dogrular.

Sabit-kanat OpenFOAM yolunun roket karsiligi.
"""

import math
import os
import re
import subprocess
from pathlib import Path

import numpy as np

from analysis.backend import linux_run

# ── Roket geometrisi (.ork'tan) ──────────────────────────────────────────────
NOSE_LEN   = 0.10      # ogive burun (m)
BODY_LEN   = 0.30      # govde (m)
RADIUS     = 0.0125    # govde yaricapi (m) -> cap 25mm
FIN_ROOT   = 0.0508    # fin kok kord (m)
FIN_TIP    = 0.0508    # fin uc kord (dikdortgen)
FIN_SPAN   = 0.030     # fin yuksekligi (m)
FIN_THICK  = 0.002     # fin kalinligi (m)
N_FINS     = 3
S_REF      = math.pi * RADIUS**2   # frontal referans alan (Barrowman ile ayni)

V_FLIGHT   = 29.0      # m/s (OpenRocket coast fazi, ~Mach 0.086)
RHO        = 1.225
NU         = 1.5e-5


def _to_wsl(p: Path):
    p = str(p.resolve())
    return f"/mnt/{p[0].lower()}{p[2:].replace(chr(92), '/')}"


# ARKA UC KATMANI: `wsl bash -c` ELLE kuruluyordu, yani analysis/backend
# devre disiydi ve CFD_BACKEND=docker bu betikte hicbir sey degistirmiyordu.
# Ayni kampanyanin iki yarisi FARKLI cozuculerde kosabilirdi. Case iskeleti
# DEGISMEDI; degisen yalnizca TASIMA katmani.
def _of_cmd(d, cmd):
    return (f"source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && "
            f"cd {d} && {cmd}")


def build_rocket_stl(path: str):
    """Ogive burun + silindir govde + 3 fin -> watertight STL."""
    import trimesh

    n_ax, n_th = 40, 48
    theta = np.linspace(0, 2*np.pi, n_th, endpoint=False)

    # Govde of revolution profili: x ekseni boyunca yaricap r(x)
    # Ogive: x in [0, NOSE_LEN], r = R*sqrt(1-((L-x)/L)^2) yaklasik tangent ogive
    xs, rs = [], []
    nx_nose = 20
    rho_og = (RADIUS**2 + NOSE_LEN**2) / (2*RADIUS)   # ogive radius
    for i in range(nx_nose+1):
        x = NOSE_LEN * i/nx_nose
        r = math.sqrt(max(rho_og**2 - (NOSE_LEN - x)**2, 0)) + RADIUS - rho_og
        xs.append(x); rs.append(max(r, 1e-4))
    nx_body = 20
    for i in range(1, nx_body+1):
        xs.append(NOSE_LEN + BODY_LEN * i/nx_body); rs.append(RADIUS)

    # Revolution mesh
    verts, faces = [], []
    for xi, ri in zip(xs, rs):
        for th in theta:
            verts.append([xi, ri*math.cos(th), ri*math.sin(th)])
    nstn = len(xs)
    for s in range(nstn-1):
        for j in range(n_th):
            a = s*n_th + j
            b = s*n_th + (j+1) % n_th
            c = (s+1)*n_th + j
            d = (s+1)*n_th + (j+1) % n_th
            faces += [[a, b, d], [a, d, c]]
    # Burun ucu + kuyruk kapagi
    tip_i = len(verts); verts.append([xs[0], 0, 0])
    for j in range(n_th):
        faces.append([tip_i, (j+1) % n_th, j])
    tail_i = len(verts); verts.append([xs[-1], 0, 0])
    base = (nstn-1)*n_th
    for j in range(n_th):
        faces.append([tail_i, base+j, base+(j+1) % n_th])

    body = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=True)

    # Finler: aft'ta dikdortgen plakalar, N_FINS adet 120 derece
    # ROCKET_NOFINS=1 → finsiz gövde (fin basınç-drag katkısını izole etmek için V&V).
    fin_x0 = NOSE_LEN + BODY_LEN - FIN_ROOT
    meshes = [body]
    n_fins = 0 if os.environ.get("ROCKET_NOFINS") else N_FINS
    # Çift-kama (diamond) kesit: LE/TE sivri, orta-kord FIN_THICK. Küt-kutu plakaya göre
    # kenar-ayrılması/form-drag'ı ÇOK daha düşük (V&V: küt-kutu CFD Cd'yi ~%60 şişiriyordu,
    # finsiz gövde OpenRocket'le %9; airfoiled fin Barrowman'a yakınsar).
    x0, xm, x1 = fin_x0, fin_x0 + FIN_ROOT/2, fin_x0 + FIN_ROOT
    zr, zt, ht = RADIUS, RADIUS + FIN_SPAN, FIN_THICK/2
    fv = [[x0, 0, zr], [xm, ht, zr], [x1, 0, zr], [xm, -ht, zr],
          [x0, 0, zt], [xm, ht, zt], [x1, 0, zt], [xm, -ht, zt]]
    ff = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],          # kök + uç kapağı
          [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],          # yan yüzeyler
          [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    for k in range(n_fins):
        ang = 2*math.pi*k/N_FINS
        fin = trimesh.Trimesh(vertices=np.array(fv, dtype=float), faces=np.array(ff),
                              process=True)
        fin.fix_normals()                          # dışa-dönük normaller (snappy doğru tarafı mesh'lesin)
        fin.apply_transform(trimesh.transformations.rotation_matrix(ang, [1, 0, 0]))
        meshes.append(fin)

    rocket = trimesh.util.concatenate(meshes)
    rocket.export(path)
    return rocket


def setup_and_run(case_dir: Path) -> dict:
    """OpenFOAM case kur, calistir, Cd dondur."""
    for sub in ("0", "constant/triSurface", "system"):
        (case_dir/sub).mkdir(parents=True, exist_ok=True)
    stl = case_dir/"constant"/"triSurface"/"rocket.stl"
    build_rocket_stl(str(stl))

    L = NOSE_LEN + BODY_LEN
    # Domain: roketi cevreleyen kutu
    xmin, xmax = -0.15, L + 0.45
    yz = 0.20
    nx, nyz = 60, 40
    (case_dir/"system"/"blockMeshDict").write_text(f"""FoamFile{{ version 2.0; format ascii; class dictionary; object blockMeshDict; }}
convertToMeters 1;
vertices (
 ({xmin} {-yz} {-yz}) ({xmax} {-yz} {-yz}) ({xmax} {yz} {-yz}) ({xmin} {yz} {-yz})
 ({xmin} {-yz} {yz}) ({xmax} {-yz} {yz}) ({xmax} {yz} {yz}) ({xmin} {yz} {yz}) );
blocks ( hex (0 1 2 3 4 5 6 7) ({nx} {nyz} {nyz}) simpleGrading (1 1 1) );
boundary (
  inlet  {{ type patch; faces ((0 4 7 3)); }}
  outlet {{ type patch; faces ((1 2 6 5)); }}
  walls  {{ type patch; faces ((0 1 5 4)(3 7 6 2)(0 3 2 1)(4 5 6 7)); }} );
""")
    (case_dir/"system"/"surfaceFeaturesDict").write_text(
        'FoamFile{ version 2.0; format ascii; class dictionary; object surfaceFeaturesDict; }\n'
        'surfaces ("rocket.stl"); includedAngle 150;\n')
    loc = f"{xmin+0.05} 0.05 0.05"
    (case_dir/"system"/"snappyHexMeshDict").write_text(f"""FoamFile{{ version 2.0; format ascii; class dictionary; object snappyHexMeshDict; }}
castellatedMesh true; snap true; addLayers true;
geometry {{ rocket.stl {{ type triSurfaceMesh; name rocket; }} }}
castellatedMeshControls {{ maxLocalCells 2000000; maxGlobalCells 6000000;
  minRefinementCells 10; nCellsBetweenLevels 3; resolveFeatureAngle 30;
  features ( {{ file "rocket.eMesh"; level 5; }} );
  refinementSurfaces {{ rocket {{ level (5 6); patchInfo {{ type wall; }} }} }}
  refinementRegions {{ }} locationInMesh ({loc}); allowFreeStandingZoneFaces true; }}
snapControls {{ nSmoothPatch 3; tolerance 4.0; nSolveIter 100; nRelaxIter 5;
  nFeatureSnapIter 10; implicitFeatureSnap false; explicitFeatureSnap true; multiRegionFeatureSnap false; }}
addLayersControls {{ relativeSizes true; layers {{ "rocket.*" {{ nSurfaceLayers 8; }} }}
  expansionRatio 1.2; finalLayerThickness 0.35; minThickness 0.02; nGrow 0; featureAngle 130;
  nRelaxIter 5; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10;
  maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.6; minMedianAxisAngle 90;
  nBufferCellsNoExtrude 0; nLayerIter 50; nRelaxedIter 20; }}
meshQualityControls {{ maxNonOrtho 70; maxBoundarySkewness 20; maxInternalSkewness 4;
  maxConcave 80; minFlatness 0.5; minVol 1e-13; minTetQuality -1e30; minArea -1;
  minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.02; minVolRatio 0.01;
  minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75;
  relaxed {{ maxNonOrtho 75; minVol 1e-14; minTetQuality -1e30; minTwist 0.001;
    minDeterminant 0.0001; minVolRatio 0.001; }} }}
writeFlags ( ); mergeTolerance 1e-6;
""")
    (case_dir/"system"/"controlDict").write_text(f"""FoamFile{{ version 2.0; format ascii; class dictionary; object controlDict; }}
application foamRun; startFrom startTime; startTime 0; endTime 600;
deltaT 1; writeInterval 600; purgeWrite 2; writeFormat binary; runTimeModifiable true;
functions {{ forces {{ type forces; libs ("libforces.so"); writeControl timeStep; writeInterval 50;
  patches ("rocket"); rho rhoInf; rhoInf {RHO}; pRef 0; CofR (0 0 0); }} }}
""")
    (case_dir/"system"/"fvSchemes").write_text("""FoamFile{ version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes{ default steadyState; }
gradSchemes{ default cellLimited Gauss linear 1; }
divSchemes{ default none; div(phi,U) bounded Gauss linearUpwindV grad(U);
  div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;
  div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes{ default Gauss linear corrected; }
interpolationSchemes{ default linear; } snGradSchemes{ default corrected; }
wallDist{ method meshWave; }""")
    # residualControl bu küt-taban roketinde 1e-6'ya inmez (iz salınımı → taban ~5e-5); ama
    # eksenel KUVVET (Cd) iter ~500'de konverje → endTime 600 force-yeterli. residual gevşek backstop.
    (case_dir/"system"/"fvSolution").write_text("""FoamFile{ version 2.0; format ascii; class dictionary; object fvSolution; }
solvers{ p{ solver GAMG; tolerance 1e-7; relTol 0.05; smoother GaussSeidel; nCellsInCoarsestLevel 20; }
  "(U|k|omega)"{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.05; } }
SIMPLE{ nNonOrthogonalCorrectors 2; consistent yes; residualControl{ p 1e-5; U 1e-5; } }
relaxationFactors{ equations{ U 0.7; k 0.5; omega 0.5; } fields{ p 0.3; } }""")
    (case_dir/"constant").mkdir(exist_ok=True)
    (case_dir/"constant"/"momentumTransport").write_text(
        'FoamFile{ version 2.0; format ascii; class dictionary; location "constant"; object momentumTransport; }\n'
        'simulationType RAS; RAS{ model kOmegaSST; turbulence on; printCoeffs on; }')
    (case_dir/"constant"/"transportProperties").write_text(
        f'FoamFile{{ version 2.0; format ascii; class dictionary; object transportProperties; }}\ntransportModel Newtonian; nu {NU};')

    I = 0.05; Lt = 0.07*2*RADIUS
    k0 = 1.5*(V_FLIGHT*I)**2; w0 = math.sqrt(k0)/(0.09**0.25*Lt); nut0 = k0/w0
    z = case_dir/"0"
    z.joinpath("U").write_text(f"""FoamFile{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({V_FLIGHT} 0 0);
boundaryField{{ inlet{{type fixedValue; value uniform ({V_FLIGHT} 0 0);}}
  outlet{{type inletOutlet; inletValue uniform (0 0 0); value uniform ({V_FLIGHT} 0 0);}}
  walls{{type slip;}} rocket{{type noSlip;}} }}""")
    z.joinpath("p").write_text("""FoamFile{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField{ inlet{type zeroGradient;} outlet{type fixedValue; value uniform 0;} walls{type zeroGradient;} rocket{type zeroGradient;} }""")
    z.joinpath("k").write_text(f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e};
boundaryField{{ inlet{{type fixedValue; value uniform {k0:.6e};}} outlet{{type inletOutlet; inletValue uniform {k0:.6e}; value uniform {k0:.6e};}}
  walls{{type zeroGradient;}} rocket{{type kqRWallFunction; value uniform {k0:.6e};}} }}""")
    z.joinpath("omega").write_text(f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f};
boundaryField{{ inlet{{type fixedValue; value uniform {w0:.4f};}} outlet{{type inletOutlet; inletValue uniform {w0:.4f}; value uniform {w0:.4f};}}
  walls{{type zeroGradient;}} rocket{{type omegaWallFunction; value uniform {w0:.4f};}} }}""")
    z.joinpath("nut").write_text(f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e};
boundaryField{{ inlet{{type calculated; value uniform {nut0:.6e};}} outlet{{type calculated; value uniform {nut0:.6e};}}
  walls{{type calculated; value uniform {nut0:.6e};}} rocket{{type nutkWallFunction; value uniform 0;}} }}""")

    d = _to_wsl(case_dir)
    for cmd, t in [("blockMesh > log.bm 2>&1", 300),
                   ("surfaceFeatures > log.sf 2>&1", 120),
                   ("snappyHexMesh -overwrite > log.snap 2>&1", 1800),
                   ("foamRun -solver incompressibleFluid > log.run 2>&1", 3600)]:
        rc = linux_run(_of_cmd(d, cmd), t).returncode
        if rc != 0:
            step = cmd.split()[0]
            log = (case_dir/f"log.{cmd.split('>')[1].split('.')[1][:4]}").read_text(errors='replace')[-400:] if False else ""
            return {"status": "FAILED", "step": step}

    ff = list((case_dir/"postProcessing"/"forces").glob("*/forces.dat"))
    if not ff:
        return {"status": "FAILED", "step": "forces"}
    lines = [l for l in ff[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
    nums = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', lines[-1])
    Fpx, Fvx = float(nums[1]), float(nums[4])   # basınç + viskoz eksenel bileşen
    Fx = Fpx + Fvx                              # toplam eksenel = drag
    q = 0.5*RHO*V_FLIGHT**2
    cd = Fx/(q*S_REF)
    # V&V-yorumlanabilirlik: Cd kırılımı. friction ∝ S_wet/S_ref (ince gövde ~56 → yüksek ama
    # fiziksel); OpenRocket/Barrowman ile fark genelde BASINÇ-drag'ında (fin+küt-taban modeli).
    return {"status": "SUCCESS", "drag_N": round(Fx, 5),
            "Cd_cfd": round(cd, 4), "Cd_pressure": round(Fpx/(q*S_REF), 4),
            "Cd_friction": round(Fvx/(q*S_REF), 4),
            "V_ms": V_FLIGHT, "S_ref_m2": round(S_REF, 6), "q_Pa": round(q, 2)}


if __name__ == "__main__":
    import json
    case = Path("rocket_cfd_case")
    print("[Rocket CFD] STL + OpenFOAM basliyor...", flush=True)
    r = setup_and_run(case)
    print(json.dumps(r, indent=2), flush=True)
    if r.get("status") == "SUCCESS":
        # OpenRocket Cd ile capraz-dogrula
        orf = Path("openrocket_result.json")
        if orf.exists():
            cd_or = json.loads(orf.read_text()).get("cd_at_burnout")
            if cd_or:
                err = abs(r["Cd_cfd"] - cd_or)/cd_or*100
                r["Cd_openrocket"] = cd_or
                r["cross_val_err_pct"] = round(err, 1)
                print(f"\nCd_CFD={r['Cd_cfd']} vs Cd_OpenRocket={cd_or} -> %{err:.0f} fark", flush=True)
        json.dump(r, open("rocket_cfd_result.json", "w"), indent=2)
        print("Kaydedildi: rocket_cfd_result.json", flush=True)
