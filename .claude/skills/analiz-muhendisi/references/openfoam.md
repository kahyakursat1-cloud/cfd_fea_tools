# OpenFOAM Reference Guide

## Table of Contents
1. [Case Directory Structure](#1-case-directory-structure)
2. [Mesh Generation](#2-mesh-generation)
3. [Boundary Conditions](#3-boundary-conditions)
4. [Solver Configuration](#4-solver-configuration)
5. [Numerical Schemes](#5-numerical-schemes)
6. [Turbulence Modeling](#6-turbulence-modeling)
7. [Parallel Execution](#7-parallel-execution)
8. [Post-Processing](#8-post-processing)
9. [Common Pitfalls & Debugging](#9-common-pitfalls--debugging)

---

## 1. Case Directory Structure

Every OpenFOAM case has three mandatory directories:

```
case/
├── 0/                  # Initial & boundary conditions
│   ├── p              # Pressure
│   ├── U              # Velocity
│   ├── k              # Turbulent kinetic energy (if RANS)
│   ├── omega          # Specific dissipation rate (if k-omega)
│   ├── nut            # Turbulent viscosity
│   └── epsilon        # Dissipation rate (if k-epsilon)
├── constant/
│   ├── transportProperties   # Fluid properties
│   ├── turbulenceProperties  # Turbulence model selection
│   └── polyMesh/             # Mesh files (generated)
│       ├── points
│       ├── faces
│       ├── owner
│       ├── neighbour
│       └── boundary
└── system/
    ├── controlDict           # Run control (solver, time, output)
    ├── fvSchemes             # Discretization schemes
    ├── fvSolution            # Linear solver & algorithm settings
    ├── blockMeshDict         # (if using blockMesh)
    ├── snappyHexMeshDict     # (if using snappyHexMesh)
    ├── decomposeParDict      # Parallel decomposition
    └── postProcessDict       # (optional) function objects
```

### FoamFile Header Template
Every OpenFOAM dictionary file must start with:
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       <CLASS>;    // dictionary, volScalarField, volVectorField, etc.
    object      <OBJECT>;   // filename (p, U, controlDict, etc.)
}
```

---

## 2. Mesh Generation

### blockMesh (structured meshes)

Best for: simple geometries (channels, pipes, boxes, wedges).

```cpp
// system/blockMeshDict
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}

convertToMeters 1.0;  // USER: scale factor

vertices
(
    (0   0   0)    // vertex 0
    (1   0   0)    // vertex 1
    (1   1   0)    // vertex 2
    (0   1   0)    // vertex 3
    (0   0   0.1)  // vertex 4
    (1   0   0.1)  // vertex 5
    (1   1   0.1)  // vertex 6
    (0   1   0.1)  // vertex 7
);

blocks
(
    // hex (vertices) (cells_x cells_y cells_z) grading
    hex (0 1 2 3 4 5 6 7) (100 50 1) simpleGrading (1 1 1)
    // USER: adjust cell counts for resolution
    // For wall-resolved y+ < 1: use grading near walls
    // Example grading: simpleGrading (1 ((0.2 0.3 0.1)(0.6 0.4 1)(0.2 0.3 10)) 1)
);

edges ();

boundary
(
    inlet
    {
        type patch;
        faces ((0 4 7 3));
    }
    outlet
    {
        type patch;
        faces ((1 2 6 5));
    }
    top
    {
        type wall;
        faces ((3 7 6 2));
    }
    bottom
    {
        type wall;
        faces ((0 1 5 4));
    }
    frontAndBack
    {
        type empty;  // 2D simulation
        faces
        (
            (0 3 2 1)
            (4 5 6 7)
        );
    }
);

mergePatchPairs ();
```

**Grading guide (wall resolution):**
- For y+ ≈ 1 (wall-resolved): first cell height ≈ y = (y+ × ν) / u_τ
- Use expansion ratio 1.1–1.3 from wall
- blockMesh grading: `simpleGrading` or `edgeGrading` for non-uniform spacing

### snappyHexMesh (complex geometries from STL)

Best for: any complex 3D geometry provided as .stl/.obj.

Key steps:
1. Create a background blockMesh (bounding box, coarse)
2. Configure snappyHexMeshDict with geometry, refinement, layers

```cpp
// system/snappyHexMeshDict — essential structure
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}

castellatedMesh true;
snap            true;
addLayers       true;  // USER: set false for initial testing

geometry
{
    myBody.stl
    {
        type triSurfaceMesh;
        name myBody;
    }
    // Refinement regions (optional)
    refinementBox
    {
        type searchableBox;
        min (-0.5 -0.5 -0.5);
        max ( 2.0  0.5  0.5);
    }
}

castellatedMeshControls
{
    maxLocalCells       1000000;
    maxGlobalCells      5000000;
    minRefinementCells  10;
    nCellsBetweenLevels 3;         // smoothing between levels
    maxLoadUnbalance    0.10;

    features
    (
        { file "myBody.eMesh"; level 2; }
    );

    refinementSurfaces
    {
        myBody
        {
            level (2 3);  // USER: (min max) refinement levels
        }
    }

    refinementRegions
    {
        refinementBox
        {
            mode inside;
            levels ((1E15 1));  // level 1 inside box
        }
    }

    locationInMesh (0 0 0);  // USER: point INSIDE the fluid domain
    allowFreeStandingZoneFaces true;
}

snapControls
{
    nSmoothPatch    3;
    tolerance       2.0;
    nSolveIter      100;
    nRelaxIter      5;
    nFeatureSnapIter 10;
}

addLayersControls
{
    relativeSizes   true;
    layers
    {
        myBody
        {
            nSurfaceLayers 5;  // USER: adjust for y+ target
        }
    }
    expansionRatio      1.2;
    finalLayerThickness 0.5;
    minThickness        0.001;
    nGrow               0;
    featureAngle        130;
    nRelaxIter          5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals      3;
    nSmoothThickness    10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle  90;
    nBufferCellsNoExtrude 0;
    nLayerIter          50;
}

meshQualityControls
{
    maxNonOrtho         65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave          80;
    minVol              1e-13;
    minTetQuality       1e-15;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.05;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
}
```

**Run sequence for snappyHexMesh:**
```bash
# 1. Extract surface features
surfaceFeatureExtract

# 2. Create background mesh
blockMesh

# 3. Run snappyHexMesh
snappyHexMesh -overwrite
# -overwrite keeps result in constant/polyMesh instead of numbered dirs

# 4. Check mesh quality
checkMesh
```

---

## 3. Boundary Conditions

### Common BC Types

| Physics | BC Type | OpenFOAM keyword |
|---|---|---|
| Velocity inlet | Fixed value | `fixedValue` |
| Pressure outlet | Fixed value | `fixedValue` |
| Wall (no-slip) | Fixed value (U=0) | `noSlip` or `fixedValue uniform (0 0 0)` |
| Symmetry plane | Symmetry | `symmetry` (patch type + BC) |
| Free-stream | Free-stream | `freestreamVelocity` / `freestreamPressure` |
| Inlet (turbulence) | Fixed value | See turbulence section |
| Wall (turbulence) | Wall function | `kqRWallFunction`, `omegaWallFunction`, `nutUSpaldingWallFunction` |
| 2D front/back | Empty | `empty` (patch type + BC) |
| Slip wall | Slip | `slip` |
| Inlet/outlet | Mixed | `inletOutlet` |
| Periodic | Cyclic | `cyclic` (patch type) |

### Template: Velocity (U) file
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    object      U;
}

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform (0 0 0);

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           uniform (10 0 0);  // USER: inlet velocity [m/s]
    }
    outlet
    {
        type            zeroGradient;
    }
    walls
    {
        type            noSlip;
    }
    frontAndBack
    {
        type            empty;
    }
}
```

### Template: Pressure (p) file — incompressible
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      p;
}

dimensions      [0 2 -2 0 0 0 0];  // kinematic pressure (p/rho)

internalField   uniform 0;

boundaryField
{
    inlet
    {
        type            zeroGradient;
    }
    outlet
    {
        type            fixedValue;
        value           uniform 0;
    }
    walls
    {
        type            zeroGradient;
    }
    frontAndBack
    {
        type            empty;
    }
}
```

---

## 4. Solver Configuration

### controlDict Template
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}

application     simpleFoam;  // USER: change solver

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         1000;        // USER: iterations (steady) or time (transient)
deltaT          1;           // USER: 1 for steady SIMPLE, calculate for transient

writeControl    timeStep;
writeInterval   100;         // USER: output frequency
purgeWrite      3;           // Keep only last N outputs (saves disk)

writeFormat     ascii;
writePrecision  8;
writeCompression off;

timeFormat      general;
timePrecision   6;

runTimeModifiable true;

// Function objects for monitoring
functions
{
    // USER: uncomment what you need

    /*
    forces
    {
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         (walls);     // USER: patch name(s)
        rho             rhoInf;
        rhoInf          1.225;       // USER: density [kg/m^3]
        CofR            (0 0 0);
    }
    */

    /*
    fieldAverage
    {
        type            fieldAverage;
        libs            (fieldFunctionObjects);
        writeControl    writeTime;
        fields
        (
            U { mean on; prime2Mean on; base time; }
            p { mean on; prime2Mean on; base time; }
        );
    }
    */
}
```

### fvSolution Template (SIMPLE)
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}

solvers
{
    p
    {
        solver          GAMG;
        smoother        DICGaussSeidel;
        tolerance       1e-06;
        relTol          0.1;
    }
    U
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-06;
        relTol          0.1;
    }
    k
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-06;
        relTol          0.1;
    }
    omega
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-06;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 1;  // USER: increase for non-orthogonal meshes
    consistent      yes;         // SIMPLEC algorithm (faster convergence)

    residualControl
    {
        p               1e-4;
        U               1e-4;
        k               1e-4;
        omega           1e-4;
    }
}

relaxationFactors
{
    fields
    {
        p               0.3;     // USER: reduce if diverging
    }
    equations
    {
        U               0.7;     // USER: reduce if diverging
        k               0.7;
        omega           0.7;
    }
}
```

---

## 5. Numerical Schemes

### fvSchemes Template (2nd order, stable)
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}

ddtSchemes
{
    default         steadyState;
    // For transient: Euler (1st), backward (2nd), CrankNicolson 0.9
}

gradSchemes
{
    default         Gauss linear;
    grad(p)         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;
}

divSchemes
{
    default         none;
    // Convection (momentum) — USER: linearUpwind for 2nd order, upwind if unstable
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    // Turbulence — upwind is usually sufficient
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    // Required for turbulence
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
    // For bad mesh: Gauss linear limited corrected 0.5
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
    // For bad mesh: limited corrected 0.5
}

wallDist
{
    method meshWave;
}
```

---

## 6. Turbulence Modeling

### turbulenceProperties
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      turbulenceProperties;
}

simulationType  RAS;

RAS
{
    RASModel        kOmegaSST;  // USER: kEpsilon, SpalartAllmaras, etc.
    turbulence      on;
    printCoeffs     on;
}
```

### Inlet Turbulence Estimation

Given freestream velocity U and characteristic length L:

```
Turbulence intensity: I = 0.01 to 0.10 (1%-10%)
  - External aero: I ≈ 0.01
  - Wind tunnel: I ≈ 0.005-0.02
  - Industrial pipe: I ≈ 0.05-0.10

k = 1.5 × (U × I)²
omega = k^0.5 / (C_mu^0.25 × l)    where l = 0.07×L, C_mu = 0.09
epsilon = C_mu × k^1.5 / l
nut = k / omega
```

### Wall Treatment

| Approach | y+ Target | Wall Function |
|---|---|---|
| Wall-resolved (low-Re) | y+ < 1 | `nutLowReWallFunction` / `omegaWallFunction` |
| Wall-modeled (high-Re) | 30 < y+ < 300 | `nutUSpaldingWallFunction` / `kqRWallFunction` |
| Automatic (SST blending) | y+ ~ 1 ideal | `nutUSpaldingWallFunction` + `omegaWallFunction` |

### k-omega SST Boundary Conditions Template
```
// 0/k
inlet:    fixedValue uniform <k_calculated>
outlet:   zeroGradient
walls:    kqRWallFunction uniform 1e-10

// 0/omega
inlet:    fixedValue uniform <omega_calculated>
outlet:   zeroGradient
walls:    omegaWallFunction uniform <omega_wall>
// omega_wall ≈ 6*nu / (beta1 * y1^2), beta1=0.075, y1=first cell height

// 0/nut
inlet:    calculated uniform 0
outlet:   calculated uniform 0
walls:    nutUSpaldingWallFunction uniform 0
```

---

## 7. Parallel Execution

### decomposeParDict
```cpp
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposeParDict;
}

