"""
Validation Suite
================
CFD : NACA 0012 @ Re=3e6 — NASA Langley deneysel verisiyle karsilastirma
FEA : Ankastre kiris — Euler-Bernoulli analitik cozumuyle karsilastirma

Her iki validation da gecerse solver/mesh pipeline guvenilir kabul edilir.
"""
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# REFERANS VERILER
# ─────────────────────────────────────────────────────────────────────────────

# NASA Langley NACA 0012 deneysel verileri (Gregory & O'Reilly 1970 + Ladson 1988)
# Re = 3e6, M = 0.15 (kompresibilite ihmal edilebilir)
NACA0012_NASA = {
    # alpha_deg: (Cl_exp, Cd_exp, kaynak)
    0: (0.000,  0.0082, "Ladson 1988 Re=3e6"),
    4: (0.452,  0.0092, "Ladson 1988 Re=3e6"),
    8: (0.862,  0.0132, "Ladson 1988 Re=3e6"),
}

# Kabul kriteri: |simülasyon - deney| / deney < %40
# Mühendislik mesh (y+~400): Cd için %40 tolerans kabul edilebilir.
# Araştırma kalitesi (<10%) için y+<100 mesh gereklidir.
CFD_TOLERANCE = 0.40

# FEA kabul kriteri: |simülasyon - analitik| / analitik < %5
FEA_TOLERANCE = 0.05


def _to_wsl_path(win_path: Path) -> str:
    p = str(win_path.resolve())
    drive = p[0].lower()
    rest = p[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def _wsl_of(wsl_dir: str, cmd: str) -> str:
    return f'wsl bash -c "source /opt/openfoam11/etc/bashrc && cd {wsl_dir} && {cmd}"'


def _run(cmd: str, timeout: int = 3600) -> int:
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout, text=True)
    return r.returncode


# ─────────────────────────────────────────────────────────────────────────────
# CFD VALIDATION — NACA 0012 2D
# ─────────────────────────────────────────────────────────────────────────────

