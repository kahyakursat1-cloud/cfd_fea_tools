# CalculiX Reference Guide

## Table of Contents
1. [Overview & Workflow](#1-overview--workflow)
2. [Input Deck Structure](#2-input-deck-structure)
3. [Element Library](#3-element-library)
4. [Material Models](#4-material-models)
5. [Boundary Conditions & Loads](#5-boundary-conditions--loads)
6. [Analysis Types](#6-analysis-types)
7. [Contact](#7-contact)
8. [Output & Post-Processing](#8-output--post-processing)
9. [Mesh Generation](#9-mesh-generation)
10. [Common Pitfalls & Debugging](#10-common-pitfalls--debugging)

---

## 1. Overview & Workflow

CalculiX consists of two programs:
- **CCX** (CalculiX CrunchiX): the solver — reads .inp files, produces .frd/.dat results
- **CGX** (CalculiX GraphiX): the pre/post-processor — mesh generation, visualization

**Typical workflow:**
```
Define geometry (CGX, Gmsh, or external mesher)
       │
       ▼
Create mesh → export as .inp format
       │
       ▼
Write input deck (.inp):
  - Nodes, Elements
  - Material, Section
  - Boundary conditions, Loads
  - Analysis step(s)
  - Output requests
       │
       ▼
Run solver: ccx jobname
       │
       ▼
Post-process: cgx -v jobname.frd
  (or export to ParaView via .vtk)
```

**What Claude can do for CalculiX tasks:**
- Generate complete .inp input decks from problem descriptions
- Create meshes for simple geometries using CGX batch scripts or inline node/element data
- Set up multi-step analyses (static → frequency, thermal → structural)
- Debug common .inp errors
- Write Python scripts for result extraction and plotting
- Generate Gmsh .geo files for complex 3D meshing → convert to CalculiX .inp

---

## 2. Input Deck Structure

A complete .inp file follows this order:

```
*HEADING
Description of the problem

** ============================================
** MESH DEFINITION
** ============================================
*NODE
nodeID, x, y, z
...

*ELEMENT, TYPE=<type>, ELSET=<name>
elemID, n1, n2, ..., nN
...

** Node and element sets for BCs and loads
*NSET, NSET=fix_nodes
nodeID1, nodeID2, ...
*NSET, NSET=load_nodes, GENERATE
startID, endID, increment

*ELSET, ELSET=body
elemID1, elemID2, ...

** Surfaces for pressure loads or contact
*SURFACE, NAME=top_surface, TYPE=ELEMENT
elsetName, S1

** ============================================
** MATERIAL & SECTION
** ============================================
*MATERIAL, NAME=steel
*ELASTIC
210000, 0.3
*DENSITY
7.85e-9
*EXPANSION
1.2e-5

*SOLID SECTION, ELSET=body, MATERIAL=steel

** ============================================
** ANALYSIS STEP(S)
** ============================================
*STEP
*STATIC
** or *FREQUENCY, *BUCKLE, *HEAT TRANSFER, etc.

** Boundary conditions
*BOUNDARY
fix_nodes, 1, 3, 0.0

** Loads
*CLOAD
load_nodes, 2, -1000.0

** Output requests
*NODE FILE
U, RF
*EL FILE
S, E
*NODE PRINT, NSET=load_nodes
U

*END STEP
```

### Syntax Rules
- Keywords start with `*` (case-insensitive)
- Comments start with `**`
- Data lines follow keyword lines
- Continuation: no explicit character needed, data continues until next `*` keyword
- Maximum 16 entries per data line, comma or space separated
- Node/element IDs are integers (1-based)

---

## 3. Element Library

### 3D Solid Elements

| Type | Description | Nodes | Best For |
|---|---|---|---|
| **C3D4** | Linear tetrahedron | 4 | Quick meshing, complex geometry (avoid for accuracy) |
| **C3D10** | Quadratic tetrahedron | 10 | General purpose, complex geometry ✓ |
| **C3D8** | Linear hexahedron | 8 | Structured meshes (beware shear locking) |
| **C3D8R** | Linear hex, reduced integration | 8 | General purpose hex (watch hourglassing) |
| **C3D20** | Quadratic hexahedron | 20 | High accuracy, structured meshes |
| **C3D20R** | Quadratic hex, reduced int. | 20 | Best accuracy/cost ratio for hex ✓ |
| **C3D6** | Linear wedge/prism | 6 | Transition elements |
| **C3D15** | Quadratic wedge | 15 | Better than C3D6 |

### Shell Elements

| Type | Description | Nodes | Notes |
|---|---|---|---|
| **S3** | Linear triangle | 3 | Avoid (too stiff) |
| **S6** | Quadratic triangle | 6 | OK for complex surfaces |
| **S4** | Linear quadrilateral | 4 | Good general shell |
| **S4R** | Linear quad, reduced int. | 4 | Watch hourglassing |
| **S8** | Quadratic quadrilateral | 8 | Good accuracy |
| **S8R** | Quadratic quad, reduced int. | 8 | Best shell element ✓ |

### Beam Elements

| Type | Description | Nodes |
|---|---|---|
| **B31** | Linear 2-node beam | 2 |
| **B32** | Quadratic 3-node beam | 3 |

### Other

| Type | Description |
|---|---|
| **SPRING1/2** | Spring elements (grounded/between nodes) |
| **DCOUP3D** | Distributing coupling (RBE3-like) |
| **MASS** | Point mass |
| **D** (type) | Thermal diffusion elements (prefix DC3D...) |

### Element Selection Guide
```
Complex 3D geometry → C3D10 (auto tet mesh from Gmsh/tetgen)
Structured simple geometry → C3D20R (best accuracy)
Thin-walled structures → S8R (with *SHELL SECTION)
Beams/frames → B31 or B32 (with *BEAM SECTION)
Thermal analysis → DC3D10 or DC3D20 (thermal counterparts)
```

---

## 4. Material Models

### Linear Elastic (Isotropic)
```
*MATERIAL, NAME=steel
*ELASTIC
210000, 0.3
** E [MPa], nu (if using mm/N/s unit system)
*DENSITY
7.85e-9
** rho [tonne/mm³] for mm/N/s system
```

### Linear Elastic (Orthotropic)
```
*ELASTIC, TYPE=ORTHO
E1, E2, E3, nu12, nu13, nu23, G12, G13
G23
```

### Elasto-Plastic (von Mises with hardening)
```
*MATERIAL, NAME=steel_plastic
*ELASTIC
210000, 0.3
*PLASTIC
** yield_stress, plastic_strain
250, 0.0
350, 0.05
450, 0.15
500, 0.30
*DENSITY
7.85e-9
```

### Thermal Properties
```
*CONDUCTIVITY
50.0
** k [W/(m·K)] or [mW/(mm·K)]

*SPECIFIC HEAT
480e6
** cp [mJ/(tonne·K)] for mm/N/s system
** Note: cp = 480 J/(kg·K) → 480e6 mJ/(tonne·K)
```

### Hyperelastic (Mooney-Rivlin for rubber)
```
*MATERIAL, NAME=rubber
*HYPERELASTIC, MOONEY-RIVLIN
C10, C01, D1
** C10 ≈ 0.5-2.0 MPa, C01 ≈ 0.1-0.5 MPa typical
** D1 = 2/K (K=bulk modulus) for near-incompressibility
```

### Common Material Properties (SI: m/kg/s and mm/tonne/s)

| Material | E [GPa] | ν | ρ [kg/m³] | σ_y [MPa] |
|---|---|---|---|---|
| Steel (mild) | 210 | 0.30 | 7850 | 250 |
| Aluminum 6061-T6 | 69 | 0.33 | 2700 | 276 |
| Titanium Ti-6Al-4V | 114 | 0.34 | 4430 | 880 |
| CFRP (quasi-iso) | 60-70 | 0.30 | 1600 | 600 (tensile) |
| Concrete | 30 | 0.20 | 2400 | — (compression: 30) |
| Copper | 117 | 0.34 | 8960 | 70 |

**Unit system reminder for CalculiX (no built-in units):**

| Quantity | m/kg/s | mm/tonne/s |
|---|---|---|
| Length | m | mm |
| Mass | kg | tonne (1000 kg) |
| Time | s | s |
| Force | N | N |
| Stress | Pa | MPa |
| Density | kg/m³ | tonne/mm³ (×1e-9) |
| Energy | J | mJ |

---

## 5. Boundary Conditions & Loads

### Displacement / Fixed BC
```
*BOUNDARY
** nodeID_or_nset, DOF_start, DOF_end, value
fix_all, 1, 3, 0.0          ** Fix x, y, z
fix_z, 3, 3, 0.0            ** Fix only z
prescribed, 1, 1, 0.5       ** Prescribe x displacement = 0.5
** DOFs: 1=x, 2=y, 3=z, 4=rotx, 5=roty, 6=rotz (beams/shells)
** For thermal: DOF 11 = temperature
```

### Symmetry Conditions
```
** X-symmetry plane (fix x-displacement):
*BOUNDARY
sym_x_nodes, 1, 1, 0.0

** Y-symmetry plane:
*BOUNDARY
sym_y_nodes, 2, 2, 0.0
```

### Concentrated Load
```
*CLOAD
** nodeID_or_nset, DOF, magnitude
load_point, 2, -5000.0      ** -5000 N in y-direction
```

### Distributed Load (Pressure)
```
** Define surface first
*SURFACE, NAME=top_face, TYPE=ELEMENT
elset_name, S2
** S1-S6 for hex face IDs; S1=tri face for tets; check element face numbering

*DLOAD
** element_or_surface, load_type, magnitude
top_face, P, 1.0            ** Pressure = 1.0 [Pa or MPa depending on units]
** Positive P = into face (compression)
```

### Gravity
```
*DLOAD
all_elements, GRAV, 9810, 0, 0, -1
** magnitude, direction_x, direction_y, direction_z
** 9810 mm/s² if using mm/tonne/s system
```

### Thermal Load (Temperature)
```
*TEMPERATURE
** nodeID_or_nset, temperature
all_nodes, 100.0
** Or from a thermal analysis result:
*TEMPERATURE, FILE=thermal_result
```

### Centrifugal Load
```
*DLOAD
all_elements, CENTRIF, omega², p1x, p1y, p1z, p2x, p2y, p2z
** omega² = angular_velocity², p1-p2 defines rotation axis
```

---

## 6. Analysis Types

### Static Analysis
```
*STEP
*STATIC
** For nonlinear (large displacement or plasticity):
*STEP, NLGEOM
*STATIC
0.1, 1.0, 0.01, 0.5
** init_increment, total_time, min_increment, max_increment

** BCs and loads here
*END STEP
```

### Frequency / Modal Analysis
```
*STEP
*FREQUENCY
10
** Number of eigenvalues to extract

** BCs only (no loads)
*BOUNDARY
fix_nodes, 1, 3, 0.0

*NODE FILE
U
*END STEP
```

### Buckling
```
*STEP
*BUCKLE
5
** Number of buckling modes

** Apply reference load
*CLOAD
top, 2, -1.0

*NODE FILE
U
*END STEP
```

### Steady-State Heat Transfer
```
*STEP
*HEAT TRANSFER, STEADY STATE

*BOUNDARY
hot_face, 11, 11, 500.0     ** Temperature BC (DOF 11)

*FILM
** element, face, sink_temp, h_coefficient
cold_face, F2, 25.0, 10.0

*RADIATE
** element, face, sink_temp, emissivity
outer_face, R2, 25.0, 0.8

*NODE FILE
NT                           ** Nodal temperature
*END STEP
```

### Coupled Thermo-Mechanical
```
** Step 1: Thermal
*STEP
*HEAT TRANSFER, STEADY STATE
** thermal BCs...
*NODE FILE
NT
*END STEP

** Step 2: Mechanical (reads temperatures from step 1)
*STEP
*STATIC
*TEMPERATURE
** Reads from previous step automatically
*BOUNDARY
fix_nodes, 1, 3, 0.0
*NODE FILE
U
*EL FILE
S
*END STEP

** OR: use coupled elements (C3D10T) with:
*STEP
*UNCOUPLED TEMPERATURE-DISPLACEMENT
```

### Multi-Step Example (Pretension → Operating Load)
```
*STEP
*STATIC
** Step 1: Bolt pretension
*BOUNDARY
bolt_nodes, 2, 2, -0.1     ** Apply bolt stretch
*END STEP

*STEP
*STATIC
** Step 2: Operating pressure (bolt BC maintained)
*DLOAD
pressure_face, P, 10.0
*NODE FILE
U, RF
*EL FILE
S
*END STEP
```

---

## 7. Contact

### Surface-to-Surface Contact
```
** Define contact surfaces
*SURFACE, NAME=master_surf, TYPE=ELEMENT
master_elset, S1

*SURFACE, NAME=slave_surf, TYPE=ELEMENT
slave_elset, S3

** Contact pair
*CONTACT PAIR, INTERACTION=contact1, TYPE=SURFACE TO SURFACE
slave_surf, master_surf

** Contact properties
*SURFACE INTERACTION, NAME=contact1
*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=HARD
** Alternative: PRESSURE-OVERCLOSURE=LINEAR with stiffness

*FRICTION
0.3
** Friction coefficient (0 for frictionless)
```

### TIE Constraint (bonded contact)
```
*TIE, NAME=bonded1, POSITION TOLERANCE=0.1
slave_surface, master_surface
```

### Contact Tips
- Slave surface should be the finer mesh
- Use `NLGEOM` for contact problems (large sliding)
- Start with frictionless, add friction after convergence
- If convergence issues: reduce increment size, add damping

---

## 8. Output & Post-Processing

### Output Requests

```
** Nodal results to .frd (for CGX/ParaView)
*NODE FILE
U        ** Displacements
RF       ** Reaction forces
NT       ** Temperatures

** Element results to .frd
*EL FILE
S        ** Stresses (all components)
E        ** Strains
PEEQ     ** Equivalent plastic strain
HFL      ** Heat flux

** Printed output to .dat (text)
*NODE PRINT, NSET=monitor_nodes
U, RF
*EL PRINT, ELSET=critical_elements
S
```

### CGX Post-Processing Commands
```bash
# Open results
cgx -v jobname.frd

# Common CGX commands:
# ds 1 e 1         → select dataset 1 (e.g., step 1), entity 1 (e.g., Ux)
# ds 1 e 7         → von Mises stress (entity 7 in stress dataset)
# plot f all        → plot filled contours on all elements
# plot e all        → plot edges
# plus e nset_name  → highlight a node set
# view front        → front view
# view iso          → isometric view
# max               → show max value location
# min               → show min value location
# send all abq      → export to Abaqus format
# send all vtk      → export to VTK format
# quit              → exit
```

### Python Script: Extract Results from .frd
```python
def parse_frd_nodal(filename, step=1, field='DISP'):
    """Extract nodal results from CalculiX .frd file.
    
    Args:
        filename: path to .frd file
        step: step number
        field: 'DISP', 'FORC', 'STRESS', 'NDTEMP' etc.
    
    Returns:
        dict: {node_id: [v1, v2, v3, ...]}
    """
    results = {}
    reading = False
    current_step = 0
    
    with open(filename, 'r') as f:
        for line in f:
            if line.startswith(' 2C'):
                # New dataset header
                current_step += 1
            if line.strip().startswith('-4') and field in line:
                if current_step == step:
                    reading = True
                    continue
            if reading:
                if line.startswith(' -3'):
                    reading = False
                    break
                if line.startswith(' -1'):
                    node_id = int(line[3:13])
                    vals = [float(line[13+i*12:25+i*12]) for i in range(
                        min(3, (len(line.rstrip())-13)//12))]
                    results[node_id] = vals
                elif line.startswith(' -2'):
                    # Continuation line
                    node_id = list(results.keys())[-1]
                    extra = [float(line[13+i*12:25+i*12]) for i in range(
                        min(3, (len(line.rstrip())-13)//12))]
                    results[node_id].extend(extra)
    return results
```

### Convert .frd to VTK (for ParaView)
```bash
# Using CGX batch mode:
echo -e "read jobname.frd\nsend all vtk\nquit" | cgx -bg

# Or use ccx2paraview (Python tool):
pip install ccx2paraview
ccx2paraview jobname.frd vtk
```

---

## 9. Mesh Generation

### Using Gmsh → CalculiX

Gmsh is the most common external mesher for CalculiX.

**Gmsh .geo file template (3D solid):**
```
// Gmsh geometry file
SetFactory("OpenCASCADE");

// Simple box example
Box(1) = {0, 0, 0,  100, 20, 5};
// {x, y, z, dx, dy, dz}

// Mesh size
Mesh.CharacteristicLengthMin = 1;
Mesh.CharacteristicLengthMax = 3;

// Physical groups (become element sets in CalculiX)
Physical Volume("body") = {1};
Physical Surface("fix_face") = {1};     // check face IDs in GUI
Physical Surface("load_face") = {2};

// Generate 2nd order tetrahedra
Mesh.ElementOrder = 2;
Mesh 3;

// Export
Save "model.inp";
```

**Run Gmsh:**
```bash
gmsh model.geo -3 -format inp -o model.inp
# -3 = generate 3D mesh
# -format inp = CalculiX/Abaqus format

# For hex-dominant mesh (if geometry allows):
gmsh model.geo -3 -algo hxt -recombine3d -format inp -o model.inp
```

**Gmsh output cleanup:** Gmsh exports Abaqus-compatible .inp files. For CalculiX:
- Node sets from Physical surfaces work directly
- Element sets from Physical volumes work directly
- Element types may need mapping: Gmsh C3D10 → CalculiX C3D10 (usually compatible)
- Remove any Abaqus-specific keywords CalculiX doesn't support

### Using CGX for Simple Geometries
```bash
# CGX batch script for a meshed plate
cgx -bg << EOF
pnt p1 0 0 0
pnt p2 100 0 0
pnt p3 100 50 0
pnt p4 0 50 0
line l1 p1 p2 20
line l2 p2 p3 10
line l3 p3 p4 20
line l4 p4 p1 10
surf s1 l1 l2 l3 l4
body b1 s1 0 0 5 2
# extrude surface s1 by 5mm with 2 divisions

mesh all
send all abq
# Writes mesh in Abaqus/CCX format
quit
EOF
```

---

## 10. Common Pitfalls & Debugging

| Symptom | Likely Cause | Fix |
|---|---|---|
| `*ERROR: zero pivot` | Unconstrained rigid body motion | Add sufficient BCs (6 DOFs for 3D) |
| `*ERROR: too many iterations` | Nonlinear convergence failure | Reduce increment size, check contact, add NLGEOM |
| Stress singularity at BC | Point load/constraint | Use distributed load, smooth BC with coupling |
| Elements distorted | Poor mesh quality | Re-mesh with better element size, check geometry |
| Wrong stress magnitudes | Unit inconsistency | Verify E, rho, loads all in same unit system |
| `*ERROR: element type not supported` | Wrong element type string | Check spelling, e.g., C3D10 not C3d10 |
| Thermal + mechanical mismatch | Wrong element type for coupled | Use thermal elements (DC3D10) or coupled (C3D10T) |
| Contact doesn't work | Wrong surface normals or pairing | Check master/slave, use NLGEOM, verify surface definitions |
| Eigenvalues negative | BCs insufficient | Ensure structure is properly constrained |
| Results look wrong in CGX | Wrong dataset/entity selected | Use `ds N e M` to select correct step and field |

### Debugging Commands
```bash
# Run with verbose output
ccx -i jobname

# Check the .sta file for convergence info
cat jobname.sta

# Check the .cvg file for convergence history
cat jobname.cvg

# The .dat file contains printed output
cat jobname.dat

# Verify mesh in CGX before solving
cgx -v model.inp
# Then: plot e all (check element shapes)
# Then: plus n nset_name (verify node sets)
```

### Convergence Tips for Nonlinear Analysis
1. Start with a linear analysis to verify setup
2. Enable `NLGEOM` only when needed (large deformation, contact)
3. Use small initial increments: `*STATIC, 0.01, 1.0, 1e-5, 0.1`
4. For contact: start with `*CONTACT PAIR, ADJUST=0.1` to close initial gaps
5. Monitor .sta file for force residuals
6. If plasticty: ensure hardening curve covers expected strain range
