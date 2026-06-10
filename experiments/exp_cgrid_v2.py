"""Deney: farfield 50c + daha iyi radyal/LE cozunurluk ile C-grid validasyon."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from construct2d_bridge import (
    _min_case,
    read_p3d_2d,
    run_construct2d,
    run_validation,
    write_ogrid_gmsh,
)

alpha = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
work = Path("cgrid_v2/c2d")
if work.parent.exists():
    shutil.rmtree(work.parent)

print("Construct2D grid uretiliyor (radi=50, jmax=150, nsrf=280, ypls=1)...", flush=True)
p3d = run_construct2d(str(Path("cgrid_work/naca0012.dat")), work, "naca0012",
                      radi=50.0, jmax=150, nsrf=280, ypls=1.0, recd=3.4e6, topo="OGRD", slvr="ELLP")
if not p3d or not p3d.exists():
    print("GRID URETIMI BASARISIZ"); sys.exit(1)

case = Path("cgrid_v2")
_min_case(case)
X, Y, ni, nj = read_p3d_2d(p3d)
seam, ni_u = write_ogrid_gmsh(str(case / "mesh.msh"), X, Y, ni, nj)
print(f"grid {ni}x{nj} cells={ni_u*(nj-1)}", flush=True)

p = str(case.resolve()); wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
def of(cmd, t=600):
    return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && cd {wsl} && {cmd}"',
                          shell=True, capture_output=True, text=True, timeout=t)
of("gmshToFoam mesh.msh > log.g2f 2>&1")
of("checkMesh > log.check 2>&1")
chk = (case / "log.check").read_text(errors="replace")
for line in chk.splitlines():
    if "non-orthogonality Max" in line or "aspect ratio" in line or "skewness" in line:
        print("  " + line.strip(), flush=True)

print(f"CFD alpha={alpha} ...", flush=True)
r = run_validation(str(case), alpha_deg=alpha)
ref = {0: (0.0, 0.0082), 4: (0.452, 0.0092), 8: (0.862, 0.0132)}.get(int(alpha))
if r.get("status") == "SUCCESS" and ref:
    r["Cl_ref"], r["Cd_ref"] = ref
    r["Cl_err_pct"] = round(abs(r["Cl"] - ref[0]) / (abs(ref[0]) + 1e-3) * 100, 1)
    r["Cd_err_pct"] = round(abs(r["Cd"] - ref[1]) / ref[1] * 100, 1)

print(json.dumps(r, indent=2, default=str), flush=True)