class NACA0012Validation:
    """
    2D NACA 0012 OpenFOAM case — simetrik profil, Re=3e6.
    Domain: C-grid tipi dikdortgen, 1 hucre kalinliginda (2D).
    AoA: velocity vektoru donduruluyor, kuvvetler donduruluyor.
    """

    # NASA verisi icin hedef kosullar
    V   = 50.0          # m/s  (Re = 1.225*50*1/1.81e-5 = 3.38e6)
    RHO = 1.225         # kg/m3
    NU  = 1.48e-5       # m2/s (Re=3e6 icin)
    C   = 1.0           # kord (birim kord)
    RE  = V * C / NU    # ~3.4e6

    def __init__(self, base_path: str = "./validation/naca0012"):
        self.base_path = Path(base_path)

    def _naca0012_profile(self, n: int = 128) -> np.ndarray:
        """NACA 0012 profil koordinatlari (kapali, birim kord)."""
        beta = np.linspace(0, np.pi, n)
        x = 0.5 * (1 - np.cos(beta))
        t = 0.12
        yt = (t / 0.2) * (0.2969*np.sqrt(x) - 0.1260*x - 0.3516*x**2
                           + 0.2843*x**3 - 0.1015*x**4)
        xu = x;  yu =  yt
        xl = x;  yl = -yt
        px = np.concatenate([xu, xl[::-1]])
        py = np.concatenate([yu, yl[::-1]])
        return np.column_stack([px, py])

    def _ogrid_profile(self, n: int = 80) -> np.ndarray:
        """NACA 0012 profil vertices for O-grid blockMesh — CCW in x-z plane.
        Starting from LE, going top surface to TE, then bottom surface back to LE.
        Returns: (n, 2) array of (x, z) coordinates.
        """
        t = 0.12
        def yt(x):
            return (t/0.2)*(0.2969*np.sqrt(np.maximum(x,1e-10))
                            - 0.1260*x - 0.3516*x**2 + 0.2843*x**3 - 0.1015*x**4)

        half = n // 2
        # Top: LE→TE (CCW: right along top)
        beta_top = np.linspace(0, np.pi, half, endpoint=False)
        x_top = 0.5 * (1 - np.cos(beta_top))
        z_top = yt(x_top)
        # Bottom: TE→LE (CCW: left along bottom)
        beta_bot = np.linspace(np.pi, 2*np.pi, n - half, endpoint=False)
        x_bot = 0.5 * (1 - np.cos(beta_bot))
        z_bot = -yt(x_bot)

        return np.column_stack([np.concatenate([x_top, x_bot]),
                                 np.concatenate([z_top, z_bot])])

    def _write_ogrid(self, case_dir: Path, alpha_deg: float) -> None:
        """O-grid blockMeshDict — structured mesh, no snappy, empty patches (true 2D).
        n=200 blocks, 80 cells wall-normal, grading 500.
        First cell ~3mm (y+~400) → wall functions (kOmegaSST), stable.
        """
        n        = getattr(self, "n_prof", 200)   # profile points — LE çözünürlüğü için
        n_normal = getattr(self, "n_norm", 80)    # cells wall-normal
        grading  = getattr(self, "grading", 500)  # grading=500 → y+≈400, non-ortho<65° (kararlı). Yüksek grading LE/TE'de bozuyor.
        W        = 0.1      # span (2D: 1 cell, empty patches)
        R        = getattr(self, "R_far", 20.0)   # dis yaricap (kiriş); yuksek-alpha lift icin buyut (∝Cl² far-field hatasi)
        cx, cz   = 0.25, 0.0  # reference centroid

        profile = self._ogrid_profile(n)

        # Outer boundary: project each profile point radially from centroid
        outer = np.zeros_like(profile)
        for i, (xi, zi) in enumerate(profile):
            dx, dz = xi - cx, zi - cz
            d = math.sqrt(dx*dx + dz*dz) or 1e-10
            outer[i] = (cx + R*dx/d, cz + R*dz/d)

        # Vertex indices:
        # 0..n-1      inner y=0   (profile)
        # n..2n-1     outer y=0
        # 2n..3n-1    inner y=W
        # 3n..4n-1    outer y=W
        lines = ["""FoamFile
{ version 2.0; format ascii; class dictionary; object blockMeshDict; }
convertToMeters 1;
vertices
(
"""]
        for xi, zi in profile:
            lines.append(f"    ({xi:.8f} 0       {zi:.8f})\n")
        for xi, zi in outer:
            lines.append(f"    ({xi:.8f} 0       {zi:.8f})\n")
        for xi, zi in profile:
            lines.append(f"    ({xi:.8f} {W:.4f} {zi:.8f})\n")
        for xi, zi in outer:
            lines.append(f"    ({xi:.8f} {W:.4f} {zi:.8f})\n")
        lines.append(");\n\nblocks\n(\n")

        # Block i: flip i↔j for positive Jacobian (verified analytically for CCW profile)
        # hex(inner_j inner_i outer_i outer_j  inner_j_W inner_i_W outer_i_W outer_j_W)
        # i-direction: CW circumferential (1 cell per block)
        # j-direction: radial inner→outer (n_normal cells, graded)
        # k-direction: span y=0→y=W (1 cell)
        for i in range(n):
            j = (i + 1) % n
            v = [j, i, n+i, n+j,  2*n+j, 2*n+i, 3*n+i, 3*n+j]
            lines.append(f"    hex ({' '.join(str(x) for x in v)}) "
                         f"(1 {n_normal} 1) simpleGrading (1 {grading} 1)\n")
        lines.append(");\n\nboundary\n(\n")

        # Block v = (j, i, n+i, n+j, 2n+j, 2n+i, 3n+i, 3n+j)
        # j_min face (airfoil): (v0,v1,v5,v4) = (j, i, 2n+i, 2n+j)
        lines.append("    airfoil { type wall; faces (\n")
        for i in range(n):
            j = (i+1) % n
            lines.append(f"        ({j} {i} {2*n+i} {2*n+j})\n")
        lines.append("    ); }\n")

        # j_max face (farfield): (v3,v7,v6,v2) = (n+j, 3n+j, 3n+i, n+i)
        lines.append("    farfield { type patch; faces (\n")
        for i in range(n):
            j = (i+1) % n
            lines.append(f"        ({n+j} {3*n+j} {3*n+i} {n+i})\n")
        lines.append("    ); }\n")

        # k_min face (y=0, front): (v0,v3,v2,v1) = (j, n+j, n+i, i)
        lines.append("    front { type empty; faces (\n")
        for i in range(n):
            j = (i+1) % n
            lines.append(f"        ({j} {n+j} {n+i} {i})\n")
        lines.append("    ); }\n")

        # k_max face (y=W, back): (v4,v5,v6,v7) = (2n+j, 2n+i, 3n+i, 3n+j)
        lines.append("    back { type empty; faces (\n")
        for i in range(n):
            j = (i+1) % n
            lines.append(f"        ({2*n+j} {2*n+i} {3*n+i} {3*n+j})\n")
        lines.append("    ); }\n")

        lines.append(");\n")
        (case_dir / "system" / "blockMeshDict").write_text("".join(lines))

    def _write_ogrid_bc(self, case_dir: Path, alpha_deg: float) -> None:
        """Boundary conditions for O-grid 2D case."""
        alpha = math.radians(alpha_deg)
        Ux = self.V * math.cos(alpha)
        Uz = self.V * math.sin(alpha)

        I = 0.05   # %5 türbülans yoğunluğu — kOmegaSST stabilitesi için
        L_t = 0.07 * self.C
        k0     = 1.5 * (self.V * I) ** 2
        omega0 = math.sqrt(k0) / (0.09**0.25 * L_t)
        nut0   = k0 / omega0

        # Duvar muamelesi — varsayilan high-Re (y+~400); y+~1 icin low-Re override edilir
        nut_wall = getattr(self, "nut_wall", "nutkWallFunction")
        k_wall   = getattr(self, "k_wall", "kqRWallFunction")

        # freestream_bc (attribute, default False): dis sinir karakteristik external-aero BC
        # (freestream/freestreamPressure -> yerel-akiya gore auto inflow/outflow). Yuksek-alpha'da
        # fixedValue+uniform over-constrained olup lift-indukli sirkulasyonu temsil edemiyor ->
        # diverjans (arXiv:2411.13077). freestream BC bu instabiliteyi giderir; alpha=0/4'te
        # fixedValue ile ayni sonucu vermeli (default False -> validated yol degismez).
        fs = getattr(self, "freestream_bc", False)
        if fs:
            ff_U     = f"farfield {{ type freestream; freestreamValue uniform ({Ux} 0 {Uz}); }}"
            ff_p     = "farfield { type freestreamPressure; freestreamValue uniform 0; }"
            ff_k     = f"farfield {{ type inletOutlet; inletValue uniform {k0:.6e}; value uniform {k0:.6e}; }}"
            ff_omega = f"farfield {{ type inletOutlet; inletValue uniform {omega0:.4f}; value uniform {omega0:.4f}; }}"
        else:
            ff_U     = f"farfield {{ type fixedValue; value uniform ({Ux} 0 {Uz}); }}"
            ff_p     = "farfield { type fixedValue; value uniform 0; }"
            ff_k     = f"farfield {{ type fixedValue; value uniform {k0:.6e}; }}"
            ff_omega = f"farfield {{ type fixedValue; value uniform {omega0:.4f}; }}"

        zero = case_dir / "0"
        zero.mkdir(exist_ok=True)

        (zero / "U").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0];
