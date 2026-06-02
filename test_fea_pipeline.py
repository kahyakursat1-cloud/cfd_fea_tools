"""End-to-end FEA pipeline smoke test.

Küre yükle -> tet mesh -> sabit alt + üst nokta yükü -> ccx çalıştır -> sonuç oku.
"""

import shutil
from pathlib import Path

import trimesh

from analysis import (
    generate_tet_mesh, FEAMaterial, FixedBC, ForceLoad, FEACase,
    write_inp, surface_face_nodes, faces_in_axis_band,
)
from analysis.ccx_runner import run_ccx


def main():
    out_dir = Path("test_fea_run").resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()

    print("[1] Test küresi oluşturuluyor (r=50mm)...")
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=0.05)
    print(f"    {len(sphere.faces)} üçgen, watertight={sphere.is_watertight}")

    print("[2] Tet mesh üretiliyor...")
    tm = generate_tet_mesh(sphere, target_size=0.012, output_dir=out_dir,
                           progress_callback=lambda p, m: print(f"    [{p}%] {m}"))
    print(f"    {tm.summary()}, type={tm.element_type}")

    print("[3] Sınır koşulları oluşturuluyor...")
    # Alt yarı (z<0) sabit
    bottom_face_idx = faces_in_axis_band(
        trimesh.Trimesh(vertices=tm.points, faces=tm.surface_tris[:, :3], process=False),
        axis=2, band="lower", fraction=0.30,
    )
    bottom_nodes = surface_face_nodes(tm, bottom_face_idx)
    print(f"    Sabit düğüm sayısı: {len(bottom_nodes)}")

    # Üst tepe (z>0) — küçük bir kuvvet uygulayacağız
    top_face_idx = faces_in_axis_band(
        trimesh.Trimesh(vertices=tm.points, faces=tm.surface_tris[:, :3], process=False),
        axis=2, band="upper", fraction=0.10,
    )
    top_nodes = surface_face_nodes(tm, top_face_idx)
    print(f"    Yüklü düğüm sayısı: {len(top_nodes)}")

    if len(bottom_nodes) == 0 or len(top_nodes) == 0:
        raise RuntimeError("BC veya yük node seti boş")

    print("[4] FEA case yazılıyor...")
    aluminum = FEAMaterial.from_gpa("ALUMINUM_6061", e_gpa=69.0, nu=0.33,
                                     rho=2700.0, yield_mpa=276.0)
    case = FEACase(
        name="sphere_test",
        mesh=tm,
        material=aluminum,
        fixed_bcs=[FixedBC(node_ids=bottom_nodes)],
        force_loads=[ForceLoad(
            node_ids=top_nodes,
            direction=(0.0, 0.0, -1.0),
            total_force_n=1000.0,  # 1 kN aşağı
        )],
        analysis_type="STATIC",
    )

    inp_path = write_inp(case, out_dir)
    print(f"    {inp_path}  ({inp_path.stat().st_size} bytes)")

    print("[5] CalculiX (WSL ccx) çalıştırılıyor...")
    res = run_ccx(inp_path, timeout=600,
                  progress_callback=lambda p, m: print(f"    [{p}%] {m}"))
    print(f"    return code: {res.return_code}")
    for line in res.stdout.splitlines()[-25:]:
        print("    >", line)
    if not res.success:
        print("    [HATA] ccx başarısız")
        if res.stderr:
            print("    STDERR:", res.stderr[:1500])
        return 1

    print(f"[6] Sonuç dosyası: {res.frd_path}  ({res.frd_path.stat().st_size} bytes)")
    print("\n[OK] End-to-end FEA pipeline çalışıyor!")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
