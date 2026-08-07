"""End-to-end CFD pipeline smoke test.

Küre STL -> OpenFOAM case -> snappyHexMesh -> foamRun -> Cd/Cl çıkar.
"""
import shutil
import sys
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
    # Smoke test: pipeline'ı KANITLAMAK için kasıtlı küçük/hızlı mesh.
    # Varsayılan domain (15×L downstream) + base cell L/8, küre için 2.5M hücre
    # üretip serial-dışı solve'u dakikalarca sürdürüyordu. Burada makul domain +
    # kaba base cell + serial (n_processors=1, MPI-WSL'i atlar) ile ~100k hücre.
    case = CFDCase(
        name="sphere_cfd",
        stl_path=stl_path,
        velocity=10.0,
        flow_direction=(1.0, 0.0, 0.0),
        rho=1.225,
        nu=1.5e-5,
        end_time=200,
        write_interval=200,
        n_processors=1,          # serial — MPI-WSL paralel takılmasını atlar
        refinement_min=1,
        refinement_max=2,
        domain_upstream=3.0,     # varsayılan 5
        domain_downstream=6.0,   # varsayılan 15 (smoke için fazla)
        domain_lateral=3.0,      # varsayılan 5
        bg_cell_size=0.3,        # ~L/3 kaba base (varsayılan otomatik L/8)
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
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    import sys
    sys.exit(main())
