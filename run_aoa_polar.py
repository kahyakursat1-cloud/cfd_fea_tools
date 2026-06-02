"""
3D AoA Polar — kanitlanmis prism mesh ile aracin stall polar'i.
AoA velocity ile uygulanir => mesh SABIT, sadece hiz degisir (verimli).
Onceden meshlenmis prism_validation/cases/minihawk_prism yeniden kullanilir.
"""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

V = 15.0
RHO = 1.225
S = 0.45            # kanat alani
C = 0.353          # kok kord (MAC ~ buna yakin)

BASE = Path("prism_validation/cases/minihawk_prism")
OUT = Path("aoa_polar")
OUT.mkdir(exist_ok=True)


def wsl_path(p: Path):
    p = str(p.resolve())
    return f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"


def wsl_of(d, cmd):
    return f'wsl bash -c "source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && cd {d} && {cmd}"'


def _read_internal(path):
    """0/ alanindan internalField skaler degerini oku."""
    m = re.search(r"internalField\s+uniform\s+([\d.eE+\-]+)", path.read_text())
    return m.group(1) if m else "0"


def _patch_boundary_type(case):
    """polyMesh/boundary: sides'i symmetry -> patch (freestream icin).
    Symmetry, ust/alt z-yuzeylerinde dusey hizi sifirlayip AoA'yi olduruyor.
    """
    bf = case/"constant"/"polyMesh"/"boundary"
    txt = bf.read_text()
    # 'sides { type symmetry;' -> 'sides { type patch;'  (sadece sides blogu)
    txt = re.sub(r"(sides\s*\{[^}]*?type\s+)symmetry(\s*;)", r"\1patch\2", txt, flags=re.DOTALL)
    bf.write_text(txt)


def write_fields(case, alpha):
    """Tilt'li freestream icin tum far-field BC'lerini freestream yap."""
    a = math.radians(alpha)
    Ux, Uz = V*math.cos(a), V*math.sin(a)
    z = case/"0"
    k0 = _read_internal(z/"k"); w0 = _read_internal(z/"omega"); nut0 = _read_internal(z/"nut")

    _patch_boundary_type(case)

    far_U = "{ type freestreamVelocity; freestreamValue uniform (%.5f 0 %.5f); }" % (Ux, Uz)
    (z/"U").write_text(f"""FoamFile{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux:.5f} 0 {Uz:.5f});
boundaryField{{ inlet {far_U} outlet {far_U} sides {far_U} aircraft {{ type noSlip; }} }}""")

    (z/"p").write_text("""FoamFile{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField{ inlet { type freestreamPressure; freestreamValue uniform 0; }
  outlet { type freestreamPressure; freestreamValue uniform 0; }
  sides { type freestreamPressure; freestreamValue uniform 0; }
  aircraft { type zeroGradient; } }""")

    # k/omega: inletOutlet (freestream'den nazik, omega bounding yapmaz)
    far_k = "{ type inletOutlet; inletValue uniform %s; value uniform %s; }" % (k0, k0)
    (z/"k").write_text(f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0};
boundaryField{{ inlet {far_k} outlet {far_k} sides {far_k} aircraft {{ type kqRWallFunction; value uniform {k0}; }} }}""")

    far_w = "{ type inletOutlet; inletValue uniform %s; value uniform %s; }" % (w0, w0)
    (z/"omega").write_text(f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0};
boundaryField{{ inlet {far_w} outlet {far_w} sides {far_w} aircraft {{ type omegaWallFunction; value uniform {w0}; }} }}""")

    far_n = "{ type calculated; value uniform %s; }" % nut0
    (z/"nut").write_text(f"""FoamFile{{ version 2.0; format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0};
boundaryField{{ inlet {far_n} outlet {far_n} sides {far_n} aircraft {{ type nutkWallFunction; value uniform 0; }} }}""")


