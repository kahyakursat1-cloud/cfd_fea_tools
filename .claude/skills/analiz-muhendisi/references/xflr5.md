# XFLR5 Reference Guide

## Table of Contents
1. [Overview & Workflow](#1-overview--workflow)
2. [Airfoil Coordinate Files](#2-airfoil-coordinate-files)
3. [Direct Foil Analysis (XFoil)](#3-direct-foil-analysis-xfoil)
4. [Wing & Plane Analysis](#4-wing--plane-analysis)
5. [Result Interpretation](#5-result-interpretation)
6. [Generating Files Programmatically](#6-generating-files-programmatically)
7. [Common Pitfalls](#7-common-pitfalls)

---

## 1. Overview & Workflow

XFLR5 is a GUI tool wrapping XFoil (2D airfoil analysis) with extensions for 3D wing
analysis using lifting-line theory (LLT), vortex lattice method (VLM), and 3D panel
methods.

**Typical workflow:**
```
Define airfoil (.dat)
       │
       ▼
Run 2D polar analysis (XFoil engine)
  - Set Reynolds number(s)
  - Set Mach number (compressibility correction)
  - Set transition (forced or free, Ncrit)
       │
       ▼
(Optional) Define wing geometry
  - Planform: span, chord, sweep, twist, dihedral
  - Assign airfoils to wing sections
       │
       ▼
Run 3D analysis (LLT / VLM / Panel)
       │
       ▼
Extract results: CL-alpha, CL-CD, Cm, span loading, induced drag
```

**What Claude can do for XFLR5 tasks:**
- Generate .dat airfoil coordinate files (NACA or custom)
- Generate batch analysis scripts for XFoil (command-line XFoil)
- Create comparison plots of airfoil polars
- Help interpret results and choose airfoils
- Calculate wing geometry parameters
- Prepare XML project files for XFLR5 import

---

## 2. Airfoil Coordinate Files

### .dat File Format
```
<Airfoil Name>
  x1    y1
  x2    y2
  ...
```

**Rules:**
- First line: airfoil name (text)
- Coordinates: x/c and y/c (normalized by chord, 0 to 1)
- Start from trailing edge upper surface (x=1), go around leading edge (x=0),
  back to trailing edge lower surface (x=1)
- OR: Selig format — upper surface first (LE to TE), then lower surface (LE to TE)
- Lednicer format — number of points header, upper surface block, blank line, lower surface block
- XFLR5 accepts all common formats

### NACA 4-Digit Generation

For NACA MPXX:
- M = max camber (% chord) / 100
- P = location of max camber (tenths of chord) / 10
- XX = max thickness (% chord) / 100

**Thickness distribution (NACA 4-digit):**
```
yt = (t/0.2) × (0.2969√x - 0.1260x - 0.3516x² + 0.2843x³ - 0.1015x⁴)
```
Note: use -0.1036x⁴ for closed trailing edge.

**Camber line:**
```
For x ≤ P:  yc = (M/P²)(2Px - x²)
For x > P:  yc = (M/(1-P)²)((1-2P) + 2Px - x²)
```

**Upper/lower surfaces:**
```
xu = x - yt×sin(θ)    yu = yc + yt×cos(θ)
xl = x + yt×sin(θ)    yl = yc - yt×cos(θ)
where θ = atan(dyc/dx)
```

### NACA 5-Digit and Laminar-Flow Series

For NACA 5-digit (e.g., 23012) and 6-series (e.g., 63-215), the formulas are more
complex. **Recommended approach:** use a Python script to generate coordinates from
established algorithms, or look up coordinate databases.

### Common Airfoil Database Sources
When user asks for a specific airfoil, generate coordinates if NACA 4-digit, otherwise
note that .dat files for most airfoils are available from UIUC Airfoil Database or
Airfoil Tools. Claude can generate common profiles programmatically.

---

## 3. Direct Foil Analysis (XFoil)

### XFoil Batch Script (command-line)

When users need automated analysis without the XFLR5 GUI, generate XFoil batch scripts:

```bash
#!/bin/bash
# XFoil batch analysis script
xfoil << EOF
LOAD airfoil.dat
PANE
OPER
VISC 500000
MACH 0.0
ITER 200
VPAR
N 9
XTR 1.0 1.0

PACC
polar_output.txt

ASEQ -5 15 0.5
PACC

QUIT
EOF
```

**Key XFoil commands:**
| Command | Description |
|---|---|
| `LOAD file.dat` | Load airfoil |
| `NACA XXXX` | Generate NACA airfoil |
| `PANE` | Re-panel airfoil (smooth) |
| `OPER` | Enter analysis mode |
| `VISC Re` | Set Reynolds number, enable viscous |
| `MACH M` | Set Mach number |
| `ITER N` | Max iterations per point |
| `ALFA α` | Analyze single angle of attack |
| `ASEQ α1 α2 dα` | Analyze alpha sequence |
| `PACC file` | Start/stop polar accumulation |
| `VPAR` → `N val` | Set Ncrit (turbulence transition) |
| `VPAR` → `XTR top bot` | Force transition location (0-1) |

### Ncrit Guidelines
| Environment | Ncrit |
|---|---|
| Sailplane in clean air | 12-14 |
| Average wind tunnel | 9 (default) |
| Dirty/turbulent environment | 4-6 |
| Outdoor (general) | 5-8 |

### Reynolds Number Reference
```
Re = ρ × V × c / μ

Common values:
- RC model aircraft (c=0.15m, V=15m/s): Re ≈ 150,000
- Small UAV (c=0.3m, V=25m/s):          Re ≈ 500,000
- GA aircraft (c=1.5m, V=60m/s):        Re ≈ 6,000,000
- Commercial airliner (c=5m, V=230m/s):  Re ≈ 50,000,000+
```

---

## 4. Wing & Plane Analysis

### Wing Geometry Parameters

When user provides wing specs, calculate:

```
Aspect Ratio:        AR = b² / S   (or b / c_mean)
Mean Aero Chord:     MAC = (2/S) ∫ c(y)² dy
Taper Ratio:         λ = c_tip / c_root
Sweep (quarter-chord): Λ_c/4
Oswald Efficiency:   e ≈ 1.78(1 - 0.045×AR^0.68) - 0.64  (Raymer approx.)
```

### XFLR5 Wing Definition

In XFLR5, wings are defined by spanwise sections:

| y position [m] | Chord [m] | Offset [m] | Dihedral [°] | Twist [°] | Airfoil |
|---|---|---|---|---|---|
| 0.0 | 0.30 | 0.0 | 0.0 | 2.0 | NACA 2412 |
| 1.5 | 0.30 | 0.0 | 3.0 | 0.0 | NACA 2412 |
| 5.0 | 0.15 | 0.05 | 3.0 | -1.0 | NACA 0009 |

**Key parameters per section:**
- **y position**: spanwise station (half-span, measured from root)
- **Chord**: local chord length
- **Offset**: x-offset of leading edge from root LE (defines sweep)
- **Dihedral**: angle between this section and previous
- **Twist**: geometric twist (washout = negative at tip)
- **Airfoil**: must have a polar already computed at relevant Re

### 3D Analysis Methods

| Method | Best For | Limitations |
|---|---|---|
| **LLT** (Lifting Line) | High AR wings, quick estimates | No sweep, no low AR, no fuselage |
| **VLM** (Vortex Lattice) | Swept/tapered wings, moderate AR | No thickness, no viscous effects |
| **3D Panel** | Bodies + wings, thickness effects | Slow, inviscid (uses 2D polars for viscous correction) |

**Analysis settings:**
- For LLT: 20-40 spanwise stations is typically sufficient
- For VLM: 20×10 to 40×20 panels (span × chord) for most wings
- All methods use XFoil polars for viscous drag estimation — ensure polars cover
  the local Re and alpha range the wing will encounter

---

## 5. Result Interpretation

### 2D Polar Curves (Airfoil)

| Plot | What to Look For |
|---|---|
| CL vs α | Linear region slope (~2π/rad ≈ 0.11/deg for thin airfoils), stall angle, max CL |
| CD vs α | Drag bucket (laminar airfoils), drag rise near stall |
| CL vs CD (drag polar) | L/D max = tangent from origin, operating range |
| CM vs α | Pitching moment slope (negative = stable), zero-lift moment |
| Transition (Xtr) vs α | Where transition occurs on upper/lower surface |

**Key performance metrics:**
```
CL_max:     Maximum lift coefficient (stall boundary)
CL/CD_max:  Maximum lift-to-drag ratio (endurance/range efficiency)
CD_min:     Minimum drag (high-speed performance)
CM_0:       Zero-lift moment (trim drag implications)
α_0L:       Zero-lift angle (airfoil camber indicator)
```

### 3D Wing Results

| Result | Meaning |
|---|---|
| CL vs α (wing) | Wing lift curve — lower slope than 2D due to finite span |
| Span loading | cl×c/CL×c_ref vs y/b — compare to elliptic for induced drag |
| Induced drag | CDi = CL²/(π×AR×e) — check Oswald efficiency |
| Bending moment | Integrate span loading for structural loads |
| Local α | Effective angle of attack across span — check for tip stall |

---

## 6. Generating Files Programmatically

### Python Script: NACA 4-Digit Airfoil Generator
```python
import numpy as np

def naca4(number, n_points=100, closed_te=True):
    """Generate NACA 4-digit airfoil coordinates.
    
    Args:
        number: 4-digit string, e.g. '2412'
        n_points: points per surface
        closed_te: close trailing edge
    
    Returns:
        x, y arrays (upper surface TE→LE, then lower surface LE→TE)
    """
    m = int(number[0]) / 100.0
    p = int(number[1]) / 10.0
    t = int(number[2:]) / 100.0
    
    # Cosine spacing for better LE resolution
    beta = np.linspace(0, np.pi, n_points)
    x = 0.5 * (1 - np.cos(beta))
    
    # Thickness
    c4 = -0.1036 if closed_te else -0.1015
    yt = 5 * t * (0.2969*np.sqrt(x) - 0.1260*x - 0.3516*x**2 
                   + 0.2843*x**3 + c4*x**4)
    
    # Camber
    yc = np.zeros_like(x)
    dyc = np.zeros_like(x)
    if m > 0 and p > 0:
        front = x <= p
        back = x > p
        yc[front] = (m/p**2) * (2*p*x[front] - x[front]**2)
        yc[back] = (m/(1-p)**2) * ((1-2*p) + 2*p*x[back] - x[back]**2)
        dyc[front] = (2*m/p**2) * (p - x[front])
        dyc[back] = (2*m/(1-p)**2) * (p - x[back])
    
    theta = np.arctan(dyc)
    
    xu = x - yt * np.sin(theta)
    yu = yc + yt * np.cos(theta)
    xl = x + yt * np.sin(theta)
    yl = yc - yt * np.cos(theta)
    
    # Combine: upper (TE→LE) + lower (LE→TE)
    x_all = np.concatenate([xu[::-1], xl[1:]])
    y_all = np.concatenate([yu[::-1], yl[1:]])
    
    return x_all, y_all

def write_dat(filename, name, x, y):
    """Write airfoil .dat file."""
    with open(filename, 'w') as f:
        f.write(f"{name}\n")
        for xi, yi in zip(x, y):
            f.write(f"  {xi:.6f}  {yi:.6f}\n")

# Example usage:
# x, y = naca4('4412', n_points=120)
# write_dat('NACA4412.dat', 'NACA 4412', x, y)
```

### Python Script: XFoil Polar Parser
```python
def parse_xfoil_polar(filename):
    """Parse XFoil polar output file.
    
    Returns: dict with keys 'alpha', 'CL', 'CD', 'CDp', 'CM', 'Top_Xtr', 'Bot_Xtr'
    """
    data = {'alpha':[], 'CL':[], 'CD':[], 'CDp':[], 'CM':[], 
            'Top_Xtr':[], 'Bot_Xtr':[]}
    reading = False
    with open(filename, 'r') as f:
        for line in f:
            if '-------' in line:
                reading = True
                continue
            if reading and line.strip():
                vals = line.split()
                if len(vals) >= 7:
                    data['alpha'].append(float(vals[0]))
                    data['CL'].append(float(vals[1]))
                    data['CD'].append(float(vals[2]))
                    data['CDp'].append(float(vals[3]))
                    data['CM'].append(float(vals[4]))
                    data['Top_Xtr'].append(float(vals[5]))
                    data['Bot_Xtr'].append(float(vals[6]))
    return data
```

### Python Script: Polar Comparison Plot
```python
import matplotlib.pyplot as plt

def plot_polar_comparison(polars, names, save_path=None):
    """Plot CL-alpha and CL-CD comparison.
    
    Args:
        polars: list of parsed polar dicts
        names: list of airfoil names
        save_path: optional file path to save figure
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    for polar, name in zip(polars, names):
        axes[0].plot(polar['alpha'], polar['CL'], label=name)
        axes[1].plot(polar['CD'], polar['CL'], label=name)
        ld = [cl/cd if cd > 0 else 0 for cl, cd in zip(polar['CL'], polar['CD'])]
        axes[2].plot(polar['alpha'], ld, label=name)
    
    axes[0].set_xlabel('α [°]')
    axes[0].set_ylabel('CL')
    axes[0].set_title('Lift Curve')
    axes[0].legend()
    axes[0].grid(True)
    
    axes[1].set_xlabel('CD')
    axes[1].set_ylabel('CL')
    axes[1].set_title('Drag Polar')
    axes[1].legend()
    axes[1].grid(True)
    
    axes[2].set_xlabel('α [°]')
    axes[2].set_ylabel('CL/CD')
    axes[2].set_title('Lift-to-Drag Ratio')
    axes[2].legend()
    axes[2].grid(True)
    
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.show()
```

---

## 7. Common Pitfalls

| Problem | Cause | Solution |
|---|---|---|
| XFoil won't converge at high α | Separation/stall | Reduce α step, increase ITER to 300+, check Ncrit |
| CL-alpha curve has gaps | Unconverged points skipped | Re-run with finer α steps near problem region |
| Drag too low (laminar) | Wrong Ncrit | Use lower Ncrit for turbulent conditions |
| Wing CL much lower than 2D | Finite wing effect | Normal — CL_wing ≈ CL_2D × AR/(AR+2) approx |
| LLT won't run | Low AR or high sweep | Switch to VLM or 3D Panel method |
| Negative CD at some α | Panel/convergence issue | Re-panel airfoil (PANE command), check coordinates |
| Import fails in XFLR5 | Wrong .dat format | Ensure single space-separated columns, no tabs |
