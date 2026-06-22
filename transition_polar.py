"""
Transition-Resolved Polar — kOmegaSSTLM (Langtry-Menter γ-Reθ)
=============================================================
y+~1 multi-grading O-grid + transition modeli ile NACA 0012 stall polar.
Laminar-turbulent gecisini cozer => CLmax ve stall acisi yakalanir.

Onceki kOmegaSST (y+~400) stall'i cozemiyordu; bu modul y+~1 BL ile
gecis modelini kullanir.
"""

import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np


def _to_wsl_path(win_path: Path) -> str:
    p = str(win_path.resolve())
    return f"/mnt/{p[0].lower()}{p[2:].replace(chr(92), '/')}"


def _wsl_of(wsl_dir: str, cmd: str) -> str:
    # FOAM_SIGFPE=false: yuksek non-ortho hucrelerde gecici NaN solver'i oldurmesin
    return (f'wsl bash -c "source /opt/openfoam11/etc/bashrc && '
            f'export FOAM_SIGFPE=false && cd {wsl_dir} && {cmd}"')


def _run(cmd, timeout=7200):
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout, text=True)
    return r.returncode


# NASA Langley NACA 0012 (Ladson 1988, Re=3e6) — stall ~16 deg, CLmax~1.5
NACA0012_REF = {
    0:  (0.000, 0.0082), 4: (0.452, 0.0092), 8: (0.862, 0.0132),
    10: (1.060, 0.0169), 12: (1.247, 0.0219), 14: (1.404, 0.0299),
    16: (1.520, 0.0438),
}