def parse_forces(case, alpha):
    ff = list((case/"postProcessing"/"forces").glob("*/forces.dat"))
    if not ff: return None
    lines = [l for l in ff[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
    if not lines: return None
    nums = re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', lines[-1])
    try:
        Fpx,Fpz = float(nums[1]),float(nums[3]); Fvx,Fvz = float(nums[4]),float(nums[6])
    except (IndexError,ValueError): return None
    Fx,Fz = Fpx+Fvx, Fpz+Fvz
    a = math.radians(alpha)
    drag =  Fx*math.cos(a)+Fz*math.sin(a)
    lift = -Fx*math.sin(a)+Fz*math.cos(a)
    q = 0.5*RHO*V**2
    return {"Cl": round(lift/(q*S),4), "Cd": round(drag/(q*S),5),
            "LD": round(lift/drag,2) if drag>0 else None}


def run_alpha(alpha):
    case = OUT/f"alpha_{alpha:02d}"
    if case.exists(): shutil.rmtree(case)
    # Meshlenmis case'i kopyala (polyMesh + system + constant)
    shutil.copytree(BASE, case, ignore=shutil.ignore_patterns(
        "postProcessing","[1-9]*","processor*","log.*","VTK"))
    # 0/ temizle, baslangic 0'i constant/polyMesh ile uyumlu birak
    # (BASE'de 0/ zaten var; sadece U'yu degistir)
    write_fields(case, alpha)
    # residualControl: sadece p+U (forces bunlara bagli; omega bounding'i beklemesin)
    fs = case/"system"/"fvSolution"
    txt = fs.read_text()
    txt = re.sub(r"residualControl\s*\{[^}]*\}",
                 "residualControl{ p 1e-5; U 1e-5; }", txt, flags=re.DOTALL)
    fs.write_text(txt)
    # endTime guvenlik tavani 400
    cdp = case/"system"/"controlDict"
    cdt = cdp.read_text()
    # endTime 200: forces ~150 iterde yakinsiyor; omega bounding residualControl'u
    # tetiklemedigi icin sabit tavan kullaniyoruz (forces dogru, runtime yari).
    cdp.write_text(re.sub(r"endTime\s+\d+;", "endTime 200;", cdt))
    d = wsl_path(case)
    if subprocess.run(wsl_of(d,"foamRun -solver incompressibleFluid > log.run 2>&1"),
                      shell=True, capture_output=True, timeout=3600, text=True).returncode != 0:
        tail = (case/"log.run").read_text(errors="replace")[-300:] if (case/"log.run").exists() else ""
        return {"alpha":alpha, "status":"FAILED", "log":tail}
    f = parse_forces(case, alpha)
    if not f: return {"alpha":alpha, "status":"NO_FORCES"}
    f["alpha"]=alpha; f["status"]="SUCCESS"
    return f


if __name__ == "__main__":
    import sys
    alphas = [int(x) for x in sys.argv[1:]] or [0,4,8,10,12,14,16]
    # Mevcut json'a append (onceden biten acilar korunur)
    results = []
    if Path("aoa_polar.json").exists():
        try:
            results = [r for r in json.load(open("aoa_polar.json"))
                       if r.get("alpha") not in alphas]
        except Exception:
            results = []
    for a in alphas:
        print(f"[Polar] alpha={a} ...", flush=True)
        r = run_alpha(a)
        results.append(r)
        print(f"  Cl={r.get('Cl')} Cd={r.get('Cd')} L/D={r.get('LD')} -> {r.get('status')}", flush=True)
        json.dump(results, open("aoa_polar.json","w"), indent=2)
    # stall tespiti
    ok = [r for r in results if r.get("Cl") is not None]
    if len(ok) >= 3:
        clmax = max(ok, key=lambda r: r["Cl"])
        print(f"\nCLmax = {clmax['Cl']} @ alpha={clmax['alpha']} deg (stall isareti)", flush=True)
    print("Kaydedildi: aoa_polar.json", flush=True)