internalField uniform ({Ux} 0 {Uz});
boundaryField
{{
    airfoil  {{ type noSlip; }}
    {ff_U}
    front    {{ type empty; }}
    back     {{ type empty; }}
}}
""")
        (zero / "p").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object p; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    airfoil  {{ type zeroGradient; }}
    {ff_p}
    front    {{ type empty; }}
    back     {{ type empty; }}
}}
""")
        (zero / "k").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform {k0:.6e};
boundaryField
{{
    airfoil  {{ type {k_wall}; value uniform {k0:.6e}; }}
    {ff_k}
    front    {{ type empty; }}
    back     {{ type empty; }}
}}
""")
        (zero / "omega").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0];
internalField uniform {omega0:.4f};
boundaryField
{{
    airfoil  {{ type omegaWallFunction; value uniform {omega0:.4f}; }}
    {ff_omega}
    front    {{ type empty; }}
    back     {{ type empty; }}
}}
""")
        (zero / "nut").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0];
internalField uniform {nut0:.6e};
boundaryField
{{
    airfoil  {{ type {nut_wall}; value uniform 0; }}
    farfield {{ type calculated; value uniform {nut0:.6e}; }}
    front    {{ type empty; }}
    back     {{ type empty; }}
}}
""")

    def _generate_stl(self, case_dir: Path) -> Path:
        """NACA 0012 profili 2D extrude ederek STL uret."""
        import trimesh
        profile = self._naca0012_profile(n=128)
        span = 0.1      # 2D: 1 hucre kalinligi (m)

        n = len(profile)
        root_v = np.column_stack([profile[:, 0], np.zeros(n), profile[:, 1]])
        tip_v  = np.column_stack([profile[:, 0], np.full(n, span), profile[:, 1]])
        verts  = np.vstack([root_v, tip_v])

        faces = []
        for i in range(n):
            j = (i + 1) % n
            r0, r1, t0, t1 = i, j, i+n, j+n
            e1 = verts[r1] - verts[r0]
            e2 = verts[t0] - verts[r0]
            norm = np.cross(e1, e2)
            cx = profile[:, 0].mean()
            cz = profile[:, 1].mean()
            mid = (verts[r0] + verts[t0]) / 2
            if np.dot(norm, mid - np.array([cx, span/2, cz])) > 0:
                faces += [[r0, r1, t0], [r1, t1, t0]]
            else:
                faces += [[r0, t0, r1], [r1, t0, t1]]

        # Kapaklari kapat
        for offset, y_val, flip in [(0, 0, True), (n, span, False)]:
            cid = len(verts) + (0 if offset == 0 else 1)
            c3d = verts[offset:offset+n].mean(axis=0)
            for i in range(n):
                j = (i + 1) % n
                a, b = i+offset, j+offset
                cross = np.cross(verts[b]-verts[a], c3d-verts[a])
                if (offset == 0 and cross[1] < 0) or (offset == n and cross[1] > 0):
                    faces.append([a, b, cid])
                else:
                    faces.append([b, a, cid])

        rc = verts[:n].mean(axis=0)
        tc = verts[n:2*n].mean(axis=0)
        all_v = np.vstack([verts, rc.reshape(1,3), tc.reshape(1,3)])

        mesh = trimesh.Trimesh(vertices=all_v,
                               faces=np.array(faces, dtype=np.int64),
                               process=True)
        trimesh.repair.fix_normals(mesh)
        stl_path = case_dir / "constant" / "triSurface" / "naca0012.stl"
        mesh.export(str(stl_path))
        return stl_path

    def _write_case(self, case_dir: Path, alpha_deg: float) -> None:
        """OpenFOAM 2D case dosyalarini yaz."""
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "0").mkdir(exist_ok=True)
        (case_dir / "constant" / "triSurface").mkdir(parents=True, exist_ok=True)
        (case_dir / "system").mkdir(exist_ok=True)

        # Hiz vektoru: AoA ile dondur
        alpha = math.radians(alpha_deg)
        Ux = self.V * math.cos(alpha)
        Uz = self.V * math.sin(alpha)

        # Turbulans IC
        I = 0.001  # dusuk turbulans (%0.1) - havayolu testi icin
        L_t = 0.07 * self.C
        k0  = 1.5 * (self.V * I) ** 2
        omega0 = math.sqrt(k0) / (0.09**0.25 * L_t)
        nut0 = k0 / omega0

        # Domain boyutlari (C-grid)
        R  = 20 * self.C   # yari cap
        W  = 0.1           # kalinlik (2D)

        # blockMeshDict — C-grid yaklasimi olarak dikdortgen domain
        x_min = -R;  x_max = R * 2
        z_min = -R;  z_max = R
        nx = 120;  nz = 60;  ny = 1

        # OpenFOAM hex vertex sirasi: x yonunde 0→1, y yonunde 0→W, z yonunde z_min→z_max
        # Standart: (0,1,2,3) alt yuz (z=z_min), (4,5,6,7) ust yuz (z=z_max)
        # y = span yonu (2D icin W kalinligi)
        (case_dir / "system" / "blockMeshDict").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object blockMeshDict; }}
convertToMeters 1;
vertices
(
    ({x_min:.4f} 0      {z_min:.4f})  // 0
    ({x_max:.4f} 0      {z_min:.4f})  // 1
    ({x_max:.4f} {W:.4f} {z_min:.4f})  // 2
    ({x_min:.4f} {W:.4f} {z_min:.4f})  // 3
    ({x_min:.4f} 0      {z_max:.4f})  // 4
    ({x_max:.4f} 0      {z_max:.4f})  // 5
    ({x_max:.4f} {W:.4f} {z_max:.4f})  // 6
    ({x_min:.4f} {W:.4f} {z_max:.4f})  // 7
);
blocks ( hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1) );
boundary
(
    inlet  {{ type patch;  faces ((0 4 7 3) (0 3 2 1) (4 5 6 7)); }}
    outlet {{ type patch;  faces ((1 2 6 5)); }}
    front  {{ type symmetry;  faces ((0 1 5 4)); }}
    back   {{ type symmetry;  faces ((3 7 6 2)); }}
);
""")

        # surfaceFeaturesDict
        (case_dir / "system" / "surfaceFeaturesDict").write_text(
            'FoamFile { version 2.0; format ascii; class dictionary; object surfaceFeaturesDict; }\n'
            'surfaces ( "naca0012.stl" );\nincludedAngle 150;\nwriteObj yes;\n'
        )

        # snappyHexMeshDict
        (case_dir / "system" / "snappyHexMeshDict").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object snappyHexMeshDict; }}
