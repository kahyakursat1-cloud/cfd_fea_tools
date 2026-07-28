"""
OpenFOAM CFD wrapper — STL'den otomatik harici aerodinamik analizi.

UYARI / DISCLAIMER
==================
Bu modül "her STL'den otomatik CFD" yapmaya çalışır. Bu araştırma seviyesinde
zor bir problem; sonuçların doğruluğu büyük ölçüde geometriye, mesh'e ve
default parametrelere bağlıdır. Konservatif default'larla başlar; profesyonel
sonuçlar için manuel tuning gerekebilir.

Strateji
--------
1) STL yi case/constant/triSurface/<name>.stl olarak kopyala
2) Bbox'tan harici domain üret (10× upstream, 30× downstream, 10× yan)
3) blockMeshDict + snappyHexMeshDict + system/* dosyalarını yaz
4) WSL içinde OpenFOAM 11 ile:
   surfaceFeatures -> blockMesh -> snappyHexMesh -overwrite -> simpleFoam
5) postProcessing/forceCoeffs1/0/coefficient.dat'ı oku

Solver: simpleFoam (steady incompressible), turbulence: k-omegaSST
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh


def _default_processors() -> int:
    """CFD için optimal MPI rank sayısı = FİZİKSEL çekirdek (host değil, arka uç).

    Open MPI fiziksel çekirdeği 'slot' sayar; mantıksal (hyperthread) sayısı verirsek
    'not enough slots' hatası. Ayrıca CFD bellek-bant sınırlı → hyperthread ~fayda yok.
    `lscpu -p=Core` benzersiz çekirdek = fiziksel. .wslconfig sınırını da yansıtır.
    """
    try:
        from .backend import linux_run as _lr
        r = _lr("lscpu -p=Core 2>/dev/null | grep -v '^#' | sort -u | wc -l", 15)
        n = int(r.stdout.strip())
        if n < 1:
            raise ValueError
        return max(1, min(n, 8))           # pratik tavan 8 (bellek koruması)
    except Exception:
        try:
            from .backend import linux_run as _lr
            r = _lr("nproc", 15)
            return max(1, min(int(r.stdout.strip()) // 2, 8))   # mantıksal/2 ≈ fiziksel
        except Exception:
            return max(1, (os.cpu_count() or 4) // 2)

from .backend import (  # noqa: E402
    WSL_DISTRO,  # geriye-uyum: supersonic_cfd vb. buradan içe aktarır
    ext4_enabled,
    linux_home,
    linux_popen,
    linux_run,
)
from .ccx_runner import windows_to_wsl_path  # noqa: E402
from .thresholds import (  # noqa: E402
    ASPECT_LIMIT,
    NONORTHO_LIMIT,
    NONORTHO_REJECT,
    RESIDUAL_TARGET,
    SKEW_LIMIT,
    SKEW_REJECT,
)

# OpenFOAM 11 (Foundation) bashrc
OF_BASHRC = "/opt/openfoam11/etc/bashrc"
# ParaView'sız environment (headless WSL'de pvserver --version takılabiliyor).
# vader single-copy: WSL'de CMA (process_vm_readv) engelli — OpenMPI paylaşımlı
# bellek aktarımı süresiz asılıyor; bilinen çözüm mekanizmayı kapatmak.
# HWLOC_COMPONENTS=-gl: KRİTİK — hwloc'un GL bileşeni GPU-topolojisi için X-sunucusuna
# (127.0.0.1:6001, DISPLAY=:0 WSLg) bağlanıp SÜRESİZ asılıyordu → mpirun -np 1 bile
# launch'ta donuyordu (strace ile bulundu). GL'i kapatınca parallel mpirun ÇALIŞIR.
# unset FOAM_SIGFPE: bashrc boş-tanımlı export ediyor, .org sigFpe varlık-bazlı.
OF_ENV_PREFIX = (
    "export ParaView_TYPE=none && "
    "export OMPI_MCA_btl_vader_single_copy_mechanism=none && "
    "export HWLOC_COMPONENTS=-gl && "
    f"source {OF_BASHRC} && unset FOAM_SIGFPE && "
)


@dataclass
class CFDCase:
    """OpenFOAM külesinin tanımı."""
    name: str
    stl_path: Path                 # Windows path
    velocity: float = 30.0         # m/s, freestream
    flow_direction: tuple[float, float, float] = (1.0, 0.0, 0.0)
    rho: float = 1.225             # kg/m^3
    nu: float = 1.5e-5             # m^2/s (hava ~15 °C)
    turbulence_intensity: float = 0.01   # %1
    domain_upstream: float = 5.0   # bbox boyu çarpanı
    domain_downstream: float = 15.0
    domain_lateral: float = 5.0
    refinement_min: int = 1        # snappyHexMesh surface min level
    refinement_max: int = 2
    n_layers: int = 0              # 0 = boundary layer eklenmesin (kararlılık için)
    first_layer_thickness: float | None = None  # m; None = göreli snappy varsayılanı
    propeller: dict | None = None  # {cap_m, area, Cp, Ct} — aktüatör disk (Froude)
    compressible: bool = False     # True: foamRun -solver fluid (Mach>0.3 için)
    t_inf: float = 288.15          # K
    p_inf: float = 101325.0       # Pa (sıkışabilir yolda mutlak basınç)
    bg_cell_size: float | None = None  # None = otomatik (L/8)
    end_time: int = 300            # SIMPLE iterasyonu
    write_interval: int = 100
    n_processors: int = 0          # 0 = otomatik (WSL nproc, max 8)
    max_global_cells: int = 1_500_000  # snappyHexMesh hücre tavanı (RAM koruması)
    ground_clearance: float | None = None  # m; verilirse taban = sabit noSlip zemin
                                           # (Ahmed-tipi zemin-etkili validasyon; incompressible)
    refinement_regions: list | None = None # hedefli bölge-refinement kutuları:
                                           # [{"ad", "min":(x,y,z), "max":(x,y,z), "level"}]
                                           # (gövde-altı/iz gibi yüzeyden-uzak kritik bölgeler;
                                           # max_global_cells tavanı yine geçerli)

    @property
    def lref(self) -> float:
        """Referans uzunluk: bbox max boyutu (ilk erişimde STL'den; sonra cache)."""
        cached = getattr(self, "_lref", None)
        if cached is not None:
            return cached
        m = trimesh.load(str(self.stl_path), force="mesh")
        val = (float((m.bounds[1] - m.bounds[0]).max())
               if isinstance(m, trimesh.Trimesh) else 1.0)
        self._lref = val
        return val


@dataclass
class CFDResult:
    case_dir: Path
    success: bool
    return_code: int
    stdout: str
    stderr: str
    cd: float | None = None
    cl: float | None = None
    cm: float | None = None
    forces_history: list[tuple[int, float, float, float]] = field(default_factory=list)
    log_files: list[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain ve dosya yardımcıları
# ---------------------------------------------------------------------------

def _compute_domain(stl_path: Path, case: CFDCase) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """STL'den domain bbox'ı ve geometri merkezi hesaplar.

    Returns:
        (domain_min, domain_max, geom_min, geom_max)
    """
    m = trimesh.load(str(stl_path), force="mesh")
    if not isinstance(m, trimesh.Trimesh):
        raise ValueError(f"STL yüklenemedi: {stl_path}")
    gmin = m.bounds[0].astype(np.float64)
    gmax = m.bounds[1].astype(np.float64)
    size = gmax - gmin
    L = float(size.max())

    # Akış yönü +x kabul edildi (case.flow_direction'a göre döndürmüyoruz)
    dmin = gmin.copy()
    dmax = gmax.copy()
    dmin[0] -= L * case.domain_upstream
    dmax[0] += L * case.domain_downstream
    dmin[1] -= L * case.domain_lateral
    dmax[1] += L * case.domain_lateral
    if case.ground_clearance is not None:
        dmin[2] = gmin[2] - case.ground_clearance   # taban = zemin düzlemi
    else:
        dmin[2] -= L * case.domain_lateral
    dmax[2] += L * case.domain_lateral
    return dmin, dmax, gmin, gmax


def _foam_header(class_: str, object_: str, location: str = "") -> str:
    loc = f'\n    location    "{location}";' if location else ""
    return (
        "/*--------------------------------*- C++ -*----------------------------------*/\n"
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {class_};{loc}\n"
        f"    object      {object_};\n"
        "}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
    )


def mesh_quality_gate(checkmesh_text: str) -> dict:
    """checkMesh çıktısını çöz + ÇÖZÜCÜ-ÖNCESİ verdict: 'ok' / 'warn' / 'reject'.
    Kötü mesh çözücüde saatlerce diverjyor/timeout'a uğruyor; bunu ÖNCEDEN yakala.
    Eşikler `thresholds.py`'den (TEK KAYNAK): warn = proje konvansiyonu
    (nonOrtho<70, skew<4), reject = diverjans deneyimi (75 / 6).
    Döner: {verdict, reasons[], non_ortho_max, skew_max, aspect_max, negatif_hacim}."""
    import re as _re

    def g(pat):
        m = _re.search(pat, checkmesh_text)
        return float(m.group(1)) if m else None
    non_ortho = g(r"non-orthogonality Max:\s*([\d.]+)")
    skew = g(r"Max skewness\s*=\s*([\d.eE+]+)")
    aspect = g(r"Max aspect ratio\s*[=:]?\s*([\d.eE+]+)")
    neg_vol = "negative volume" in checkmesh_text.lower()
    reasons, verdict = [], "ok"
    # REJECT: çözücü neredeyse kesin patlar
    if neg_vol:
        reasons.append("negatif hacimli hücre (mesh bozuk)"); verdict = "reject"
    if non_ortho is not None and non_ortho >= NONORTHO_REJECT:
        reasons.append(f"aşırı non-ortogonallik ({non_ortho:.0f}°≥{NONORTHO_REJECT:.0f})")
        verdict = "reject"
    if skew is not None and skew >= SKEW_REJECT:
        reasons.append(f"aşırı skewness ({skew:.1f}≥{SKEW_REJECT:.0f})"); verdict = "reject"
    # WARN: sınırda; koşabilir ama dikkat
    if verdict != "reject":
        if non_ortho is not None and NONORTHO_LIMIT <= non_ortho < NONORTHO_REJECT:
            reasons.append(f"yüksek non-ortogonallik ({non_ortho:.0f}°, eşik {NONORTHO_LIMIT:.0f})")
            verdict = "warn"
        if skew is not None and SKEW_LIMIT <= skew < SKEW_REJECT:
            reasons.append(f"yüksek skewness ({skew:.1f}, eşik {SKEW_LIMIT:.0f})"); verdict = "warn"
        if aspect is not None and aspect > ASPECT_LIMIT:
            reasons.append(f"çok yüksek aspect ratio ({aspect:.0e})"); verdict = "warn"
    return {"verdict": verdict, "reasons": reasons, "non_ortho_max": non_ortho,
            "skew_max": skew, "aspect_max": aspect, "negatif_hacim": neg_vol,
            "mesh_ok": "Mesh OK" in checkmesh_text}


# ---------------------------------------------------------------------------
# Dictionary yazıcılar
# ---------------------------------------------------------------------------

def _write_block_mesh(case_dir: Path, dmin: np.ndarray, dmax: np.ndarray,
                      cell_size: float, ground: bool = False) -> None:
    nx = max(int(math.ceil((dmax[0] - dmin[0]) / cell_size)), 8)
    ny = max(int(math.ceil((dmax[1] - dmin[1]) / cell_size)), 8)
    nz = max(int(math.ceil((dmax[2] - dmin[2]) / cell_size)), 8)

    txt = _foam_header("dictionary", "blockMeshDict", "system")
    txt += "convertToMeters 1.0;\n\n"
    txt += "vertices\n(\n"
    v = [
        (dmin[0], dmin[1], dmin[2]),
        (dmax[0], dmin[1], dmin[2]),
        (dmax[0], dmax[1], dmin[2]),
        (dmin[0], dmax[1], dmin[2]),
        (dmin[0], dmin[1], dmax[2]),
        (dmax[0], dmin[1], dmax[2]),
        (dmax[0], dmax[1], dmax[2]),
        (dmin[0], dmax[1], dmax[2]),
    ]
    for x, y, z in v:
        txt += f"    ({x:.6f} {y:.6f} {z:.6f})\n"
    txt += ");\n\n"
    txt += f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)\n);\n\n"
    txt += "edges\n(\n);\n\n"
    bottom_type = "wall" if ground else "patch"
    txt += (
        "boundary\n(\n"
        "    inlet     { type patch; faces ((0 4 7 3)); }\n"
        "    outlet    { type patch; faces ((1 2 6 5)); }\n"
        "    top       { type patch; faces ((3 7 6 2)); }\n"
        f"    bottom    {{ type {bottom_type}; faces ((0 1 5 4)); }}\n"
        "    front     { type patch; faces ((0 3 2 1)); }\n"
        "    back      { type patch; faces ((4 5 6 7)); }\n"
        ");\n\n"
        "mergePatchPairs\n(\n);\n"
    )
    (case_dir / "system" / "blockMeshDict").write_text(txt)