numberOfSubdomains  4;  // USER: set to number of CPU cores

method          scotch;  // automatic load balancing (recommended)
// Alternative: method hierarchical; with coeffs below
/*
hierarchicalCoeffs
{
    n           (2 2 1);
    delta       0.001;
    order       xyz;
}
*/
```

### Run commands
```bash
# Decompose
decomposePar

# Run in parallel
mpirun -np 4 simpleFoam -parallel

# Reconstruct
reconstructPar

# Reconstruct specific time
reconstructPar -time 1000
```

---

## 8. Post-Processing

### Force coefficients (lift, drag)
```cpp
// In system/controlDict → functions {}
forceCoeffs
{
    type            forceCoeffs;
    libs            (forces);
    writeControl    timeStep;
    writeInterval   1;

    patches         (airfoil);    // USER: wall patch name
    rho             rhoInf;
    rhoInf          1.225;        // USER: freestream density
    liftDir         (0 1 0);      // USER: lift direction
    dragDir         (1 0 0);      // USER: drag direction
    CofR            (0.25 0 0);   // USER: moment reference point
    pitchAxis       (0 0 1);
    magUInf         30;           // USER: freestream velocity magnitude
    lRef            1.0;          // USER: reference length (chord)
    Aref            1.0;          // USER: reference area
}
```

### Sampling / Probes
```cpp
// system/sampleDict or inline in controlDict functions
probes
{
    type            probes;
    libs            (sampling);
    writeControl    timeStep;
    writeInterval   1;
    fields          (p U);
    probeLocations
    (
        (0.5 0.1 0.05)
        (1.0 0.1 0.05)
    );
}
```

### Useful post-processing commands
```bash
# Calculate y+ (run after simulation)
simpleFoam -postProcess -func yPlus