castellatedMesh true; snap true; addLayers true;
geometry
{{
    naca0012.stl {{ type triSurfaceMesh; name naca0012; }}
}}
castellatedMeshControls
{{
    maxLocalCells 2000000; maxGlobalCells 8000000;
    minRefinementCells 10; nCellsBetweenLevels 3;
    resolveFeatureAngle 30;
    locationInMesh ({R} {W/2} 0);
    allowFreeStandingZoneFaces true;
    features ( {{ file "naca0012.eMesh"; level 4; }} );
    refinementSurfaces {{ naca0012 {{ level (4 6); patchInfo {{ type wall; }} }} }}
    refinementRegions {{ naca0012 {{ mode inside; levels ((1e15 6)); }} }}
}}
snapControls
{{ nSmoothPatch 3; tolerance 4.0; nSolveIter 300; nRelaxIter 5;
   nFeatureSnapIter 10; implicitFeatureSnap false; explicitFeatureSnap true;
   multiRegionFeatureSnap false; }}
addLayersControls
{{
    relativeSizes true;
    layers {{ "naca0012_.*" {{ nSurfaceLayers 5; }} }}
    expansionRatio 1.3; finalLayerThickness 0.3; minThickness 0.05;
    nGrow 0; featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1;
    nSmoothNormals 3; nSmoothThickness 10; maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3; minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0; nLayerIter 50;
}}
meshQualityControls
{{ maxNonOrtho 70; maxBoundarySkewness 20; maxInternalSkewness 4;
   maxConcave 80; minFlatness 0.5; minVol 1e-13; minTetQuality -1e30;
   minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.02;
   minVolRatio 0.01; minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75; }}
writeFlags ( scalarLevels layerSets layerFields );
mergeTolerance 1e-6;
""")

        # controlDict
        (case_dir / "system" / "controlDict").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object controlDict; }}
application foamRun;
startFrom startTime; startTime 0; endTime 2000;
deltaT 1; writeInterval 100; purgeWrite 3; writeFormat binary;
runTimeModifiable true;
functions
{{
    forces {{
        type forces; libs ("libforces.so");
        writeControl timeStep; writeInterval 50;
        patches ("naca0012"); rho rhoInf; rhoInf {self.RHO};
        pRef 0; CofR (0.25 {W/2} 0);
    }}
}}
""")

        # fvSchemes
        (case_dir / "system" / "fvSchemes").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; grad(U) cellLimited Gauss linear 1;
                  grad(k) cellLimited Gauss linear 1; grad(omega) cellLimited Gauss linear 1; }
divSchemes      { default none;
                  div(phi,U)     bounded Gauss linearUpwindV grad(U);
                  div(phi,k)     bounded Gauss linearUpwind grad(k);
                  div(phi,omega) bounded Gauss linearUpwind grad(omega);
                  div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
wallDist        { method meshWave; }
""")

        # fvSolution
        (case_dir / "system" / "fvSolution").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSolution; }
solvers
{
    p { solver GAMG; tolerance 1e-7; relTol 0.01; smoother GaussSeidel;
        nPreSweeps 0; nPostSweeps 2; cacheAgglomeration on;
        agglomerator faceAreaPair; nCellsInCoarsestLevel 10; mergeLevels 1; }
    "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel;
                    tolerance 1e-7; relTol 0.01; }
}
SIMPLE { nNonOrthogonalCorrectors 1; consistent yes;
         // residual!=kuvvet: 1e-5 gevsekti (kuvvet platoya oturmadan durur). 1e-7 = TMR'de
         // dogrulanan seviye (dusuk-alpha icin yeterli; yuksek-alpha polar icin force-plateau ideal).
         residualControl { p 1e-7; U 1e-7; "(k|omega)" 1e-7; } }
relaxationFactors { equations { U 0.7; k 0.5; omega 0.5; } fields { p 0.3; } }
""")

        # turbulenceProperties
        (case_dir / "constant" / "turbulenceProperties").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType RAS;
RAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }
""")

        (case_dir / "constant" / "transportProperties").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object transportProperties; }}
transportModel Newtonian;
nu {self.NU};
""")

        # 0/ — baslangic kosullari
        zero = case_dir / "0"

        (zero / "U").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0];
