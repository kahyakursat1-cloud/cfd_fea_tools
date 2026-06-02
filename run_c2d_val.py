"""Mevcut Construct2D p3d'sinden OpenFOAM mesh + CFD validasyon."""
import sys, json, shutil
from pathlib import Path
from construct2d_bridge import read_p3d_2d, write_ogrid_gmsh, _min_case, run_validation
import subprocess

p3d = Path("cgrid_work/naca0012.p3d")
case = Path("c2dval")
if case.exists():
    shutil.rmtree(case)
_min_case(case)

X, Y, ni, nj = read_p3d_2d(p3d)
seam, ni_u = write_ogrid_gmsh(str(case/"mesh.msh"), X, Y, ni, nj)
print(f"grid {ni}x{nj} seam={seam} cells={ni_u*(nj-1)}", flush=True)

p = str(case.resolve()); wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
def of(cmd, t=300):
    return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && cd {wsl} && {cmd}"',
                          shell=True, capture_output=True, text=True, timeout=t)
g = of("gmshToFoam mesh.msh > log.g2f 2>&1")
of("checkMesh > log.check 2>&1")
chk = (case/"log.check").read_text(errors="replace")
for line in chk.splitlines():
    if "non-orthogonality Max" in line or "aspect ratio" in line or "Max skewness" in line:
        print("  " + line.strip(), flush=True)

alpha = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
print(f"CFD alpha={alpha} ...", flush=True)
r = run_validation(str(case), alpha_deg=alpha)
ref = {0: (0.0, 0.0082), 4: (0.452, 0.0092), 8: (0.862, 0.0132)}.get(int(alpha))
if r.get("status") == "SUCCESS" and ref:
    r["Cl_ref"], r["Cd_ref"] = ref
    r["Cd_err_pct"] = round(abs(r["Cd"]-ref[1])/ref[1]*100, 1)
print(json.dumps(r, indent=2), flush=True)
json.dump(r, open("c2dval_result.json", "w"), indent=2)
