"""
Süpersonik CFD — shockFluid (yoğunluk-bazlı, Kurganov şok-yakalama).
====================================================================
Roketler için M>0.8 rejimi: foamRun -solver shockFluid (OF11). Basınç-bazlı
fluid çözücüsünün soğuk-başlangıç kararsızlığı YOK — şoklar karakteristik
yönde taşınır. Zaman-yürüyüşlü (CFL≤0.3 adaptif), inviscid-duvar (slip),
serbest-akış süpersonik sınırlar. Sürükleme = basınç + dalga sürüklemesi
(süpersonik küt/sivri cisimde baskın; skin-friction ihmal — ön-tasarım).

Mesh: openfoam_runner snappy yardımcıları yeniden kullanılır.
CLI: python supersonic_cfd.py model.stl --mach 2.0 --tip roket
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import trimesh

from analysis.openfoam_runner import (
    OF_BASHRC,
    WSL_DISTRO,
    CFDCase,
    _compute_domain,
    _foam_header,
    _write_block_mesh,
    _write_decompose_par,
    _write_snappy,
    _write_surface_features,
    windows_to_wsl_path,
)
from vehicle_pipeline import _hull_projected_area

GAMMA = 1.4
R_AIR = 287.058
MU_AIR = 1.8e-5
PR = 0.72


def sound_speed(t_k: float) -> float:
    return math.sqrt(GAMMA * R_AIR * t_k)


def _of(wsl_dir, cmd, timeout):
    full = (f"export ParaView_TYPE=none && source {OF_BASHRC} && "
            f"unset FOAM_SIGFPE && cd '{wsl_dir}' && {cmd}")
    return subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "bash", "-c", full],
                          capture_output=True, text=True, timeout=timeout)


def _write_shock_thermo(case_dir: Path):
    cp = GAMMA * R_AIR / (GAMMA - 1)   # 1004.7
    (case_dir / "constant" / "physicalProperties").write_text(
        _foam_header("dictionary", "physicalProperties", "constant") +
        "thermoType\n{\n    type hePsiThermo; mixture pureMixture;\n"
        "    transport const; thermo hConst; equationOfState perfectGas;\n"
        "    specie specie; energy sensibleInternalEnergy;\n}\n"
        "mixture\n{\n"
        "    specie         { molWeight 28.96; }\n"
        f"    thermodynamics {{ Cp {cp:.2f}; Hf 0; }}\n"
        f"    transport      {{ mu {MU_AIR:.3e}; Pr {PR}; }}\n}}\n")
    (case_dir / "constant" / "momentumTransport").write_text(
        _foam_header("dictionary", "momentumTransport", "constant") +
        "simulationType laminar;\n")


def _write_shock_fields(case_dir: Path, surf: str, mach: float,
                        t_inf: float, p_inf: float):
    a = sound_speed(t_inf)
    u = mach * a
    fs = ["inlet", "top", "bottom", "front", "back"]   # serbest-akış sınırları
    def bf(lines):
        return "boundaryField\n{\n" + "".join(lines) + "}\n"
    # U: serbest akış sabit, outlet zeroGradient (süpersonik çıkış), duvar slip
    ulines = [f"    {p} {{ type fixedValue; value uniform ({u:.4f} 0 0); }}\n" for p in fs]
    ulines.append("    outlet { type zeroGradient; }\n")
    ulines.append(f"    {surf} {{ type slip; }}\n")   # inviscid duvar
    # M>=2.5: durgun iç alan (U=0) -> bow-shock girişten kademeli yürür;
    # impulsive üniform başlangıç güçlü genleşmede negatif T üretiyordu.
    u_init = "(0 0 0)" if mach >= 2.5 else f"({u:.4f} 0 0)"
    (case_dir / "0" / "U").write_text(
        _foam_header("volVectorField", "U", "0") +
        "dimensions [0 1 -1 0 0 0 0];\n"
        f"internalField uniform {u_init};\n" + bf(ulines))
    # T
    tlines = [f"    {p} {{ type fixedValue; value uniform {t_inf}; }}\n" for p in fs]
    tlines.append("    outlet { type zeroGradient; }\n")
    tlines.append(f"    {surf} {{ type zeroGradient; }}\n")
    (case_dir / "0" / "T").write_text(
        _foam_header("volScalarField", "T", "0") +
        "dimensions [0 0 0 1 0 0 0];\n"
        f"internalField uniform {t_inf};\n" + bf(tlines))
    # p
    plines = [f"    {p} {{ type fixedValue; value uniform {p_inf}; }}\n" for p in fs]
    plines.append("    outlet { type zeroGradient; }\n")
    plines.append(f"    {surf} {{ type zeroGradient; }}\n")
    (case_dir / "0" / "p").write_text(
        _foam_header("volScalarField", "p", "0") +
        "dimensions [1 -1 -2 0 0 0 0];\n"
        f"internalField uniform {p_inf};\n" + bf(plines))
    return u


def _write_shock_system(case_dir: Path, surf: str, end_time: float,
                        write_int: float, lref: float, u: float,
                        rho_inf: float, sref: float, mach: float = 2.0):
    # Yüksek Mach'ta vanLeer başlangıç-darbesinde overshoot -> negatif T.
    # Minmod (en disipatif TVD limiter) + düşük maxCo ile sağlamlaştır.
    robust = mach >= 2.5
    lim, limV = ("Minmod", "MinmodV") if robust else ("vanLeer", "vanLeerV")
    maxco = 0.2 if robust else 0.3
    (case_dir / "system" / "fvSchemes").write_text(
        _foam_header("dictionary", "fvSchemes", "system") +
        "fluxScheme Kurganov;\n"
        "ddtSchemes { default Euler; }\n"
        "gradSchemes { default Gauss linear; }\n"
        "divSchemes { default none; }\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes\n{\n    default linear;\n"
        f"    reconstruct(rho) {lim};\n    reconstruct(U) {limV};\n"
        f"    reconstruct(T) {lim};\n}}\n"
        "snGradSchemes { default corrected; }\n")
    (case_dir / "system" / "fvSolution").write_text(
        _foam_header("dictionary", "fvSolution", "system") +
        "solvers\n{\n"
        '    "(rho|rhoU|rhoE).*" { solver diagonal; }\n'
        '    "U.*" { solver smoothSolver; smoother GaussSeidel; nSweeps 2;\n'
        "            tolerance 1e-09; relTol 0.01; }\n"
        '    "e.*" { solver smoothSolver; smoother GaussSeidel; nSweeps 2;\n'
        "            tolerance 1e-10; relTol 0; }\n"
        "}\nPIMPLE {}\n")
    fc = (
        "functions\n{\n    forceCoeffs1\n    {\n"
        '        type forceCoeffs; libs ("libforces.so");\n'
        "        writeControl timeStep; writeInterval 20;\n"
        f"        patches ({surf});\n"
        f"        rho rhoInf; rhoInf {rho_inf:.5f};\n"
        "        liftDir (0 0 1); dragDir (1 0 0);\n"
        "        CofR (0 0 0); pitchAxis (0 1 0);\n"
        f"        magUInf {u:.4f}; lRef {lref:.6f}; Aref {sref:.8f};\n"
        "    }\n}\n")
    (case_dir / "system" / "controlDict").write_text(
        _foam_header("dictionary", "controlDict", "system") +
        "application foamRun; solver shockFluid;\n"
        "startFrom startTime; startTime 0; stopAt endTime;\n"
        f"endTime {end_time:.6e}; deltaT {end_time/4000:.3e};\n"
        "writeControl adjustableRunTime;\n"
        f"writeInterval {write_int:.6e};\n"
        "purgeWrite 2; writeFormat ascii; writePrecision 7;\n"
        "runTimeModifiable true; adjustTimeStep yes; maxCo 0.3;\n"
        f"maxDeltaT {end_time/200:.3e};\n" + fc)


def run_supersonic(stl_path, mach=2.0, vehicle_type="roket", quality="standart",
                   t_inf=288.15, p_inf=101325.0, n_flow_pass=30,
                   out_root="vehicle_runs", progress_cb=None) -> dict:
    stl_path = Path(stl_path)
    stem = stl_path.stem

    def cb(p, m):
        if progress_cb:
            progress_cb(p, m)

    m = trimesh.load(str(stl_path), force="mesh")
    dims = (m.bounds[1] - m.bounds[0]).astype(float)
    L = float(dims.max())
    sref = _hull_projected_area(m.vertices, 0)   # gerçek izdüşüm frontal (akış +x)
    rho_inf = p_inf / (R_AIR * t_inf)
    a = sound_speed(t_inf)
    u = mach * a

    run_dir = Path(out_root) / f"{stem}_M{mach:g}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # ── Mesh: openfoam_runner yardımcılarıyla ──
    div = {"hizli": 5, "standart": 7, "hassas": 9}[quality]
    refmax = {"hizli": 2, "standart": 3, "hassas": 4}[quality]
    case = CFDCase(name=f"{stem}_M{mach:g}", stl_path=stl_path, velocity=u,
                   rho=rho_inf, domain_upstream=5.0, domain_downstream=12.0,
                   domain_lateral=6.0, refinement_min=max(1, refmax - 1),
                   refinement_max=refmax, bg_cell_size=L / div,
                   max_global_cells={"hizli": 600_000, "standart": 1_500_000,
                                     "hassas": 3_000_000}[quality],
                   n_processors=1)
    case_dir = (run_dir / case.name).resolve()
    if case_dir.exists():
        shutil.rmtree(case_dir)
    (case_dir / "0").mkdir(parents=True)
    (case_dir / "constant" / "triSurface").mkdir(parents=True)
    (case_dir / "system").mkdir(parents=True)
    surf = stem.replace(" ", "_")
    shutil.copy(stl_path, case_dir / "constant" / "triSurface" / stl_path.name)
    dmin, dmax, gmin, gmax = _compute_domain(stl_path, case)
    cx, cy, cz = [(gmin[i] + gmax[i]) / 2 for i in range(3)]
    inside_pt = (cx + L * 2.0, cy + L * 0.13, cz + L * 0.13)
    _write_block_mesh(case_dir, dmin, dmax, case.bg_cell_size)
    _write_snappy(case_dir, stl_path.name, surf, inside_pt, case)
    _write_surface_features(case_dir, stl_path.name)
    _write_decompose_par(case_dir, 1)

    end_time = n_flow_pass * (L / u)         # N akış-geçiş süresi
    _write_shock_thermo(case_dir)
    _write_shock_fields(case_dir, surf, mach, t_inf, p_inf)
    _write_shock_system(case_dir, surf, end_time, end_time / 10, L, u, rho_inf, sref, mach)

    wsl_dir = windows_to_wsl_path(case_dir)
    for pct, msg, cmd, tmo in [
            (10, "surfaceFeatures", "surfaceFeatures", 120),
            (20, "blockMesh", "blockMesh", 120),
            (45, "snappyHexMesh (şok-mesh)", "snappyHexMesh -overwrite", 2400),
            (55, "checkMesh", "checkMesh", 300)]:
        cb(pct, msg + "...")
        r = _of(wsl_dir, cmd + f" > log.{cmd.split()[0]} 2>&1", tmo)
        if cmd != "checkMesh" and r.returncode != 0:
            return {"status": "FAILED", "asama": cmd, "case": str(case_dir),
                    "error": (case_dir / f"log.{cmd.split()[0]}").read_text(errors="ignore")[-1500:]}

    cb(70, f"shockFluid (M={mach}, zaman-yürüyüşü)...")
    r = _of(wsl_dir, "foamRun > log.foamRun 2>&1", 7200)
    log = (case_dir / "log.foamRun").read_text(errors="ignore")
    base_artifact = ""
    if "FOAM FATAL" in log or r.returncode != 0:
        # Cd yakınsadıktan SONRA geç taban-çökmesi -> değeri kurtar, bayrakla
        cdc, driftc, ok = _cd_converged(case_dir)
        if not ok:
            return {"status": "FAILED", "asama": "shockFluid", "case": str(case_dir),
                    "error": log[-1500:]}
        base_artifact = ("geç taban-bölgesi (inviscid near-vacuum) çökmesi; "
                         f"Cd yakınsamadan sonra alındı (drift %{driftc:.2f})")

    cb(92, "Cd ayrıştırılıyor...")
    cd, cd_hist = _parse_cd(case_dir)
    if cd is None:
        return {"status": "FAILED", "error": "forceCoeffs okunamadı", "case": str(case_dir)}
    drift = (abs(cd_hist[-1] - cd_hist[-max(2, len(cd_hist)//5)])
             / (abs(cd_hist[-1]) + 1e-9) * 100) if len(cd_hist) >= 6 else None
    out = {"status": "ok", "model": stem, "mach": mach, "U_ms": round(u, 1),
           "rejim": "süpersonik" if mach > 1 else "transonik",
           "S_ref_m2": round(sref, 6), "Cd": round(cd, 4),
           "Cd_drift_pct": round(drift, 2) if drift else None,
           "drag_N": round(cd * 0.5 * rho_inf * u**2 * sref, 2),
           "case": str(case_dir),
           "_not": ("shockFluid Euler-benzeri (inviscid duvar): basınç + dalga "
                    "sürüklemesi; skin-friction yok (süpersonikte ikincil). Tek "
                    "mesh — bağımsızlık gösterilmedi.")}
    if base_artifact:
        out["uyari"] = base_artifact
    (run_dir / "supersonic.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    cb(100, f"Cd(M={mach}) = {cd:.3f}")
    return out


def run_mach_sweep(stl_path, machs=(0.8, 1.2, 2.0, 3.0), vehicle_type="roket",
                   quality="standart", t_inf=288.15, p_inf=101325.0,
                   n_flow_pass=30, out_root="vehicle_runs", progress_cb=None) -> dict:
    """Cd-Mach eğrisi: ilk Mach tam pipeline (mesh üretir), sonrakiler aynı
    mesh'i kopyalayıp yalnız 0/{p,T,U} + controlDict yeniden yazıp koşar."""
    stl_path = Path(stl_path)
    stem = stl_path.stem
    machs = sorted(machs)

    def cb(p, m):
        if progress_cb:
            progress_cb(p, m)

    m = trimesh.load(str(stl_path), force="mesh")
    dims = (m.bounds[1] - m.bounds[0]).astype(float)
    L = float(dims.max())
    sref = _hull_projected_area(m.vertices, 0)   # gerçek izdüşüm frontal (akış +x)
    rho_inf = p_inf / (R_AIR * t_inf)
    a = sound_speed(t_inf)

    cb(2, f"İlk nokta M={machs[0]} (mesh bu koşuda üretilir)")
    r0 = run_supersonic(stl_path, machs[0], vehicle_type, quality, t_inf, p_inf,
                        n_flow_pass, out_root, progress_cb=None)
    if r0["status"] != "ok":
        return {"status": "FAILED", "error": r0.get("error"), "mach": machs[0]}
    base_case = Path(r0["case"])
    surf = stem.replace(" ", "_")
    rows = [{"mach": machs[0], "Cd": r0["Cd"], "drift_pct": r0["Cd_drift_pct"]}]

    for i, mach in enumerate(machs[1:], start=1):
        cb(int(100 * i / len(machs)), f"M={mach} (mesh yeniden kullanılıyor)")
        case_a = base_case.parent / f"{base_case.name}_m{mach:g}"
        if case_a.exists():
            shutil.rmtree(case_a)
        # mesh + setup kopyala, zaman dizinlerini temizle
        shutil.copytree(base_case, case_a)
        for d in case_a.iterdir():
            if d.is_dir() and d.name not in ("0", "constant", "system") \
               and d.name.replace(".", "", 1).isdigit():
                shutil.rmtree(d)
        if (case_a / "postProcessing").exists():
            shutil.rmtree(case_a / "postProcessing")
        u = mach * a
        end_time = n_flow_pass * (L / u)
        _write_shock_fields(case_a, surf, mach, t_inf, p_inf)
        _write_shock_system(case_a, surf, end_time, end_time / 10, L, u, rho_inf, sref, mach)
        r = _of(windows_to_wsl_path(case_a), "foamRun > log.foamRun 2>&1", 7200)
        log = (case_a / "log.foamRun").read_text(errors="ignore")
        artifact = None
        if "FOAM FATAL" in log or r.returncode != 0:
            cdc, driftc, ok = _cd_converged(case_a)
            if not ok:
                rows.append({"mach": mach, "Cd": None, "durum": "failed"})
                continue
            artifact = f"geç taban-çökmesi; Cd yakınsamadan sonra (drift %{driftc:.2f})"
        cd, hist = _parse_cd(case_a)
        drift = (abs(hist[-1] - hist[-max(2, len(hist)//5)]) / (abs(hist[-1]) + 1e-9) * 100
                 if cd is not None and len(hist) >= 6 else None)
        row = {"mach": mach, "Cd": round(cd, 4) if cd else None,
               "drift_pct": round(drift, 2) if drift else None}
        if artifact:
            row["uyari"] = artifact
        rows.append(row)

    out = {"status": "ok", "model": stem, "S_ref_m2": round(sref, 6),
           "egri": rows, "case_dir": str(base_case.parent),
           "_not": "shockFluid inviscid duvar; mutlak Cd inviscid base-drag "
                   "nedeniyle yüksek olabilir, Cd-Mach TRENDİ güvenilir."}
    run_dir = base_case.parent
    (run_dir / "mach_sweep.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    _sweep_report(out, run_dir / "rapor_supersonik")
    out["report"] = str(run_dir / "rapor_supersonik" / "MACH_SWEEP.md")
    cb(100, "Cd-Mach taraması tamamlandı")
    return out


def _sweep_report(out, rep_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rep_dir = Path(rep_dir)
    (rep_dir / "figures").mkdir(parents=True, exist_ok=True)
    ok = [r for r in out["egri"] if r.get("Cd") is not None]
    if len(ok) >= 2:
        ms = [r["mach"] for r in ok]
        cds = [r["Cd"] for r in ok]
        fig, ax = plt.subplots(figsize=(5, 3.2))
        ax.plot(ms, cds, "o-", color="#1f4e79", mfc="white", ms=6, lw=1.4)
        ax.axvline(1.0, ls=":", color="gray", lw=0.8)
        ax.text(1.02, ax.get_ylim()[0], "M=1", fontsize=7, color="gray")
        ax.set_xlabel("Mach"); ax.set_ylabel("$C_D$ (frontal)")
        ax.set_title("Süpersonik Sürükleme Eğrisi (shockFluid)", fontsize=10)
        ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(rep_dir / "figures" / "cd_mach.png", dpi=200)
        plt.close(fig)
    md = [f"# Süpersonik Cd-Mach Taraması — {out['model']}",
          f"\n**Referans alan (frontal):** {out['S_ref_m2']} m²  ",
          "**Yöntem:** OpenFOAM 11 shockFluid (Kurganov yoğunluk-bazlı şok-yakalama)\n",
          "| Mach | $C_D$ | drift % | not |", "|------|-------|---------|-----|"]
    for r in out["egri"]:
        cd = r.get("Cd")
        note = "geç taban-çökmesi (yakınsama sonrası)" if r.get("uyari") else ""
        md.append(f"| {r['mach']} | {cd if cd is not None else '— (başarısız)'} | "
                  f"{r.get('drift_pct', '—')} | {note} |")
    md.append("\n![Cd-Mach](figures/cd_mach.png)\n")
    md.append(f"> ⚠️ *{out['_not']} Skin-friction yok (süpersonikte ikincil); "
              "transonik (M≈1) bölge en belirsiz. Tek mesh — GCI yapılmadı.*\n")
    (rep_dir / "MACH_SWEEP.md").write_text("\n".join(md), encoding="utf-8")


def _parse_cd(case_dir: Path):
    cands = list((case_dir / "postProcessing" / "forceCoeffs1").glob("*/coefficient.dat"))
    if not cands:
        cands = list((case_dir / "postProcessing" / "forceCoeffs1").glob("*/forceCoeffs.dat"))
    if not cands:
        return None, []
    cd_idx, hist = None, []
    for line in cands[0].read_text().splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            if "Cd" in s:
                parts = s.lstrip("#").split()
                for i, p in enumerate(parts):
                    if p == "Cd":
                        cd_idx = i
            continue
        parts = s.split()
        if cd_idx is not None and cd_idx < len(parts):
            try:
                hist.append(float(parts[cd_idx]))
            except ValueError:
                pass
    if not hist:
        return None, []
    return float(np.mean(hist[-max(1, len(hist)//5):])), hist   # son %20 ortalama


def _cd_converged(case_dir: Path, drift_tol: float = 8.0, min_hist: int = 40):
    """Geç taban-bölgesi (inviscid wake near-vacuum) çökmesi shockFluid'i M≳2.5'te
    yakınsamadan SONRA düşürebilir. Cd yeterli geçmişle oturmuşsa (drift toleransı
    geniş — inviscid taban yavaş oturur, drift tabloda gösterilir) değeri kurtar."""
    cd, hist = _parse_cd(case_dir)
    if cd is None or len(hist) < min_hist:
        return None, None, False
    w = max(2, len(hist) // 5)
    drift = abs(hist[-1] - hist[-w]) / (abs(hist[-1]) + 1e-9) * 100
    return cd, drift, drift <= drift_tol


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Süpersonik CFD (shockFluid)")
    ap.add_argument("model")
    ap.add_argument("--mach", type=float, default=2.0)
    ap.add_argument("--tarama", type=float, nargs="+", default=None,
                    help="Cd-Mach taraması için Mach listesi (örn. 0.8 1.2 2 3)")
    ap.add_argument("--tip", default="roket")
    ap.add_argument("--kalite", default="standart", choices=["hizli", "standart", "hassas"])
    ap.add_argument("--gecis", type=int, default=30, help="akış-geçiş süresi sayısı")
    args = ap.parse_args()

    def _cb(p, msg):
        print(f"[{p:3d}%] {msg}", flush=True)

    if args.tarama:
        r = run_mach_sweep(args.model, args.tarama, args.tip, args.kalite,
                           n_flow_pass=args.gecis, progress_cb=_cb)
        if r["status"] == "ok":
            for row in r["egri"]:
                print(f"  M={row['mach']}: Cd={row.get('Cd')}")
            print("Rapor:", r["report"])
        else:
            print(f"BASARISIZ: {r.get('error','')}")
    else:
        r = run_supersonic(args.model, args.mach, args.tip, args.kalite,
                           n_flow_pass=args.gecis, progress_cb=_cb)
        if r["status"] == "ok":
            print(f"\nM={r['mach']} ({r['U_ms']} m/s): Cd={r['Cd']} "
                  f"(drift {r['Cd_drift_pct']}%), drag={r['drag_N']} N")
        else:
            print(f"BASARISIZ [{r.get('asama','')}]: {r.get('error','')[-400:]}")