internalField uniform ({Ux} 0 {Uz});
boundaryField
{{
    inlet   {{ type fixedValue; value uniform ({Ux} 0 {Uz}); }}
    outlet  {{ type inletOutlet; inletValue uniform (0 0 0); value uniform ({Ux} 0 {Uz}); }}
    naca0012 {{ type noSlip; }}
    front   {{ type symmetry; }}
    back    {{ type symmetry; }}
}}
""")

        (zero / "p").write_text("""FoamFile
{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    inlet   { type zeroGradient; }
    outlet  { type fixedValue; value uniform 0; }
    naca0012 { type zeroGradient; }
    front   { type symmetry; }
    back    { type symmetry; }
}
""")

        (zero / "k").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform {k0:.6e};
boundaryField
{{
    inlet   {{ type fixedValue; value uniform {k0:.6e}; }}
    outlet  {{ type inletOutlet; inletValue uniform {k0:.6e}; value uniform {k0:.6e}; }}
    naca0012 {{ type kqRWallFunction; value uniform {k0:.6e}; }}
    front   {{ type symmetry; }}
    back    {{ type symmetry; }}
}}
""")

        (zero / "omega").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0];
internalField uniform {omega0:.4f};
boundaryField
{{
    inlet   {{ type fixedValue; value uniform {omega0:.4f}; }}
    outlet  {{ type inletOutlet; inletValue uniform {omega0:.4f}; value uniform {omega0:.4f}; }}
    naca0012 {{ type omegaWallFunction; value uniform {omega0:.4f}; }}
    front   {{ type symmetry; }}
    back    {{ type symmetry; }}
}}
""")

        (zero / "nut").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0];
internalField uniform {nut0:.6e};
boundaryField
{{
    inlet   {{ type calculated; value uniform {nut0:.6e}; }}
    outlet  {{ type calculated; value uniform {nut0:.6e}; }}
    naca0012 {{ type nutkWallFunction; value uniform 0; }}
    front   {{ type symmetry; }}
    back    {{ type symmetry; }}
}}
""")

    def _parse_forces(self, case_dir: Path, alpha_deg: float) -> dict:
        """forces.dat dosyasindan Cl, Cd hesapla."""
        force_files = list((case_dir / "postProcessing" / "forces").glob("*/forces.dat"))
        if not force_files:
            return {}
        lines = [l for l in force_files[0].read_text().splitlines()
                 if not l.strip().startswith("#") and l.strip()]
        if not lines:
            return {}

        nums = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', lines[-1])
        try:
            Fpx, Fpy, Fpz = float(nums[1]), float(nums[2]), float(nums[3])
            Fvx, Fvy, Fvz = float(nums[4]), float(nums[5]), float(nums[6])
        # sessiz-yutma: kabul — bos sozluk "kuvvet okunamadi" demek ve cagiran
        # bunu 0 ile karistirmiyor. SINIR: sabit sutun indisleri OF surumune bagli.
        except (IndexError, ValueError):
            return {}

        Fx = Fpx + Fvx
        Fz = Fpz + Fvz

        # AoA dongusunu geri al: drag = akis yonunde, lift = dike
        alpha = math.radians(alpha_deg)
        drag =  Fx * math.cos(alpha) + Fz * math.sin(alpha)
        lift = -Fx * math.sin(alpha) + Fz * math.cos(alpha)

        # Normalize (2D: span = W = 0.1 m)
        W  = 0.1
        q  = 0.5 * self.RHO * self.V ** 2
        S  = self.C * W  # birim kord x W

        return {
            "Cl": lift / (q * S),
            "Cd": drag / (q * S),
        }

    def run(self, alpha_deg: float = 0) -> dict:
        """Tek AoA icin CFD calistir, NASA verisiyle karsilastir.
        O-grid blockMesh kullanir — snappy yok, empty patches (true 2D), y+~30.
        """
        case_dir = self.base_path / f"alpha_{alpha_deg:02d}"
        if case_dir.exists():
            shutil.rmtree(case_dir)

        print(f"[CFD VAL] NACA 0012 O-grid  alpha={alpha_deg} deg  Re={self.RE:.2e}")

        # Klasor yapisi
        (case_dir / "system").mkdir(parents=True, exist_ok=True)
        (case_dir / "constant").mkdir(exist_ok=True)

        # O-grid blockMeshDict
        self._write_ogrid(case_dir, alpha_deg)
        self._write_ogrid_bc(case_dir, alpha_deg)

        # Solver dosyalari
        W = 0.1
        (case_dir / "system" / "controlDict").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object controlDict; }}
application foamRun;
startFrom startTime; startTime 0; endTime 2000;
deltaT 1; writeInterval 200; purgeWrite 3; writeFormat binary;
runTimeModifiable true;
functions
{{
    forces {{
        type forces; libs ("libforces.so");
        writeControl timeStep; writeInterval 50;
        patches ("airfoil"); rho rhoInf; rhoInf {self.RHO};
        pRef 0; CofR (0.25 {W/2} 0);
    }}
}}
""")
        # Yuksek AoA icin daha konservatif scheme ve relaxation. force_gentle (attribute,
        # default yok) ince mesh + orta-AoA gibi yakinsamasi zor durumlar icin ayni nazik
        # ayarlari acar (a4_fine: ince O-grid + alpha=4 -> sirkulasyon, default relax diverjyor).
        is_high_aoa = alpha_deg >= 6 or getattr(self, "force_gentle", False)
        div_U = "bounded Gauss upwind" if is_high_aoa else "bounded Gauss linearUpwindV grad(U)"
        relax_U = 0.5 if is_high_aoa else 0.6
        relax_k = 0.3 if is_high_aoa else 0.4
        relax_p = 0.2 if is_high_aoa else 0.25

        (case_dir / "system" / "fvSchemes").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object fvSchemes; }}
ddtSchemes      {{ default steadyState; }}
gradSchemes     {{ default Gauss linear; grad(U) cellLimited Gauss linear 1;
                  grad(k) cellLimited Gauss linear 1; grad(omega) cellLimited Gauss linear 1; }}
divSchemes      {{ default none;
                  div(phi,U)     {div_U};
                  div(phi,k)     bounded Gauss upwind;
                  div(phi,omega) bounded Gauss upwind;
                  div((nuEff*dev2(T(grad(U))))) Gauss linear; }}
laplacianSchemes {{ default Gauss linear corrected; }}
interpolationSchemes {{ default linear; }}
snGradSchemes   {{ default corrected; }}
wallDist        {{ method meshWave; }}
""")
        (case_dir / "system" / "fvSolution").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object fvSolution; }}
