"""End-to-end CFD pipeline smoke test.

Küre STL -> OpenFOAM case -> snappyHexMesh -> foamRun -> Cd/Cl çıkar.
"""

import shutil
from pathlib import Path
import trimesh

from analysis import CFDCase, run_cfd


def main():
    out_dir = Path("test_cfd_run").resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()

    print("[1] Test küresi (r=0.5 m) yazılıyor...")
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=0.5)
    stl_path = out_dir / "sphere.stl"
    sphere.export(stl_path)
    print(f"    {stl_path}  ({len(sphere.faces)} üçgen)")

    print("[2] CFD case kuruluyor...")
    case = CFDCase(
        name="sphere_cfd",
        stl_path=stl_path,
        velocity=10.0,
        flow_direction=(1.0, 0.0, 0.0),
        rho=1.225,
        nu=1.5e-5,
        end_time=200,
        write_interval=200,
        n_processors=4,
        refinement_min=1,
        refinement_max=2,
    )

    print("[3] CFD koşusu başlatılıyor (snappyHexMesh + foamRun)...")
    res = run_cfd(case, out_dir, timeout=2400,
                  progress_callback=lambda p, m: print(f"    [{p}%] {m}"))

    print(f"[4] success={res.success}, return_code={res.return_code}")
    if not res.success:
        print("    [HATA]")
        print("    STDOUT son 30 satır:")
        for line in res.stdout.splitlines()[-30:]:
            print("    >", line)
        print("    STDERR:", res.stderr[-1500:])
        return 1

    print(f"    Cd = {res.cd}")
    print(f"    Cl = {res.cl}")
    print(f"    Cm = {res.cm}")
    if res.forces_history:
        print(f"    {len(res.forces_history)} iter kayıt edilmiş")
    print("\n[OK] CFD pipeline çalışıyor!")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