def _write_snappy(case_dir: Path, stl_name: str, surface_name: str,
                   inside_pt: tuple[float, float, float], case: CFDCase) -> None:
    max_local = max(case.max_global_cells // 4, 100_000)
    txt = _foam_header("dictionary", "snappyHexMeshDict", "system")
    txt += (
        "castellatedMesh true;\n"
        "snap            true;\n"
        f"addLayers       {'true' if case.n_layers > 0 else 'false'};\n\n"
    )
    rregions = case.refinement_regions or []
    txt += (
        "geometry\n{\n"
        f"    {stl_name}\n"
        "    {\n"
        "        type triSurfaceMesh;\n"
        f"        name {surface_name};\n"
        "    }\n"
    )
    for rr in rregions:
        mn, mx = rr["min"], rr["max"]
        txt += (f"    {rr['ad']} {{ type searchableBox; "
                f"min ({mn[0]:.6f} {mn[1]:.6f} {mn[2]:.6f}); "
                f"max ({mx[0]:.6f} {mx[1]:.6f} {mx[2]:.6f}); }}\n")
    txt += "}\n\n"
    rregion_txt = "".join(
        f"        {rr['ad']} {{ mode inside; levels ((1e15 {int(rr['level'])})); }}\n"
        for rr in rregions)
    txt += (
        "castellatedMeshControls\n{\n"
        f"    maxLocalCells       {max_local};\n"
        f"    maxGlobalCells      {case.max_global_cells};\n"
        "    minRefinementCells  10;\n"
        "    nCellsBetweenLevels 3;\n"
        "    maxLoadUnbalance    0.10;\n"
        "    features\n    (\n"
        f"        {{ file \"{surface_name}.eMesh\"; level {case.refinement_max}; }}\n"
        "    );\n"
        "    refinementSurfaces\n    {\n"
        f"        {surface_name}\n"
        "        {\n"
        f"            level ({case.refinement_min} {case.refinement_max});\n"
        "            patchInfo { type wall; }\n"
        "        }\n"
        "    }\n"
        "    refinementRegions\n    {\n" + rregion_txt + "    }\n"
        f"    locationInMesh ({inside_pt[0]:.6f} {inside_pt[1]:.6f} {inside_pt[2]:.6f});\n"
        "    allowFreeStandingZoneFaces true;\n"
        "    resolveFeatureAngle 30;\n"
        "}\n\n"
    )
    txt += (
        "snapControls\n{\n"
        "    nSmoothPatch    3;\n"
        "    tolerance       2.0;\n"
        "    nSolveIter      30;\n"
        "    nRelaxIter      5;\n"
        "    nFeatureSnapIter 10;\n"
        "    implicitFeatureSnap false;\n"
        "    explicitFeatureSnap true;\n"
        "    multiRegionFeatureSnap false;\n"
        "}\n\n"
    )
    if case.first_layer_thickness:
        h1 = case.first_layer_thickness
        sizing = (
            "    relativeSizes false;\n"
            f"    firstLayerThickness {h1:.6e};\n"
            f"    minThickness {h1 * 0.25:.6e};\n"
            "    expansionRatio 1.25;\n"
        )
    else:
        sizing = (
            "    relativeSizes true;\n"
            "    expansionRatio 1.2;\n"
            "    finalLayerThickness 0.5;\n"
            "    minThickness 0.1;\n"
        )
    txt += (
        "addLayersControls\n{\n"
        + sizing +
        "    layers\n    {\n"
        f"        {surface_name} {{ nSurfaceLayers {max(case.n_layers, 0)}; }}\n"
        "    }\n"
        "    nGrow 0;\n"
        "    featureAngle 130;\n"
        "    nRelaxIter 5;\n"
        "    nSmoothSurfaceNormals 1;\n"
        "    nSmoothNormals 3;\n"
        "    nSmoothThickness 10;\n"
        "    maxFaceThicknessRatio 0.5;\n"
        "    maxThicknessToMedialRatio 0.3;\n"
        "    minMedialAxisAngle 90;\n"
        "    nBufferCellsNoExtrude 0;\n"
        "    nLayerIter 50;\n"
        "}\n\n"
    )
    txt += (
        "meshQualityControls\n{\n"
        "    maxNonOrtho 65;\n"
        "    maxBoundarySkewness 20;\n"
        "    maxInternalSkewness 4;\n"
        "    maxConcave 80;\n"
        "    minVol 1e-13;\n"
        "    minTetQuality 1e-15;\n"
        "    minArea -1;\n"
        "    minTwist 0.02;\n"
        "    minDeterminant 0.001;\n"
        "    minFaceWeight 0.05;\n"
        "    minVolRatio 0.01;\n"
        "    minTriangleTwist -1;\n"
        "    nSmoothScale 4;\n"
        "    errorReduction 0.75;\n"
        "}\n\n"
        "writeFlags ( scalarLevels layerSets layerFields );\n"
        "mergeTolerance 1e-6;\n"
    )
    (case_dir / "system" / "snappyHexMeshDict").write_text(txt)


def _write_surface_features(case_dir: Path, stl_name: str) -> None:
    txt = _foam_header("dictionary", "surfaceFeaturesDict", "system")
    txt += (
        f"surfaces (\"{stl_name}\");\n\n"
        "includedAngle 150;\n"
        "subsetFeatures\n{\n    nonManifoldEdges no;\n    openEdges yes;\n}\n"
        "writeObj yes;\n"
    )
    (case_dir / "system" / "surfaceFeaturesDict").write_text(txt)


def _write_control_dict(case_dir: Path, case: CFDCase, surface_name: str,
                          lref: float, wake_x: float | None = None) -> None:
    txt = _foam_header("dictionary", "controlDict", "system")
    solver = "fluid" if case.compressible else "incompressibleFluid"
    txt += (
        "application     foamRun;\n"
        f"solver          {solver};\n\n"
        "startFrom       startTime;\n"
        "startTime       0;\n"
        "stopAt          endTime;\n"
        f"endTime         {case.end_time};\n"
        "deltaT          1;\n\n"
        "writeControl    timeStep;\n"
        f"writeInterval   {case.write_interval};\n"
        "purgeWrite      2;\n"
        "writeFormat     ascii;\n"
        "writePrecision  8;\n"
        "writeCompression off;\n"
        "timeFormat      general;\n"
        "timePrecision   6;\n"
        "runTimeModifiable true;\n\n"
    )
    fx, fy, fz = case.flow_direction
    # Lift yönü: akış yönüne dik, x-z düzleminde (alpha != 0'da (0,0,1) yanlış olur)
    lift = (-fz, 0.0, fx)
    norm = math.sqrt(lift[0]**2 + lift[2]**2) or 1.0
    lift = (lift[0]/norm, 0.0, lift[2]/norm)
    Aref = lref * lref
    txt += (
        "functions\n{\n"
        "    forceCoeffs1\n    {\n"
        "        type            forceCoeffs;\n"
        "        libs            (\"libforces.so\");\n"
        "        writeControl    timeStep;\n"
        "        writeInterval   1;\n"
        f"        patches         ({surface_name});\n"
        "        rho             rhoInf;\n"
        f"        rhoInf          {case.rho};\n"
        f"        liftDir         ({lift[0]} {lift[1]} {lift[2]});\n"
        f"        dragDir         ({fx} {fy} {fz});\n"
        "        CofR            (0 0 0);\n"
        "        pitchAxis       (0 1 0);\n"
        f"        pRef            {case.p_inf if case.compressible else 0};\n"
        f"        magUInf         {case.velocity};\n"
        f"        lRef            {lref:.6f};\n"
        f"        Aref            {Aref:.6f};\n"
        "    }\n"
    )
    # İz-düzlemi örnekleme (far-field momentum-açığı drag için U,p) — akış-dik kesit
    if wake_x is not None:
        txt += (
            "    wakePlane\n    {\n"
            "        type            surfaces;\n"
            "        libs            (\"libsampling.so\");\n"
            "        writeControl    writeTime;\n"
            "        surfaceFormat   vtk;\n"
            "        fields          (p U);\n"
            "        interpolationScheme cellPoint;\n"
            "        surfaces\n        (\n"
            "            wake\n            {\n"
            "                type        cutPlane;\n"
            "                planeType   pointAndNormal;\n"
            f"                point       ({wake_x:.6f} 0 0);\n"
            "                normal      (1 0 0);\n"
            "                interpolate true;\n"
            "            }\n        );\n"
            "    }\n"
        )
    txt += "}\n"
    (case_dir / "system" / "controlDict").write_text(txt)


def _write_fv_schemes(case_dir: Path) -> None:
    txt = _foam_header("dictionary", "fvSchemes", "system")
    txt += (
        "ddtSchemes      { default steadyState; }\n\n"
        "gradSchemes\n{\n"
        "    default         Gauss linear;\n"
        "    grad(U)         cellLimited Gauss linear 1;\n"
        "    grad(p)         Gauss linear;\n"
        "}\n\n"
        "divSchemes\n{\n"
        "    default                                 none;\n"
        "    div(phi,U)                              bounded Gauss linearUpwind grad(U);\n"
        "    div(phi,k)                              bounded Gauss upwind;\n"
        "    div(phi,omega)                          bounded Gauss upwind;\n"
        "    div(phi,nuTilda)                        bounded Gauss upwind;\n"
        "    div(phi,e)                              bounded Gauss upwind;\n"
        "    div(phi,h)                              bounded Gauss upwind;\n"
        "    div(phi,K)                              bounded Gauss upwind;\n"
        "    div(phi,Ekp)                            bounded Gauss upwind;\n"
        "    div(phid,p)                             Gauss upwind;\n"
        "    div(phi,(p|rho))                        Gauss upwind;\n"
        "    div(meshPhi,p)                          Gauss linear;\n"
        "    div((nuEff*dev2(T(grad(U)))))           Gauss linear;\n"
        "    div(((rho*nuEff)*dev2(T(grad(U)))))     Gauss linear;\n"
        "}\n\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n"
        "wallDist { method meshWave; }\n"
    )
    (case_dir / "system" / "fvSchemes").write_text(txt)


def _write_fv_solution(case_dir: Path, compressible: bool = False) -> None:
    txt = _foam_header("dictionary", "fvSolution", "system")
    txt += (
        "solvers\n{\n"
        "    p\n    {\n"
        "        solver          GAMG;\n"
        "        smoother        DICGaussSeidel;\n"
        "        tolerance       1e-06;\n"
        "        relTol          0.1;\n"
        "    }\n"
        "    \"(U|k|omega|nuTilda|e|h)\"\n    {\n"
        "        solver          smoothSolver;\n"
        "        smoother        symGaussSeidel;\n"
        "        tolerance       1e-06;\n"
        "        relTol          0.1;\n"
        "    }\n"
        "    rho\n    {\n"
        "        solver          diagonal;\n"
        "    }\n"
        "}\n\n"
        "SIMPLE\n{\n"
        "    nNonOrthogonalCorrectors 1;\n"
        "    consistent      yes;\n"
        "    residualControl\n    {\n"
        f"        p               {RESIDUAL_TARGET:g};\n"
        f"        U               {RESIDUAL_TARGET:g};\n"
        f"        \"(k|omega|nuTilda)\" {RESIDUAL_TARGET:g};\n"
        "    }\n"
        "}\n\n"
        # Sıkışabilir soğuk-başlangıç kararsızlığı (T<0 abort) için düşük
        # relaxation; sıkıştırılamaz yol hızlı kalır
        + ("relaxationFactors\n{\n"
           "    fields { p 0.2; rho 0.05; }\n"
           "    equations { U 0.3; \"(k|omega|nuTilda)\" 0.3; \"(e|h)\" 0.3; }\n"
           "}\n" if compressible else
           "relaxationFactors\n{\n"
           "    fields { p 0.3; }\n"
           "    equations { U 0.7; \"(k|omega|nuTilda)\" 0.7; }\n"
           "}\n")
    )
    (case_dir / "system" / "fvSolution").write_text(txt)


def _write_decompose_par(case_dir: Path, n: int) -> None:
    txt = _foam_header("dictionary", "decomposeParDict", "system")
    txt += (
        f"numberOfSubdomains {n};\n"
        "method scotch;\n"
    )
    (case_dir / "system" / "decomposeParDict").write_text(txt)


def _write_transport(case_dir: Path, nu: float) -> None:
    txt = _foam_header("dictionary", "transportProperties", "constant")
    txt += (
        "transportModel  Newtonian;\n"
        f"nu              [0 2 -1 0 0 0 0] {nu};\n"
    )
    (case_dir / "constant" / "transportProperties").write_text(txt)


def _write_momentum(case_dir: Path) -> None:
    """OpenFOAM 11: constant/momentumTransport"""
    txt = _foam_header("dictionary", "momentumTransport", "constant")
    txt += (
        "simulationType  RAS;\n\n"
        "RAS\n{\n"
        "    model           kOmegaSST;\n"
        "    turbulence      on;\n"
        "    printCoeffs     on;\n"
        "}\n"
    )
    (case_dir / "constant" / "momentumTransport").write_text(txt)


def _write_physical_properties(case_dir: Path, nu: float) -> None:
    """OF 11 incompressibleFluid solver: constant/physicalProperties"""
    txt = _foam_header("dictionary", "physicalProperties", "constant")
    txt += (
        "viscosityModel  constant;\n"
        f"nu              [0 2 -1 0 0 0 0] {nu};\n"
    )
    (case_dir / "constant" / "physicalProperties").write_text(txt)


def _write_physical_properties_compressible(case_dir: Path, case: CFDCase) -> None:
    """OF11 'fluid' çözücüsü: hePsiThermo + Sutherland hava."""
    txt = _foam_header("dictionary", "physicalProperties", "constant")
    txt += (
        "thermoType\n{\n"
        "    type            hePsiThermo;\n"
        "    mixture         pureMixture;\n"
        "    transport       sutherland;\n"
        "    thermo          hConst;\n"
        "    equationOfState perfectGas;\n"
        "    specie          specie;\n"
        "    energy          sensibleInternalEnergy;\n"
        "}\n\n"
        "mixture\n{\n"
        "    specie         { molWeight 28.96; }\n"
        "    thermodynamics { Cp 1005; Hf 0; }\n"
        "    transport      { As 1.4792e-06; Ts 116; }\n"
        "}\n"
    )
    (case_dir / "constant" / "physicalProperties").write_text(txt)


def _write_field_T(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    t = case.t_inf
    txt = _foam_header("volScalarField", "T", "0")
    txt += (
        "dimensions      [0 0 0 1 0 0 0];\n\n"
        f"internalField   uniform {t};\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform {t}; }}\n"
        f"    outlet  {{ type inletOutlet; inletValue uniform {t}; value uniform {t}; }}\n"
        "    top     { type zeroGradient; }\n"
        "    bottom  { type zeroGradient; }\n"
        "    front   { type zeroGradient; }\n"
        "    back    { type zeroGradient; }\n"
        f"    {surface_name} {{ type zeroGradient; }}\n"   # adyabatik duvar
        "}\n"
    )
    (case_dir / "0" / "T").write_text(txt)


def _write_field_alphat(case_dir: Path, surface_name: str) -> None:
    txt = _foam_header("volScalarField", "alphat", "0")
    txt += (
        "dimensions      [1 -1 -1 0 0 0 0];\n\n"
        "internalField   uniform 0;\n\n"
        "boundaryField\n{\n"
        "    inlet   { type calculated; value uniform 0; }\n"
        "    outlet  { type calculated; value uniform 0; }\n"
        "    top     { type calculated; value uniform 0; }\n"
        "    bottom  { type calculated; value uniform 0; }\n"
        "    front   { type calculated; value uniform 0; }\n"
        "    back    { type calculated; value uniform 0; }\n"
        f"    {surface_name} {{ type compressible::alphatWallFunction; value uniform 0; }}\n"
        "}\n"
    )
    (case_dir / "0" / "alphat").write_text(txt)


def _write_field_p_compressible(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    p = case.p_inf
    txt = _foam_header("volScalarField", "p", "0")
    txt += (
        "dimensions      [1 -1 -2 0 0 0 0];\n\n"
        f"internalField   uniform {p};\n\n"
        "boundaryField\n{\n"
        "    inlet   { type zeroGradient; }\n"
        f"    outlet  {{ type fixedValue; value uniform {p}; }}\n"
        "    top     { type slip; }\n"
        "    bottom  { type slip; }\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type zeroGradient; }}\n"
        "}\n"
    )
    (case_dir / "0" / "p").write_text(txt)


# 0/ field dosyaları
def _write_field_U(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    fx, fy, fz = case.flow_direction
    Ux, Uy, Uz = (case.velocity * fx, case.velocity * fy, case.velocity * fz)
    bottom = "{ type noSlip; }" if case.ground_clearance is not None else "{ type slip; }"
    txt = _foam_header("volVectorField", "U", "0")
    txt += (
        "dimensions      [0 1 -1 0 0 0 0];\n\n"
        f"internalField   uniform ({Ux} {Uy} {Uz});\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform ({Ux} {Uy} {Uz}); }}\n"
        "    outlet  { type inletOutlet; inletValue uniform (0 0 0); "
        f"value uniform ({Ux} {Uy} {Uz}); }}\n"
        f"    top     {{ type slip; }}\n"
        f"    bottom  {bottom}\n"
        f"    front   {{ type slip; }}\n"
        f"    back    {{ type slip; }}\n"
        f"    {surface_name} {{ type noSlip; }}\n"
        "}\n"
    )
    (case_dir / "0" / "U").write_text(txt)


def _write_field_p(case_dir: Path, surface_name: str, ground: bool = False) -> None:
    bottom = "{ type zeroGradient; }" if ground else "{ type slip; }"
    txt = _foam_header("volScalarField", "p", "0")
    txt += (
        "dimensions      [0 2 -2 0 0 0 0];\n\n"
        "internalField   uniform 0;\n\n"
        "boundaryField\n{\n"
        "    inlet   { type zeroGradient; }\n"
        "    outlet  { type fixedValue; value uniform 0; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type zeroGradient; }}\n"
        "}\n"
    )
    (case_dir / "0" / "p").write_text(txt)


def _write_field_k(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    I = case.turbulence_intensity
    k = 1.5 * (case.velocity * I) ** 2
    bottom = ("{ type kqRWallFunction; value uniform 1e-10; }"
              if case.ground_clearance is not None else "{ type slip; }")
    txt = _foam_header("volScalarField", "k", "0")
    txt += (
        "dimensions      [0 2 -2 0 0 0 0];\n\n"
        f"internalField   uniform {k:.6e};\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform {k:.6e}; }}\n"
        "    outlet  { type zeroGradient; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type kqRWallFunction; value uniform 1e-10; }}\n"
        "}\n"
    )
    (case_dir / "0" / "k").write_text(txt)


def _write_field_omega(case_dir: Path, case: CFDCase, surface_name: str, lref: float) -> None:
    I = case.turbulence_intensity
    k = 1.5 * (case.velocity * I) ** 2
    Cmu = 0.09
    l = 0.07 * lref
    omega = (k ** 0.5) / (Cmu ** 0.25 * l)
    bottom = (f"{{ type omegaWallFunction; value uniform {omega:.6e}; }}"
              if case.ground_clearance is not None else "{ type slip; }")
    txt = _foam_header("volScalarField", "omega", "0")
    txt += (
        "dimensions      [0 0 -1 0 0 0 0];\n\n"
        f"internalField   uniform {omega:.6e};\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform {omega:.6e}; }}\n"
        "    outlet  { type zeroGradient; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type omegaWallFunction; value uniform {omega:.6e}; }}\n"
        "}\n"
    )
    (case_dir / "0" / "omega").write_text(txt)


def _write_field_nut(case_dir: Path, surface_name: str, ground: bool = False) -> None:
    bottom = ("{ type nutUSpaldingWallFunction; value uniform 0; }"
              if ground else "{ type slip; }")
    txt = _foam_header("volScalarField", "nut", "0")
    txt += (
        "dimensions      [0 2 -1 0 0 0 0];\n\n"
        "internalField   uniform 0;\n\n"
        "boundaryField\n{\n"
        "    inlet   { type calculated; value uniform 0; }\n"
        "    outlet  { type calculated; value uniform 0; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type nutUSpaldingWallFunction; value uniform 0; }}\n"
        "}\n"
    )
    (case_dir / "0" / "nut").write_text(txt)


# ---------------------------------------------------------------------------
# Case oluşturma + çalıştırma
# ---------------------------------------------------------------------------

def build_case(case: CFDCase, out_dir: Path) -> Path:
    """Tüm OpenFOAM dosyalarını yaz, STL'i kopyala. case_dir döndür."""
    case_dir = (Path(out_dir) / case.name).resolve()
    if case_dir.exists():
        shutil.rmtree(case_dir)
    (case_dir / "0").mkdir(parents=True)
    (case_dir / "constant" / "triSurface").mkdir(parents=True)
    (case_dir / "system").mkdir(parents=True)

    # STL kopyala
    stl_name = case.stl_path.name
    surface_name = case.stl_path.stem.replace(" ", "_")
    shutil.copy(case.stl_path, case_dir / "constant" / "triSurface" / stl_name)

    # Domain
    dmin, dmax, gmin, gmax = _compute_domain(case.stl_path, case)
    size = gmax - gmin
    L = float(size.max())
    cell_size = case.bg_cell_size or (L / 10.0)

    # locationInMesh: geometri MERKEZİNİN biraz dışı olmalı (içinde olmamalı)
    # Akış yönünde geometri arkasında bir nokta seç
    cx = (gmin[0] + gmax[0]) * 0.5
    cy = (gmin[1] + gmax[1]) * 0.5
    cz = (gmin[2] + gmax[2]) * 0.5
    inside_pt = (cx + L * 2.0, cy + L * 0.1, cz + L * 0.1)

    ground = case.ground_clearance is not None
    _write_block_mesh(case_dir, dmin, dmax, cell_size, ground=ground)
    _write_snappy(case_dir, stl_name, surface_name, inside_pt, case)
    _write_surface_features(case_dir, stl_name)
    lref = L
    # İz-düzlemi: gövde arkası 2 boy (uzak-iz basınç toparlanması), domain içinde
    wake_x = float(gmax[0] + 2.0 * lref)
    _write_control_dict(case_dir, case, surface_name, lref, wake_x=wake_x)
    _write_fv_schemes(case_dir)
    _write_fv_solution(case_dir, case.compressible)
    n_proc = case.n_processors if case.n_processors > 0 else _default_processors()
    case.n_processors = n_proc  # downstream run_cfd için sabitle
    _write_decompose_par(case_dir, n_proc)
    _write_transport(case_dir, case.nu)
    _write_momentum(case_dir)
    if case.compressible:
        _write_physical_properties_compressible(case_dir, case)
    else:
        _write_physical_properties(case_dir, case.nu)

    _write_field_U(case_dir, case, surface_name)
    if case.compressible:
        _write_field_p_compressible(case_dir, case, surface_name)
        _write_field_T(case_dir, case, surface_name)
        _write_field_alphat(case_dir, surface_name)
    else:
        _write_field_p(case_dir, surface_name, ground=ground)
    _write_field_k(case_dir, case, surface_name)
    _write_field_omega(case_dir, case, surface_name, lref)
    _write_field_nut(case_dir, surface_name, ground=ground)

    if case.propeller:
        _write_propeller(case_dir, case.propeller, gmin, gmax, cell_size)

    if case.compressible:
        # Negatif-T abort koruması: sıcaklığı fiziksel banta kıs (geçici
        # ara-iterasyon taşmaları çözümü öldürmesin)
        (case_dir / "constant" / "fvConstraints").write_text(
            _foam_header("dictionary", "fvConstraints", "constant") +
            "limitT\n{\n    type      limitTemperature;\n"
            "    selectionMode all;\n    min       100;\n    max       1000;\n}\n")

    return case_dir


def _write_propeller(case_dir: Path, prop: dict, gmin, gmax, bg_cell: float):
    """Burnun önünde silindirik cellSet (topoSetDict) + actuationDiskSource.
    diskDir (-1 0 0): AMPİRİK doğrulama (küp testi) Usource'un ters
    konvansiyonla girdiğini gösterdi — +x diskDir akışı YAVAŞLATTI
    (sürükleme 16.5→11.6 N, türbin etkisi); pervane için dHat ters."""
    cap = prop["cap_m"]
    yc = float((gmin[1] + gmax[1]) / 2)
    zc = float((gmin[2] + gmax[2]) / 2)
    t = max(0.06 * cap, 3.0 * bg_cell)
    x2 = float(gmin[0]) - 0.02 * float(gmax[0] - gmin[0])
    x1 = x2 - t
    (case_dir / "system" / "topoSetDict").write_text(
        _foam_header("dictionary", "topoSetDict", "system") +
        "actions (\n"
        "  { name pervaneDisk; type cellSet; action new; source cylinderToCell;\n"
        f"    p1 ({x1:.6f} {yc:.6f} {zc:.6f}); p2 ({x2:.6f} {yc:.6f} {zc:.6f}); "
        f"radius {cap/2:.6f}; }}\n"
        ");\n")
    up = x1 - 1.5 * cap
    (case_dir / "constant" / "fvModels").write_text(
        _foam_header("dictionary", "fvModels", "constant") +
        "pervane\n{\n"
        "    type            actuationDiskSource;\n"
        "    select          cellSet;\n"
        "    cellSet         pervaneDisk;\n"
        "    diskDir         (-1 0 0);\n"
        f"    Cp              {prop['Cp']};\n"
        f"    Ct              {prop['Ct']};\n"
        f"    diskArea        {prop['area']:.6f};\n"
        f"    upstreamPoint   ({up:.6f} {yc:.6f} {zc:.6f});\n"
        "}\n")


def _wsl_run(wsl_dir: str, command: str, timeout: int) -> subprocess.CompletedProcess:
    """OF environment ile seçili Linux arka ucunda (wsl|docker) komut çalıştır."""
    full = f"{OF_ENV_PREFIX}cd '{wsl_dir}' && {command}"
    return linux_run(full, timeout)


# Uzun-koşan OF binary'leri: timeout/iptal'de WSL-içi orphan bırakmamak için
# (Windows-tarafı wsl.exe öldürmek WSL-içi süreç ağacını öldürmüyordu → orphan,
# aynı case'de çakışma, 50× yavaşlama — bu oturumun pahalı dersi).
_OF_BINS = ("foamRun", "snappyHexMesh", "blockMesh", "simpleFoam", "potentialFoam",
            "surfaceFeatures", "mpirun", "decomposePar", "reconstructPar")


def divergence_in_log(log_text: str) -> str | None:
    """foamRun logunda KESİN diverjans imzası ara (NaN/inf residual, FPE, solver crash).
    Çözücü timeout'a kadar koşup NaN üretse returncode 0 olabilir → garbage'ı yakala.
    'bounding k/omega' gibi NORMAL mesajları kasıtlı dışlar (yanlış-pozitif önleme)."""
    low = log_text.lower()
    if re.search(r"initial residual\s*=\s*[-+]?(nan|inf)\b", low):
        return "residual NaN/inf (diverjans)"
    if "floating point exception" in low:
        return "floating point exception (diverjans)"
    if re.search(r"#0\s+foam::error", low):
        return "solver crash (Foam::error)"
    return None


def _cd_plateau(cds, tol: float) -> bool:
    """Erken-durdurma kararı: uç-uca drift < tol VE pencere-genliği küçük olmalı.
    Salınımlı çözümde (keskin-kenar küt cisim, steady-SIMPLE) iki uç tesadüfen
    çakışıp drift<tol verebilir — erken kesmek faz-piyangosudur (küp dersi
    2026-07-12: AYNI mesh'te Cd 0.916↔1.097). Genlik büyükse end_time'a koşulur;
    raporlama katmanı pencere-ortalaması + genliği banda ekler."""
    drift = abs(cds[-1] - cds[0]) / (abs(cds[-1]) + 1e-12)
    if drift >= tol:
        return False
    mu = sum(cds) / len(cds)
    amp = (max(cds) - min(cds)) / 2.0
    return amp <= 2.0 * tol * (abs(mu) + 1e-12)


def _wrap_timeout(command: str, tmo: int) -> tuple[str, list[str]]:
    """Komutta OF binary varsa WSL-içi GNU timeout ile sar (orphan-önleme).
    Döndür: (sarılmış_komut, kill_edilecek_binary_listesi)."""
    bins = [b for b in _OF_BINS if b in command]
    if not bins:
        return command, []
    return f"timeout -k 10 -s TERM {max(tmo - 20, 30)} {command}", bins


def _wsl_kill(patterns) -> None:
    """WSL-içi orphan OF süreçlerini öldür (pkill -9 -f)."""
    if not patterns:
        return
    cmd = "; ".join(f"pkill -9 -f {p} 2>/dev/null" for p in patterns) + "; true"
    try:
        linux_run(cmd, 30)
    # sessiz-yutma: kabul — süreç zaten ölmüş olabilir; öldürme başarısızlığı sonucu etkilemez
    except Exception:
        pass


def run_cfd(case: CFDCase, out_dir: Path, timeout: int = 3600,
             progress_callback=None) -> CFDResult:
    """Case'i kur, mesh'i üret, çöz, sonuçları parse et."""
    case_dir = build_case(case, out_dir)
    wsl_dir = windows_to_wsl_path(case_dir)
    log_files: list[Path] = []
    all_stdout = []
    all_stderr = []

    # ext4 modu (CFD_EXT4=1, yalnız wsl): case çözüm süresince Linux-yerli diskte koşar —
    # drvfs(9p) paralel-yazım çökmesini (küre I/O vakası) kökten çözer + belirgin hız.
    # Solver bitince/başarısızlıkta içerik Windows tarafına geri kopyalanır.
    ext4 = ext4_enabled()
    exec_dir = wsl_dir
    if ext4:
        _home = linux_home()
        exec_dir = f"{_home}/cfd_runs/{case.name}"
        try:
            prep = linux_run(f"rm -rf '{exec_dir}' && mkdir -p '{_home}/cfd_runs' && "
                             f"cp -a '{wsl_dir}' '{exec_dir}'", 900)
            if prep.returncode != 0:
                raise RuntimeError(prep.stderr[-200:])
        except Exception as e:
            all_stderr.append(f"ext4 hazırlık başarısız — drvfs'te koşuluyor: {e}")
            exec_dir, ext4 = wsl_dir, False

    def _copy_back():
        nonlocal ext4
        if ext4:
            try:
                linux_run(f"cp -a '{exec_dir}/.' '{wsl_dir}/' && rm -rf '{exec_dir}'", 1800)
            except Exception as e:
                all_stderr.append(f"ext4 geri-kopyalama hatası: {e}")
            ext4 = False

    def _ret(res_obj):
        _copy_back()
        return res_obj

    def _step(percent: int, msg: str, command: str, log_name: str,
              tmo: int) -> subprocess.CompletedProcess | None:
        if progress_callback:
            progress_callback(percent, msg)
        # WSL-içi GNU timeout ile sar: süre aşılırsa WSL kendi süreç ağacını öldürür
        # (Windows-tarafı tmo backstop, biraz daha yüksek). Orphan'ı kökten önler.
        wrapped, bins = _wrap_timeout(command, tmo)
        try:
            r = _wsl_run(exec_dir, wrapped + f" > {log_name} 2>&1", timeout=tmo)
        except subprocess.TimeoutExpired as e:
            all_stderr.append(f"TIMEOUT in {log_name}: {e}")
            _wsl_kill(bins)            # Windows-tarafı aşımı: WSL orphan'larını öldür
            return None
        log_files.append(case_dir / log_name)
        all_stdout.append(f"--- {log_name} ---\n{r.stdout}")
        if r.stderr:
            all_stderr.append(f"--- {log_name} stderr ---\n{r.stderr}")
        return r

    def _foam_run_early_stop(command: str, tmo: int, msg: str,
                             window: int = 50, tol: float = 0.003) -> int:
        """foamRun'ı (seri ya da `mpirun ... -parallel`) arka planda koş; coefficient.dat'tan
        Cd'yi canlı izle; son `window` iterasyonda Cd-drifti `tol`un altına inince solver'ı
        orphan-güvenli öldür (erken yakınsama). Döner: returncode (0=ok, !=0=hata/timeout)."""
        if progress_callback:
            progress_callback(70, msg)
        wrapped, bins = _wrap_timeout(command, tmo)
        full = f"{OF_ENV_PREFIX}cd '{exec_dir}' && {wrapped} > log.foamRun 2>&1"
        proc = linux_popen(full)
        t0 = time.time(); early = False; n_iter = 0
        while proc.poll() is None:
            time.sleep(12)
            try:
                if ext4:
                    txt = _wsl_run(exec_dir, "cat postProcessing/forceCoeffs1/*/"
                                             "coefficient.dat 2>/dev/null || true",
                                   timeout=30).stdout
                    hist = parse_force_coeffs_text(txt)[3]
                else:
                    hist = parse_force_coeffs(case_dir)[3]
            except Exception:
                hist = []
            n_iter = len(hist)
            if n_iter >= 2 * window:
                cds = [h[1] for h in hist[-window:]]
                if _cd_plateau(cds, tol):
                    _wsl_kill(bins); early = True
                    break
            if time.time() - t0 > tmo:
                _wsl_kill(bins); break
        try:
            proc.wait(timeout=30)
        # sessiz-yutma: kabul — erken-durdurma İYİLEŞTİRMESİ; düşerse koşu tam süre devam eder (güvenli taraf)
        except Exception:
            pass
        log_files.append(case_dir / "log.foamRun")
        if early and progress_callback:
            progress_callback(72, f"Cd yakınsadı ({n_iter} iter, drift<{tol}) — erken durdu")
        return 0 if (early or proc.returncode == 0) else (proc.returncode or -1)

    # 1) surfaceFeatures
    r = _step(10, "surfaceFeatures...", "surfaceFeatures", "log.surfaceFeatures", 120)
    if r is None or r.returncode != 0:
        return _ret(CFDResult(case_dir=case_dir, success=False,
                              return_code=-1 if r is None else r.returncode,
                              stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                              log_files=log_files))

    # 2) blockMesh
    r = _step(20, "blockMesh...", "blockMesh", "log.blockMesh", 120)
    if r is None or r.returncode != 0:
        return _ret(CFDResult(case_dir=case_dir, success=False,
                              return_code=-1 if r is None else r.returncode,
                              stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                              log_files=log_files))

    # 3) snappyHexMesh
    r = _step(40, "snappyHexMesh (mesh adapsiyonu, en uzun adım)...",
              "snappyHexMesh -overwrite", "log.snappyHexMesh", 1800)
    if r is None or r.returncode != 0:
        return _ret(CFDResult(case_dir=case_dir, success=False,
                              return_code=-1 if r is None else r.returncode,
                              stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                              log_files=log_files))

    # 4) checkMesh (uyarılar normal, başarısızlık değil)
    _step(55, "checkMesh...", "checkMesh", "log.checkMesh", 300)

    # 4-gate) Mesh-kalite ön-geçidi: reject-kalite mesh'i ÇÖZÜCÜDEN ÖNCE ele
    # (negatif hacim / aşırı non-ortho-skew → çözücü saatlerce diverjyor/timeout).
    if ext4:
        cm_txt = _wsl_run(exec_dir, "cat log.checkMesh 2>/dev/null || true",
                          timeout=60).stdout
    else:
        cm = case_dir / "log.checkMesh"
        cm_txt = cm.read_text(errors="ignore") if cm.exists() else ""
    if cm_txt:
        mq = mesh_quality_gate(cm_txt)
        if mq["verdict"] == "reject":
            all_stderr.append("Mesh kalitesiz, çözücüye GÖNDERİLMEDİ: "
                              + "; ".join(mq["reasons"]))
            return _ret(CFDResult(case_dir=case_dir, success=False, return_code=-2,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))

    # 4b) topoSet (varsa — pervane diski cellSet'i vb.)
    if (case_dir / "system" / "topoSetDict").exists():
        r = _step(57, "topoSet (pervane diski)...", "topoSet", "log.topoSet", 300)
        if r is None or r.returncode != 0:
            return _ret(CFDResult(case_dir=case_dir, success=False,
                                  return_code=-1 if r is None else r.returncode,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))

    # 5) Solver: foamRun (OF 11) — çok işlemcili
    n = case.n_processors
    if n > 1:
        # mpirun bazı WSL kurulumlarında süresiz asılı kalıyor (worker'lar hiç
        # doğmuyor, log 0 bayt). 15 sn'lik smoke geçemezse seri koşuya düş.
        try:
            probe = _wsl_run(wsl_dir, "timeout 15 mpirun -np 2 true", timeout=40)
            mpi_ok = probe.returncode == 0
        except subprocess.TimeoutExpired:
            mpi_ok = False
        if not mpi_ok:
            all_stderr.append("UYARI: mpirun smoke testi başarısız/asılı — seri koşuya düşüldü")
            if progress_callback:
                progress_callback(58, "mpirun çalışmıyor — seri moda geçildi")
            n = 1
    if n > 1:
        r = _step(60, f"decomposePar ({n} işlemci)...",
                  "decomposePar -force", "log.decomposePar", 300)
        if r is None or r.returncode != 0:
            return _ret(CFDResult(case_dir=case_dir, success=False,
                                  return_code=-1 if r is None else r.returncode,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))
        # Paralel foamRun + CANLI Cd-yakınsama erken-durdurma (4 çekirdek × erken-stop)
        rc = _foam_run_early_stop(
            f"mpirun --oversubscribe -np {n} foamRun -parallel",
            max(timeout - 600, 600), f"foamRun (paralel SIMPLE, {n} çekirdek, Cd-izlemeli)...")
        if rc != 0:
            return _ret(CFDResult(case_dir=case_dir, success=False, return_code=rc,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))
        _step(95, "reconstructPar...", "reconstructPar -latestTime",
              "log.reconstructPar", 600)
    else:
        # Seri foamRun + CANLI Cd-yakınsama erken-durdurması: residualControl (1e-4)
        # çoğu kaba case'de plato yaptığından tetiklenmez → end_time'a kadar boşa koşar.
        # Cd (mühendislik niceliği) bir pencerede sabitlenince solver'ı temiz öldür → CPU.
        rc = _foam_run_early_stop("foamRun", max(timeout - 600, 600),
                                  "foamRun (seri SIMPLE, Cd-yakınsama izlemeli)...")
        if rc != 0:
            return _ret(CFDResult(case_dir=case_dir, success=False, return_code=rc,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))

    # Çözücü bitti → ext4 içeriği Windows tarafına al (diverjans/parse yerel dosyadan)
    _copy_back()

    # Diverjans bekçisi: solver returncode 0 olsa bile NaN/inf üretmiş olabilir
    # (timeout'a kadar koşup ıraksar). Garbage sonucu BAŞARILI sayma.
    solver_log = case_dir / "log.foamRun"
    if solver_log.exists():
        diverg = divergence_in_log(solver_log.read_text(errors="ignore"))
        if diverg:
            all_stderr.append(f"DIVERJANS: {diverg} — sonuç güvenilmez")
            return CFDResult(case_dir=case_dir, success=False, return_code=-2,
                             stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                             log_files=log_files)

    # 6) Force coefficients parse
    cd, cl, cm, history = parse_force_coeffs(case_dir)

    if progress_callback:
        progress_callback(100, "CFD tamamlandı")

    return CFDResult(
        case_dir=case_dir, success=True, return_code=0,
        stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
        cd=cd, cl=cl, cm=cm, forces_history=history, log_files=log_files,
    )


def parse_force_coeffs_text(text: str) -> tuple[float | None, float | None,
                                                float | None,
                                                list[tuple[int, float, float, float]]]:
    """coefficient.dat İÇERİĞİNİ parse et (ext4/uzak arka uçta canlı izleme için
    dosyasız sürüm). Returns: (Cd_son, Cl_son, Cm_son, [(iter, Cd, Cl, Cm), ...])"""
    history: list[tuple[int, float, float, float]] = []
    cd_idx = cl_idx = cm_idx = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            # Header satırı: # Time Cd Cs Cl ... formatı değişebilir
            if "Cd" in line or "Cm" in line:
                parts = line.lstrip("#").split()
                for i, p in enumerate(parts):
                    if p == "Cd":
                        cd_idx = i
                    elif p == "Cl":
                        cl_idx = i
                    elif p == "Cm":
                        cm_idx = i
            continue
        parts = line.split()
        try:
            t = int(float(parts[0]))
            cd = float(parts[cd_idx]) if cd_idx is not None and cd_idx < len(parts) else float("nan")
            cl = float(parts[cl_idx]) if cl_idx is not None and cl_idx < len(parts) else float("nan")
            cm = float(parts[cm_idx]) if cm_idx is not None and cm_idx < len(parts) else float("nan")
            history.append((t, cd, cl, cm))
        # sessiz-yutma: kabul — bozuk satır atlanır; BAŞLIK bulunamama durumu hemen altta AYRICA ele alınıp None döner (NaN üretilmez)
        except (ValueError, IndexError):
            continue
    # BAŞLIK BULUNAMADIYSA sahte sayı üretme: cd_idx/cl_idx/cm_idx None kalırsa her
    # satır NaN üretiyor ve history NaN'la doluyordu -> çağıran "Cd = nan" alıyordu.
    # (Fizik kapısı da NaN'ı ıskalıyordu; ikisi birleşince format değişimi sessizce
    # "Cd=nan, kapı ok" veriyordu.) Okunamadıysa dürüst cevap None'dır.
    if cd_idx is None and cl_idx is None and cm_idx is None:
        return None, None, None, []
    if not history:
        return None, None, None, history
    _, cd, cl, cm = history[-1]
    return cd, cl, cm, history


def parse_force_coeffs(case_dir: Path) -> tuple[float | None, float | None,
                                                  float | None,
                                                  list[tuple[int, float, float, float]]]:
    """postProcessing/forceCoeffs1/0/coefficient.dat'ı parse et."""
    candidates = list((case_dir / "postProcessing" / "forceCoeffs1").glob("*/coefficient.dat"))
    if not candidates:
        candidates = list((case_dir / "postProcessing" / "forceCoeffs1").glob("*/forceCoeffs.dat"))
    if not candidates:
        return None, None, None, []
    return parse_force_coeffs_text(candidates[0].read_text(errors="ignore"))