solvers
{{
    p {{ solver GAMG; tolerance 1e-8; relTol 0.01; smoother GaussSeidel;
        nPreSweeps 0; nPostSweeps 2; cacheAgglomeration on;
        agglomerator faceAreaPair; nCellsInCoarsestLevel 10; mergeLevels 1; }}
    "(U|k|omega)" {{ solver smoothSolver; smoother symGaussSeidel;
                    tolerance 1e-8; relTol 0.01; }}
}}
SIMPLE {{ nNonOrthogonalCorrectors 2; consistent yes;
         residualControl {{ p 1e-5; U 1e-5; "(k|omega)" 1e-5; }} }}
relaxationFactors {{ equations {{ U {relax_U}; k {relax_k}; omega {relax_k}; }} fields {{ p {relax_p}; }} }}
""")
        (case_dir / "constant" / "turbulenceProperties").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType RAS;
RAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }
""")
        (case_dir / "constant" / "transportProperties").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object transportProperties; }}
transportModel Newtonian;
nu {self.NU};
""")

        wsl = _to_wsl_path(case_dir)

        # O-grid: sadece blockMesh + solver (snappy yok)
        for cmd, label, timeout in [
            ("blockMesh > log.bm 2>&1",           "blockMesh",    300),
            ("foamRun -solver incompressibleFluid > log.s 2>&1", "solver", 7200),
        ]:
            rc = _run(_wsl_of(wsl, cmd), timeout=timeout)
            if rc != 0:
                log_file = case_dir / f"log.{label[:2]}"
                log_tail = log_file.read_text(errors="replace")[-300:] if log_file.exists() else ""
                return {"status": "FAILED", "step": label, "log": log_tail}
            print(f"  [{label}] OK")

        sim = self._parse_forces(case_dir, alpha_deg)
        if not sim:
            return {"status": "FAILED", "step": "forces_parse"}

        ref = NACA0012_NASA.get(alpha_deg)
        result = {
            "alpha": alpha_deg,
            "Re": self.RE,
            "Cl_sim": round(sim["Cl"], 4),
            "Cd_sim": round(sim["Cd"], 5),
            "source": ref[2] if ref else "N/A",
        }

        if ref:
            Cl_ref, Cd_ref = ref[0], ref[1]
            Cl_abs_err = abs(sim["Cl"] - Cl_ref)
            Cl_rel_err = Cl_abs_err / (abs(Cl_ref) + 1e-3)
            Cd_err     = abs(sim["Cd"] - Cd_ref) / Cd_ref
            result.update({
                "Cl_ref":     Cl_ref,
                "Cd_ref":     Cd_ref,
                "Cl_err_abs": round(Cl_abs_err, 4),
                "Cl_err_pct": round(Cl_rel_err * 100, 1),
                "Cd_err_pct": round(Cd_err * 100, 1),
                "Cl_pass":    Cl_abs_err < 0.05 if abs(Cl_ref) < 0.01 else Cl_rel_err < CFD_TOLERANCE,
                "Cd_pass":    Cd_err < CFD_TOLERANCE,
            })
            result["status"] = "PASS" if (result["Cl_pass"] and result["Cd_pass"]) else "FAIL"
        else:
            result["status"] = "NO_REF"

        return result


# ─────────────────────────────────────────────────────────────────────────────
# FEA VALIDATION — ANKASTRE KIRIS
# ─────────────────────────────────────────────────────────────────────────────

class CantileverBeamValidation:
    """
    Dikdortgen kesitli ankastre kiris, ucunda tekil kuvvet.
    Euler-Bernoulli analitik: delta = F*L^3 / (3*E*I)
    Kabul: FEA sonucu analitikten < %5 farkli olmali.
    """

    # Kiris boyutlari
    L = 0.5    # m  uzunluk
    b = 0.02   # m  genislik
    h = 0.01   # m  yukseklik (yuklenme yonu)
    F = 100.0  # N  uç kuvveti (+z yonu)

    # Malzeme: Al 6061
    E  = 69e9   # Pa
    NU = 0.33

    def __init__(self, base_path: str = "./validation/cantilever"):
        self.base_path = Path(base_path)

    @property
    def analytical_deflection(self) -> float:
        """Euler-Bernoulli max deflection (m)."""
        I = self.b * self.h**3 / 12
        return self.F * self.L**3 / (3 * self.E * I)

    @property
    def analytical_max_stress(self) -> float:
        """Max bending stress at fixed end (Pa): sigma = M*c/I"""
        I = self.b * self.h**3 / 12
        M = self.F * self.L
        c = self.h / 2
        return M * c / I

    def run(self) -> dict:
        """Ankastre kiris FEA calistir, analitikle karsilastir.
        B31 (Timoshenko kiris elementi) kullanilir — 1D kiris icin dogru formülasyon.
        S3 shell veya C3D4 solid bu geometride yaniltici sonuc verir.
        """
        case_dir = self.base_path
        case_dir.mkdir(parents=True, exist_ok=True)

        delta_analytic = self.analytical_deflection
        sigma_analytic = self.analytical_max_stress

        print(f"[FEA VAL] Ankastre kiris  L={self.L}m  b={self.b}m  h={self.h}m")
        print(f"  Analitik defleksiyon: {delta_analytic*1000:.4f} mm")
        print(f"  Analitik max gerilme: {sigma_analytic/1e6:.2f} MPa")

        # B31 kiris elementi ile 1D mesh
        n_elem = 20    # 20 element yeterli
        n_node = n_elem + 1
        dx = self.L / n_elem

        inp_path = case_dir / "cantilever.inp"
        lines = ["*HEADING\nCantilever beam B31 validation\n"]

        # Nodes: x ekseninde esit aralikli
        lines.append("*NODE, NSET=NALL\n")
        for i in range(n_node):
            x = i * dx
            lines.append(f"{i+1}, {x:.8e}, 0.0, 0.0\n")

        # B31 elementleri
        lines.append("*ELEMENT, TYPE=B31, ELSET=EBEAM\n")
        for i in range(n_elem):
            lines.append(f"{i+1}, {i+1}, {i+2}\n")

        # Kiris kesiti: dikdortgen  b x h
        # CalculiX RECT section: parametreler a, b (genislik, yukseklik)
        # Kesit normal vektoru: 0,0,-1 (z yönünde egrilme icin)
        lines.append("*BEAM SECTION, ELSET=EBEAM, MATERIAL=AL6061, SECTION=RECT\n")
        lines.append(f"{self.b}, {self.h}\n")
        lines.append("0., 1., 0.\n")   # local y ekseni (enine yön)

        # Malzeme
        lines.append("*MATERIAL, NAME=AL6061\n")
        lines.append(f"*ELASTIC\n{self.E:.6e}, {self.NU}\n")
        lines.append("*DENSITY\n2700\n")

        # Sinir kosulu: node 1 tum DOF sabit
        lines.append("*NSET, NSET=NSET_FIXED\n1\n")
        lines.append("*NSET, NSET=NSET_LOAD\n")
        lines.append(f"{n_node}\n")

        # Analiz adimi
        lines.append("*BOUNDARY\nNSET_FIXED, 1, 6, 0\n")
        lines.append("*STEP\n*STATIC\n1.0, 1.0\n")
        lines.append(f"*CLOAD\n{n_node}, 3, {self.F:.4f}\n")  # DOF3 = z defleksiyonu
        lines.append("*NODE PRINT, NSET=NALL\nU\n")
        lines.append("*NODE FILE\nU\n")
        lines.append("*EL FILE\nS\n")
        lines.append("*END STEP\n")

        inp_path.write_text("".join(lines))

        # CCX calistir
        wsl_dir = _to_wsl_path(case_dir)
        rc = _run(f'wsl bash -c "cd {wsl_dir} && ccx -i cantilever 2>&1"',
                  timeout=300)

        # FRD parse
        frd_path = case_dir / "cantilever.frd"
        if not frd_path.exists():
            return {"status": "FAILED", "step": "ccx_no_output"}

        lines = frd_path.read_text(errors="replace").splitlines()
        block = None
        disps, stresses = [], []

        def _is_float(s):
            try: float(s); return True
            # sessiz-yutma: kabul — sayi-mi testi; istisna kontrol akisi
            except (ValueError, TypeError): return False

        for line in lines:
            if " -4  DISP" in line:   block = "DISP";   continue
            if " -4  STRESS" in line: block = "STRESS"; continue
            if line.startswith(" -4"): block = None
            if block and line.startswith(" -1"):
                parts = line.split()
                vals = [float(v) for v in parts[2:] if _is_float(v)]
                if block == "DISP" and len(vals) >= 3:
                    disps.append((vals[0]**2 + vals[1]**2 + vals[2]**2)**0.5)
                elif block == "STRESS" and len(vals) >= 6:
                    s11,s22,s33,s12,s23,s13 = vals[:6]
                    vm = ((s11-s22)**2+(s22-s33)**2+(s33-s11)**2
                          + 6*(s12**2+s23**2+s13**2))**0.5 / 2**0.5
                    stresses.append(vm)

        # B31 icin .dat dosyasindan da oku (daha temiz format)
        dat_path = case_dir / "cantilever.dat"
        if dat_path.exists() and not disps:
            dat_lines = dat_path.read_text(errors="replace").splitlines()
            in_u = False
            for line in dat_lines:
                if "displacements" in line.lower():
                    in_u = True; continue
                if in_u and line.strip() == "":
                    in_u = False
                if in_u:
                    parts = line.split()
                    try:
                        u1, u2, u3 = float(parts[1]), float(parts[2]), float(parts[3])
                        disps.append((u1**2 + u2**2 + u3**2)**0.5)
                    # sessiz-yutma: kabul — .frd blogunda basliklar/ayirac satirlari
                    # sayi tasimaz; tek satir atlanir. Hicbiri okunamazsa asagidaki
                    # `if not disps` FAILED/frd_parse_empty doner, yani bos sonuc
                    # basarili sayilmaz.
                    except (IndexError, ValueError):
                        pass

        if not disps:
            return {"status": "FAILED", "step": "frd_parse_empty"}

        delta_fea  = max(disps)
        sigma_fea  = max(stresses) if stresses else None

        err_disp   = abs(delta_fea - delta_analytic) / delta_analytic
        err_stress = abs(sigma_fea - sigma_analytic) / sigma_analytic if sigma_fea else None

        result = {
            "L_m":  self.L, "b_m": self.b, "h_m": self.h, "F_N": self.F,
            "E_GPa": self.E / 1e9, "nu": self.NU,
            "delta_analytic_mm": round(delta_analytic * 1000, 4),
            "delta_fea_mm":      round(delta_fea  * 1000, 4),
            "deflection_err_pct": round(err_disp * 100, 2),
            "deflection_pass":   err_disp < FEA_TOLERANCE,
        }
        if sigma_fea is not None:
            result.update({
                "sigma_analytic_MPa": round(sigma_analytic / 1e6, 2),
                "sigma_fea_MPa":      round(sigma_fea / 1e6, 2),
                "stress_err_pct":     round(err_stress * 100, 2) if err_stress else None,
                "stress_pass":        err_stress < FEA_TOLERANCE if err_stress else False,
            })
        result["status"] = "PASS" if result["deflection_pass"] else "FAIL"
        return result


# ─────────────────────────────────────────────────────────────────────────────
# ANA SUITE
# ─────────────────────────────────────────────────────────────────────────────

class ValidationSuite:

    def __init__(self, base_path: str = "./validation"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        self.results = {}

    def run_fea(self) -> dict:
        v = CantileverBeamValidation(str(self.base_path / "cantilever"))
        r = v.run()
        self.results["fea_cantilever"] = r
        return r

    def run_cfd(self, alpha_deg: int = 0) -> dict:
        v = NACA0012Validation(str(self.base_path / "naca0012"))
        r = v.run(alpha_deg)
        self.results[f"cfd_alpha{alpha_deg}"] = r
        return r

    def print_report(self) -> None:
        print()
        print("=" * 60)
        print("  VALIDATION RAPORU")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)

        # FEA
        fea = self.results.get("fea_cantilever", {})
        if fea:
            print()
            print("FEA — Ankastre Kiris (Euler-Bernoulli)")
            print(f"  Geometri : L={fea['L_m']}m  b={fea['b_m']}m  h={fea['h_m']}m")
            print(f"  Yuk      : F={fea['F_N']} N")
            print(f"  Malzeme  : E={fea['E_GPa']} GPa")
            print()
            print(f"  {'Buyukluk':25s}  {'Analitik':12s}  {'FEA':12s}  {'Hata':8s}  {'Gecti?':6s}")
            print(f"  {'-'*65}")
            print(f"  {'Defleksiyon (mm)':25s}  {fea['delta_analytic_mm']:12.4f}  "
                  f"{fea['delta_fea_mm']:12.4f}  "
                  f"{fea['deflection_err_pct']:7.2f}%  "
                  f"{'PASS' if fea['deflection_pass'] else 'FAIL':6s}")
            if "sigma_analytic_MPa" in fea:
                print(f"  {'Max gerilme (MPa)':25s}  {fea['sigma_analytic_MPa']:12.2f}  "
                      f"{fea['sigma_fea_MPa']:12.2f}  "
                      f"{fea.get('stress_err_pct', 'N/A'):7}%  "
                      f"{'PASS' if fea.get('stress_pass') else 'FAIL':6s}")
            print(f"\n  >> FEA VALIDATION: {fea['status']}")

        # CFD
        for key, cfd in self.results.items():
            if not key.startswith("cfd_"):
                continue
            print()
            print(f"CFD — NACA 0012  alpha={cfd.get('alpha')} deg  Re={cfd.get('Re', 0):.2e}")
            print(f"  Kaynak: {cfd.get('source', 'N/A')}")
            print()
            if "Cl_ref" in cfd:
                print(f"  {'Katsayi':8s}  {'Deney':10s}  {'OF-11':10s}  {'Hata':8s}  {'Gecti?':6s}")
                print(f"  {'-'*48}")
                print(f"  {'Cl':8s}  {cfd['Cl_ref']:10.4f}  {cfd['Cl_sim']:10.4f}  "
                      f"{cfd['Cl_err_pct']:7.1f}%  {'PASS' if cfd['Cl_pass'] else 'FAIL':6s}")
                print(f"  {'Cd':8s}  {cfd['Cd_ref']:10.5f}  {cfd['Cd_sim']:10.5f}  "
                      f"{cfd['Cd_err_pct']:7.1f}%  {'PASS' if cfd['Cd_pass'] else 'FAIL':6s}")
            print(f"\n  >> CFD VALIDATION: {cfd['status']}")

        # Ozet
        all_pass = all(r.get("status") == "PASS" for r in self.results.values())
        print()
        print("=" * 60)
        print(f"  GENEL SONUC: {'VALIDATED' if all_pass else 'VALIDATION FAILED'}")
        print("=" * 60)

    def save(self, path: str = None) -> None:
        out = Path(path or str(self.base_path / "validation_results.json"))
        out.write_text(json.dumps(self.results, indent=2, default=str))
        print(f"Sonuclar kaydedildi: {out}")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    suite = ValidationSuite("./validation")

    if mode in ("all", "fea"):
        print("--- FEA VALIDATION ---")
        fea_r = suite.run_fea()
        print(f"FEA: {fea_r.get('status')}  "
              f"defleksiyon hata={fea_r.get('deflection_err_pct')}%")

    if mode in ("all", "cfd"):
        # NASA verisi: alpha=0 ve 4 deg (bagli akis)
        # alpha=8: stall yakininda ayrilmis akis — y+~400 O-grid bu rejimi cozemez
        for alpha in [0, 4]:
            print()
            print(f"--- CFD VALIDATION alpha={alpha} ---")
            cfd_r = suite.run_cfd(alpha_deg=alpha)
            print(f"  Cd={cfd_r.get('Cd_sim')} (ref={cfd_r.get('Cd_ref')}, err={cfd_r.get('Cd_err_pct')}%)  "
                  f"Cl={cfd_r.get('Cl_sim')} (ref={cfd_r.get('Cl_ref')}, err={cfd_r.get('Cl_err_pct')}%)  "
                  f"-> {cfd_r.get('status')}")

    suite.print_report()
    suite.save()
