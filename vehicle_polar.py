"""
Araç polar taraması: tek mesh, çoklu hücum açısı → Cl/Cd/Cm eğrileri + rapor.
==============================================================================
Mesh bir kez üretilir (ilk α için tam pipeline); sonraki α'larda case kopyalanıp
yalnız 0/U ve forceCoeffs yönleri yeniden yazılır, çözücü yeniden koşar — α başına
snappyHexMesh maliyeti ödenmez.

Cm notu: moment forceCoeffs CofR'ı etrafındadır (varsayılan model orijini).
Statik stabilite yorumu için CofR ağırlık merkezine taşınmalıdır (--cofr).

CLI: python vehicle_polar.py model.stl --tip ucak --hiz 25 --alfalar -4 0 4 8 12
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

import matplotlib
import numpy as np

from validity_envelope import force_admissibility

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.ccx_runner import windows_to_wsl_path
from analysis.openfoam_runner import (
    _wrap_timeout,
    _write_control_dict,
    _write_field_U,
    _wsl_kill,
    _wsl_run,
    parse_force_coeffs,
)
from vehicle_pipeline import run_vehicle_analysis, trailing_mean

plt.rcParams.update({"figure.dpi": 300, "savefig.dpi": 300, "font.size": 9,
                     "axes.grid": True, "grid.alpha": 0.3})


def _wsl_solve(case_dir: Path, timeout=7200):
    wrapped, bins = _wrap_timeout("foamRun", timeout)
    try:
        return _wsl_run(windows_to_wsl_path(case_dir),
                        wrapped + " > log.foamRun 2>&1", timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        _wsl_kill(bins)
        return subprocess.CompletedProcess(args="foamRun", returncode=-1,
                                           stdout="", stderr="TIMEOUT")


def run_polar(stl_path, vehicle_type="ucak", velocity=25.0, alphas=(-4, 0, 4, 8),
              quality="standart", n_layers=0, nose_axis="+x", up_axis="+z",
              cofr=(0.0, 0.0, 0.0), out_root="vehicle_runs", n_processors=0,
              progress_cb=None) -> dict:
    alphas = sorted(alphas)
    stem = Path(stl_path).stem

    def cb(p, m):
        if progress_cb:
            progress_cb(p, m)

    cb(0, f"Polar: ilk nokta α={alphas[0]}° (mesh bu koşuda üretilir)")
    r0 = run_vehicle_analysis(stl_path, vehicle_type, velocity, alphas[0], quality,
                              out_root=out_root, n_processors=n_processors,
                              nose_axis=nose_axis, up_axis=up_axis,
                              n_layers=n_layers, progress_cb=None)
    if r0.status != "ok":
        return {"status": "failed", "error": r0.error, "alpha": alphas[0]}

    base_case = Path(r0.case_dir)
    scale = (r0.geometry["lmax_m"] ** 2) / r0.aref_m2   # forceCoeffs Aref=lref^2 -> gercek Aref
    rows = [{"alpha": alphas[0], "Cl": r0.cl, "Cd": r0.cd,
             "Cm": None, "yplus_ort": (r0.sinir_tabaka or {}).get("yplus", {}).get("ort")}]
    cd0, cl0, cm0, _hist0 = parse_force_coeffs(base_case)
    cm0 = trailing_mean([h[3] for h in _hist0], cm0)
    rows[0]["Cm"] = round(cm0 * scale, 5) if cm0 is not None and math.isfinite(cm0) else None

    class _C:  # _write_field_U/_write_control_dict'in ihtiyaç duyduğu alanlar
        pass

    # snappy patch adi = triSurface'taki STL stem'i (oriented ad — case adi DEGIL)
    tris = list((base_case / "constant" / "triSurface").glob("*.stl"))
    surface = tris[0].stem.replace(" ", "_") if tris else base_case.name
    lref = r0.geometry["lmax_m"]

    for i, a_deg in enumerate(alphas[1:], start=1):
        cb(int(100 * i / len(alphas)), f"Polar: α={a_deg}° (mesh yeniden kullanılıyor)")
        case_a = base_case.parent / f"{base_case.name}_a{str(a_deg).replace('-', 'm')}"
        if case_a.exists():
            shutil.rmtree(case_a)
        shutil.copytree(base_case, case_a)
        for d in case_a.iterdir():
            if d.is_dir() and d.name not in ("0", "constant", "system") \
               and d.name.replace(".", "", 1).replace("-", "").isdigit():
                shutil.rmtree(d)
        pp = case_a / "postProcessing"
        if pp.exists():
            shutil.rmtree(pp)

        a = math.radians(a_deg)
        c = _C()
        c.velocity = velocity
        c.flow_direction = (math.cos(a), 0.0, math.sin(a))
        c.rho = 1.225
        c.turbulence_intensity = 0.01
        c.compressible = False
        c.p_inf = 101325.0
        c.ground_clearance = None
        import re as _re
        m_end = _re.search(r"^endTime\s+(\d+)\s*;", (base_case / "system" / "controlDict").read_text(), _re.M)
        c.end_time = int(m_end.group(1)) if m_end else 400
        c.write_interval = c.end_time
        _write_field_U(case_a, c, surface)
        _write_control_dict(case_a, c, surface, lref)
        r = _wsl_solve(case_a)
        cd, cl, cm, _hist = parse_force_coeffs(case_a)
        cd = trailing_mean([h[1] for h in _hist], cd)
        cl = trailing_mean([h[2] for h in _hist], cl)
        cm = trailing_mean([h[3] for h in _hist], cm)
        ok = r.returncode == 0 and cd is not None and math.isfinite(cd) and abs(cd * scale) < 5
        cd_s = round(cd * scale, 5) if ok else None
        cl_s = round(cl * scale, 5) if ok and cl is not None else None
        # Fizik kapısı NOKTA BAZINDA: tek bir fizik-dışı α, lift eğimini ve L/D'yi
        # sessizce bozar — o nokta polardan dışlanır, gerekçesi satırda kalır.
        fz = force_admissibility(cd_s, cl_s, a_deg) if ok else {"verdict": "ok", "reasons": []}
        rows.append({"alpha": a_deg,
                     "Cl": cl_s,
                     "Cd": cd_s,
                     "Cm": round(cm * scale, 5) if ok and cm is not None and math.isfinite(cm) else None,
                     "durum": ("ok" if fz["verdict"] == "ok" else f"fizik: {fz['verdict']}")
                              if ok else "failed",
                     "fizik": fz})

    out = {"status": "ok", "stl": str(stl_path), "vehicle_type": vehicle_type,
           "velocity": velocity, "aref_m2": r0.aref_m2, "cofr_notu":
           "Cm model orijini etrafında — statik stabilite için CofR'ı CG'ye taşıyın",
           "polar": rows}
    run_dir = base_case.parent
    (run_dir / "polar.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    _polar_report(out, run_dir / "rapor_polar")
    out["report"] = str(run_dir / "rapor_polar" / "POLAR.md")
    return out


def _fizik_ok(r) -> bool:
    """Fizik-dışı nokta eğri uydurmaya ve figüre GİRMEZ (tabloda gerekçesiyle kalır)."""
    return (r.get("fizik") or {}).get("verdict", "ok") != "inadmissible"


def _polar_report(out, rep_dir: Path):
    rep_dir = Path(rep_dir)
    (rep_dir / "figures").mkdir(parents=True, exist_ok=True)
    rows = [r for r in out["polar"] if r.get("Cd") is not None and _fizik_ok(r)]
    if len(rows) >= 2:
        a = [r["alpha"] for r in rows]
        cl = [r["Cl"] for r in rows]
        cd = [r["Cd"] for r in rows]
        cm = [r.get("Cm") for r in rows]
        fig, axs = plt.subplots(1, 3, figsize=(10, 3))
        axs[0].plot(a, cl, "o-", color="#1f4e79")
        axs[0].set_xlabel("α (°)"); axs[0].set_ylabel("$C_L$")
        axs[1].plot(cd, cl, "o-", color="#2e7d32")
        axs[1].set_xlabel("$C_D$"); axs[1].set_ylabel("$C_L$")
        if all(v is not None for v in cm):
            axs[2].plot(a, cm, "o-", color="#7b1fa2")
        axs[2].set_xlabel("α (°)"); axs[2].set_ylabel("$C_M$ (orijin)")
        fig.suptitle(f"Polar — {Path(out['stl']).name}, V={out['velocity']} m/s", fontsize=10)
        fig.tight_layout()
        fig.savefig(rep_dir / "figures" / "polar.png")
        plt.close(fig)

    md = [f"# Polar Taraması — {Path(out['stl']).name}",
          f"\n**V = {out['velocity']} m/s**, A_ref = {out['aref_m2']} m² "
          f"({out['vehicle_type']})\n",
          "| α (°) | $C_L$ | $C_D$ | L/D | $C_M$ | Fizik |",
          "|-------|-------|-------|-----|-------|-------|"]
    for r in out["polar"]:
        if r.get("Cd"):
            ld = round(r["Cl"] / r["Cd"], 2) if r.get("Cl") else "—"
            fz = (r.get("fizik") or {}).get("verdict", "ok")
            fz_s = {"ok": "✅", "suspect": "⚠️ şüpheli", "inadmissible": "⛔ dışlandı"}[fz]
            md.append(f"| {r['alpha']} | {r.get('Cl', '—')} | {r['Cd']} | {ld} | "
                      f"{r.get('Cm', '—')} | {fz_s} |")
        else:
            md.append(f"| {r['alpha']} | — | — | — | — | — (başarısız) |")
    disi = [r for r in out["polar"] if r.get("Cd") is not None and not _fizik_ok(r)]
    if disi:
        md.append("\n**Fizik kapısı:** aşağıdaki noktalar fiziksel olarak kabul edilemez ve "
                  "eğri uydurma/figür DIŞINDA bırakıldı:  ")
        md.extend(f"- α={r['alpha']}°: {'; '.join((r.get('fizik') or {}).get('reasons', []))}  "
                  for r in disi)
        md.append("")
    ok_rows = [r for r in out["polar"] if r.get("Cl") is not None and _fizik_ok(r)]
    if len(ok_rows) >= 2:
        sl = (ok_rows[-1]["Cl"] - ok_rows[0]["Cl"]) / (ok_rows[-1]["alpha"] - ok_rows[0]["alpha"])
        md.append(f"\n**Lift eğimi** ≈ {sl:.4f}/° (ince kanat teorisi ~0.1096/°)  ")
        cms = [r for r in ok_rows if r.get("Cm") is not None]
        if len(cms) >= 2:
            sm = (cms[-1]["Cm"] - cms[0]["Cm"]) / (cms[-1]["alpha"] - cms[0]["alpha"])
            md.append(f"**dCm/dα** ≈ {sm:.4f}/° — {out['cofr_notu']}  ")
    md.append("\n![Polar](figures/polar.png)\n")
    md.append("> ⚠️ *Tüm noktalar aynı mesh'i kullanır (tutarlı kıyas); mutlak "
              "değerler tek-mesh belirsizliği taşır. Yüksek α'da (stall) RANS "
              "güvenilirliği düşer.*\n")
    (rep_dir / "POLAR.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Tek mesh, çoklu hücum açısı polar taraması")
    ap.add_argument("model")
    ap.add_argument("--tip", default="ucak")
    ap.add_argument("--hiz", type=float, default=25.0)
    ap.add_argument("--alfalar", type=float, nargs="+", default=[-4, 0, 4, 8])
    ap.add_argument("--kalite", default="standart")
    ap.add_argument("--katman", type=int, default=0)
    ap.add_argument("--burun", default="+x")
    ap.add_argument("--ust", default="+z")
    args = ap.parse_args()

    def _cb(p, m):
        print(f"[{p:3d}%] {m}", flush=True)

    out = run_polar(args.model, args.tip, args.hiz, args.alfalar, args.kalite,
                    args.katman, args.burun, args.ust, progress_cb=_cb)
    if out["status"] == "ok":
        for r in out["polar"]:
            print(r)
        print("Rapor:", out["report"])
    else:
        print("BASARISIZ:", out.get("error", "")[-400:])