# Calculate wall shear stress
simpleFoam -postProcess -func wallShearStress

# Calculate Q-criterion (vortex identification)
simpleFoam -postProcess -func Q

# Convert to VTK for ParaView
foamToVTK
```

---

## 9. Common Pitfalls & Debugging

| Symptom | Likely Cause | Fix |
|---|---|---|
| Floating point exception | Bad mesh cells, wrong BC | Run `checkMesh`, fix negative volume cells |
| Divergence (Ux, p) | Too aggressive relaxation | Reduce URF to 0.3/0.5 for p/U, use upwind first |
| Residuals plateau | Mesh too coarse or wrong BC | Refine mesh, check outlet BC, check physical setup |
| Segfault in parallel | Decomposition issues | Check `decomposeParDict`, try `scotch` method |
| y+ too high | Insufficient near-wall resolution | Add boundary layers, reduce first cell height |
| Non-physical results | Wrong dimensions or units | Check `dimensions` in all 0/ files, verify units |
| `GAMG: No convergence` | Singular matrix (BC issue) | Ensure at least one fixed-value p patch |

### Debugging commands
```bash
checkMesh                        # Mesh quality report
checkMesh -allGeometry -allTopology  # Detailed check
simpleFoam -postProcess -func residuals  # Plot residuals
foamListTimes                    # List available time directories
foamLog log.simpleFoam           # Parse log for residuals → gnuplot data
```