class TransitionPolar:
    V   = 50.0
    RHO = 1.225
    NU  = 1.48e-5
    C   = 1.0
    RE  = V * C / NU

    def __init__(self, base="./transition/naca0012"):
        self.base = Path(base)

    # ── Profil ──────────────────────────────────────────────────────────────
    def _profile(self, n=240):
        t = 0.12
        def yt(x):
            return (t/0.2)*(0.2969*np.sqrt(np.maximum(x,1e-10)) - 0.1260*x
                            - 0.3516*x**2 + 0.2843*x**3 - 0.1015*x**4)
        half = n // 2
        bt = np.linspace(0, np.pi, half, endpoint=False)
        xt = 0.5*(1-np.cos(bt)); zt = yt(xt)
        bb = np.linspace(np.pi, 2*np.pi, n-half, endpoint=False)
        xb = 0.5*(1-np.cos(bb)); zb = -yt(xb)
        return np.column_stack([np.concatenate([xt,xb]), np.concatenate([zt,zb])])

    # ── O-grid: multi-grading -> y+~1 ───────────────────────────────────────
    def _write_mesh(self, case_dir):
        n = 240            # cevresel
        n_normal = 160     # radyal
        W = 0.1
        R = 20.0
        cx, cz = 0.25, 0.0
        prof = self._profile(n)
        outer = np.zeros_like(prof)
        for i,(xi,zi) in enumerate(prof):
            dx,dz = xi-cx, zi-cz
            d = math.hypot(dx,dz) or 1e-10
            outer[i] = (cx+R*dx/d, cz+R*dz/d)

        L = ["FoamFile{ version 2.0; format ascii; class dictionary; object blockMeshDict; }\n",
             "convertToMeters 1;\nvertices\n(\n"]
        for xi,zi in prof:  L.append(f"    ({xi:.8f} 0      {zi:.8f})\n")
        for xi,zi in outer: L.append(f"    ({xi:.8f} 0      {zi:.8f})\n")
        for xi,zi in prof:  L.append(f"    ({xi:.8f} {W:.4f} {zi:.8f})\n")
        for xi,zi in outer: L.append(f"    ({xi:.8f} {W:.4f} {zi:.8f})\n")
        L.append(");\n\nblocks\n(\n")
        # multiGrading: ilk %0.02 radyal -> %65 hucre exp10, kalan -> %35 exp100
        # => ilk hucre ~9um => y+~1
        grad = "simpleGrading (1 ((0.0002 0.65 10)(0.9998 0.35 100)) 1)"
        for i in range(n):
            j = (i+1)%n
            v = [j,i,n+i,n+j, 2*n+j,2*n+i,3*n+i,3*n+j]
            L.append(f"    hex ({' '.join(map(str,v))}) (1 {n_normal} 1) {grad}\n")
        L.append(");\n\nboundary\n(\n")
        L.append("    airfoil { type wall; faces (\n")
        for i in range(n):
            j=(i+1)%n; L.append(f"        ({j} {i} {2*n+i} {2*n+j})\n")
        L.append("    ); }\n    farfield { type patch; faces (\n")
        for i in range(n):
            j=(i+1)%n; L.append(f"        ({n+j} {3*n+j} {3*n+i} {n+i})\n")
        L.append("    ); }\n    front { type empty; faces (\n")
        for i in range(n):
            j=(i+1)%n; L.append(f"        ({j} {n+j} {n+i} {i})\n")
        L.append("    ); }\n    back { type empty; faces (\n")
        for i in range(n):
            j=(i+1)%n; L.append(f"        ({2*n+j} {2*n+i} {3*n+i} {3*n+j})\n")
        L.append("    ); }\n);\n")
        (case_dir/"system"/"blockMeshDict").write_text("".join(L))

    # ── 0/ alanlari (transition: + gammaInt, ReThetat) ──────────────────────
    def _write_fields(self, case_dir, alpha_deg):
        a = math.radians(alpha_deg)
        Ux, Uz = self.V*math.cos(a), self.V*math.sin(a)
        I = 0.0018   # %0.18 serbest akim Tu (NASA dusuk-turbulans tunel)
        Lt = 0.07*self.C
        k0 = 1.5*(self.V*I)**2
        w0 = math.sqrt(k0)/(0.09**0.25*Lt)
        nut0 = k0/w0
        zero = case_dir/"0"; zero.mkdir(exist_ok=True)

        def w(name, body): (zero/name).write_text(body)

        w("U", f"""FoamFile{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} 0 {Uz});
boundaryField{{ airfoil{{type noSlip;}} farfield{{type freestreamVelocity; freestreamValue uniform ({Ux} 0 {Uz});}} front{{type empty;}} back{{type empty;}} }}""")
        w("p", """FoamFile{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField{ airfoil{type zeroGradient;} farfield{type freestreamPressure; freestreamValue uniform 0;} front{type empty;} back{type empty;} }""")
        w("k", f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e};
boundaryField{{ airfoil{{type kqRWallFunction; value uniform {k0:.6e};}} farfield{{type freestream; freestreamValue uniform {k0:.6e};}} front{{type empty;}} back{{type empty;}} }}""")
        w("omega", f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f};
boundaryField{{ airfoil{{type omegaWallFunction; value uniform {w0:.4f};}} farfield{{type freestream; freestreamValue uniform {w0:.4f};}} front{{type empty;}} back{{type empty;}} }}""")
        w("nut", f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e};
boundaryField{{ airfoil{{type nutLowReWallFunction; value uniform 0;}} farfield{{type calculated; value uniform {nut0:.6e};}} front{{type empty;}} back{{type empty;}} }}""")
        # Transition alanlari
        w("gammaInt", """FoamFile{ version 2.0; format ascii; class volScalarField; object gammaInt; }
dimensions [0 0 0 0 0 0 0]; internalField uniform 1;
boundaryField{ airfoil{type zeroGradient;} farfield{type inletOutlet; inletValue uniform 1; value uniform 1;} front{type empty;} back{type empty;} }""")
        w("ReThetat", """FoamFile{ version 2.0; format ascii; class volScalarField; object ReThetat; }
