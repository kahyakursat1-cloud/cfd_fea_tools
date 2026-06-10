"""
Araç pipeline'ı 3D doğrulama çapası — keskin kenarlı küp.
=========================================================
Literatür: yüzeyi akışa dik küp Cd ≈ 1.05 (Hoerner 1965; Re>1e4'te Re-bağımsız).
Keskin kenar ayrılmayı sabitler → sınır-tabaka çözünürlüğüne duyarsız; prizma
katmansız snappy hattı için doğru doğrulama vakası (küre YANLIŞ vaka olurdu:
drag krizi geçiş-güdümlü, fully-turbulent RANS sistematik şaşırır).

Çalıştırma: python check_vehicle_validation.py [hizli|standart]
Çıktı: vehicle_validation.json + vehicle_runs/dogrulama_kup/ raporu
Kabul bandı: |Cd - 1.05| / 1.05 <= %15 (küt-cisim RANS belirsizliği)
"""
import json
import sys
from pathlib import Path

import trimesh

from vehicle_pipeline import run_vehicle_analysis

CD_REF = 1.05
TOL_PCT = 15.0


def main():
    quality = sys.argv[1] if len(sys.argv) > 1 else "standart"
    stl = Path("vehicle_runs") / "dogrulama_kup.stl"
    stl.parent.mkdir(exist_ok=True)
    trimesh.creation.box(extents=(0.5, 0.5, 0.5)).export(str(stl))

    def cb(p, m):
        print(f"[{p:3d}%] {m}", flush=True)

    r = run_vehicle_analysis(stl, vehicle_type="genel", velocity=10.0,
                             alpha_deg=0.0, quality=quality, progress_cb=cb)
    out = {"vaka": "kup 0.5 m, V=10 m/s (Re~3.4e5), yuzeyi akisa dik",
           "Cd_ref": CD_REF, "kaynak": "Hoerner 1965, Fluid-Dynamic Drag",
           "kalite": quality, "status": r.status}
    if r.status == "ok":
        err = abs(r.cd - CD_REF) / CD_REF * 100
        out.update({"Cd_sim": r.cd, "hata_pct": round(err, 1),
                    "gecti": err <= TOL_PCT,
                    "mesh_hucre": (r.mesh or {}).get("cells"),
                    "rapor": r.report})
        print(f"\nKUP DOGRULAMA: Cd={r.cd} (ref {CD_REF}) hata=%{err:.1f} "
              f"{'GECTI' if err <= TOL_PCT else 'KALDI'} (band %{TOL_PCT})")
    else:
        out["error"] = r.error[-500:]
        print("DOGRULAMA KOSUSU BASARISIZ")
    Path("vehicle_validation.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if out.get("gecti") else 1


if __name__ == "__main__":
    sys.exit(main())