dimensions [0 0 0 0 0 0 0]; internalField uniform 100;
boundaryField{ airfoil{type zeroGradient;} farfield{type inletOutlet; inletValue uniform 100; value uniform 100;} front{type empty;} back{type empty;} }""")

    def _set_model(self, case_dir, model, end_time):
        """momentumTransport modelini ve controlDict endTime'i degistir (2 asamali run)."""
        W = 0.1
        (case_dir/"constant"/"momentumTransport").write_text(
            f"""FoamFile{{ version 2.0; format ascii; class dictionary; location "constant"; object momentumTransport; }}
simulationType RAS; RAS{{ model {model}; turbulence on; printCoeffs on; }}""")
        cd = (case_dir/"system"/"controlDict").read_text()
        cd = re.sub(r"endTime\s+\d+;", f"endTime {end_time};", cd)
        (case_dir/"system"/"controlDict").write_text(cd)

    def _write_system_constant(self, case_dir):
        W = 0.1
        (case_dir/"constant"/"momentumTransport").write_text(
            """FoamFile{ version 2.0; format ascii; class dictionary; location "constant"; object momentumTransport; }
simulationType RAS; RAS{ model kOmegaSSTLM; turbulence on; printCoeffs on; }""")
        (case_dir/"constant"/"physicalProperties").write_text(
            f"""FoamFile{{ version 2.0; format ascii; class dictionary; location "constant"; object physicalProperties; }}
viscosityModel constant; nu [0 2 -1 0 0 0 0] {self.NU};""")
        # transportProperties de yaz (uyumluluk)
        (case_dir/"constant"/"transportProperties").write_text(
            f"""FoamFile{{ version 2.0; format ascii; class dictionary; object transportProperties; }}
transportModel Newtonian; nu {self.NU};""")
        (case_dir/"system"/"controlDict").write_text(f"""FoamFile{{ version 2.0; format ascii; class dictionary; object controlDict; }}
application foamRun; startFrom startTime; startTime 0; endTime 3000;
deltaT 1; writeInterval 500; purgeWrite 2; writeFormat binary; runTimeModifiable true;
functions{{ forces{{ type forces; libs ("libforces.so"); writeControl timeStep; writeInterval 100;
patches ("airfoil"); rho rhoInf; rhoInf {self.RHO}; pRef 0; CofR (0.25 {W/2} 0); }} }}""")
        # Yuksek non-ortho O-grid (TE ~82 deg) icin agresif limitleme
        (case_dir/"system"/"fvSchemes").write_text("""FoamFile{ version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes{ default steadyState; }
gradSchemes{ default cellLimited Gauss linear 1; grad(U) cellLimited Gauss linear 1;
  grad(k) cellLimited Gauss linear 1; grad(omega) cellLimited Gauss linear 1; }
divSchemes{ default none; div(phi,U) bounded Gauss upwind;
  div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;
  div(phi,gammaInt) bounded Gauss upwind; div(phi,ReThetat) bounded Gauss upwind;
  div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes{ default Gauss linear limited corrected 0.33; }
interpolationSchemes{ default linear; } snGradSchemes{ default limited corrected 0.33; }
wallDist{ method meshWave; }""")
        (case_dir/"system"/"fvSolution").write_text("""FoamFile{ version 2.0; format ascii; class dictionary; object fvSolution; }
solvers{ p{ solver GAMG; tolerance 1e-7; relTol 0.05; smoother GaussSeidel;
  nCellsInCoarsestLevel 20; }
  "(U|k|omega|gammaInt|ReThetat)"{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.05; nSweeps 2; } }
SIMPLE{ nNonOrthogonalCorrectors 6; consistent yes;
  # residual≠kuvvet: 1e-5→1e-6 (kuvvet daha çok platoya oturur). Yüksek-α polar
  # noktalarında force-plateau ideal; bu eşik sıkılaştırma düşük-riskli ara çözüm.
  residualControl{ p 1e-6; U 1e-6; "(k|omega)" 1e-6; } }
relaxationFactors{ equations{ U 0.3; k 0.2; omega 0.2; gammaInt 0.2; ReThetat 0.2; } fields{ p 0.15; } }""")

    def _parse_forces(self, case_dir, alpha_deg):
        ff = list((case_dir/"postProcessing"/"forces").glob("*/forces.dat"))
        if not ff: return {}
        lines = [l for l in ff[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
        if not lines: return {}
        nums = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', lines[-1])
        try:
            Fpx,Fpz = float(nums[1]),float(nums[3])
            Fvx,Fvz = float(nums[4]),float(nums[6])
        except (IndexError,ValueError): return {}
        Fx,Fz = Fpx+Fvx, Fpz+Fvz
        a = math.radians(alpha_deg)
        drag =  Fx*math.cos(a)+Fz*math.sin(a)
        lift = -Fx*math.sin(a)+Fz*math.cos(a)
        q = 0.5*self.RHO*self.V**2; S = self.C*0.1
        return {"Cl": lift/(q*S), "Cd": drag/(q*S)}

    def run_alpha(self, alpha_deg):
        case = self.base/f"alpha_{alpha_deg:02d}"
        if case.exists(): shutil.rmtree(case)
        for sub in ("system","constant","0"): (case/sub).mkdir(parents=True, exist_ok=True)
        self._write_mesh(case); self._write_fields(case, alpha_deg)
        self._write_system_constant(case)
        wsl = _to_wsl_path(case)
        if _run(_wsl_of(wsl, "blockMesh > log.bm 2>&1"), 300) != 0:
            return {"status":"FAILED","step":"blockMesh"}

        # Asama 1: kOmegaSST ile akisi kur (uniform-init FPE'sini onler)
        self._set_model(case, "kOmegaSST", 600)
        if _run(_wsl_of(wsl, "foamRun -solver incompressibleFluid > log.s1 2>&1"), 3600) != 0:
            tail = (case/"log.s1").read_text(errors="replace")[-400:] if (case/"log.s1").exists() else ""
            return {"status":"FAILED","step":"solver_stage1","log":tail}

        # Asama 2: kOmegaSSTLM transition modeli, kurulu akistan devam
        cd = (case/"system"/"controlDict").read_text()
        (case/"system"/"controlDict").write_text(cd.replace("startFrom startTime", "startFrom latestTime"))
        self._set_model(case, "kOmegaSSTLM", 3000)
        if _run(_wsl_of(wsl, "foamRun -solver incompressibleFluid > log.s2 2>&1"), 7200) != 0:
            tail = (case/"log.s2").read_text(errors="replace")[-400:] if (case/"log.s2").exists() else ""
            return {"status":"FAILED","step":"solver_stage2","log":tail}
        sim = self._parse_forces(case, alpha_deg)
        if not sim: return {"status":"FAILED","step":"forces"}
        ref = NACA0012_REF.get(alpha_deg)
        out = {"alpha":alpha_deg, "Cl":round(sim["Cl"],4), "Cd":round(sim["Cd"],5),
               "status":"SUCCESS"}
        if ref:
            out["Cl_ref"], out["Cd_ref"] = ref
            out["Cl_err_pct"] = round(abs(sim["Cl"]-ref[0])/(abs(ref[0])+1e-3)*100,1)
            out["Cd_err_pct"] = round(abs(sim["Cd"]-ref[1])/ref[1]*100,1)
        return out


if __name__ == "__main__":
    import json
    import sys
    tp = TransitionPolar()
    alphas = [int(x) for x in sys.argv[1:]] or [0,4,8,10,12,14]
    results = []
    for a in alphas:
        print(f"[Transition] alpha={a} ...", flush=True)
        r = tp.run_alpha(a)
        results.append(r)
        print(f"  Cl={r.get('Cl')} (ref={r.get('Cl_ref')}) Cd={r.get('Cd')} "
              f"-> {r.get('status')} {r.get('step','')}", flush=True)
    json.dump(results, open("transition_polar.json","w"), indent=2)
    print("\nKaydedildi: transition_polar.json")
