"""
SIMP topoloji optimizasyonu — CFD-yüklü, CalculiX tabanlı (Faz 3.1).
====================================================================
Akış: stüdyo CFD koşusunun basınç alanı → tet mesh → SIMP/OC döngüsü:
ρ_e^p·E0 malzeme kutulaması (ccx K ayrık malzeme) → ccx statik →
*EL PRINT ENER eleman enerjisinden duyarlılık → duyarlılık filtresi →
OC güncellemesi. Dış yüzey kabuğu PASİF-KATI tutulur (aerodinamik form
korunur; iç yapı optimize edilir).

Çıktılar (run_dir/topopt/): rho.vtk (ρ-alanı), tasarim.stl (ρ≥0.5 eşik),
yakinsama.png, sonuc_topopt.json.

DÜRÜSTLÜK: tek yük durumu (seçilen CFD koşusu), lineer statik, komplians
minimizasyonu. Burkulma/yorulma/flutter kısıtları YOK — ön-tasarım aracı.

CLI: python vehicle_topopt.py vehicle_runs/<model> --hacim 0.4 --iter 30
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
from scipy.spatial import cKDTree

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import trimesh

from analysis.ccx_runner import run_ccx
from analysis.tet_mesher import generate_tet_mesh
from fea_runner import MATERIAL_LIBRARY
from vehicle_fea import CONSTRAINT_PRESETS, _map_pressure_to_tet

RHO_MIN = 0.05


# ───────────────────────── yardımcılar ─────────────────────────

def _tet_volumes(P, tets):
    a = P[tets[:, 1]] - P[tets[:, 0]]
    b = P[tets[:, 2]] - P[tets[:, 0]]
    c = P[tets[:, 3]] - P[tets[:, 0]]
    return np.abs(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6.0


def _write_inp(path: Path, P, tets, bins_of, bin_rho, e0_mpa, nu, density,
               fixed_nodes, cload_block: str, penal: float):
    """TO'ya özel inp: K adet malzeme kutusu + sabit CLOAD bloğu."""
    L = ["*HEADING", "SIMP topoloji optimizasyonu iterasyonu", "*NODE"]
    for i, (x, y, z) in enumerate(P, start=1):
        L.append(f"{i}, {x:.9e}, {y:.9e}, {z:.9e}")
    nb = len(bin_rho)
    for b in range(nb):
        ids = np.where(bins_of == b)[0]
        if len(ids) == 0:
            continue
        L.append(f"*ELEMENT, TYPE=C3D4, ELSET=BIN{b:02d}")
        for ei in ids:
            n = tets[ei] + 1
            L.append(f"{ei+1}, {n[0]}, {n[1]}, {n[2]}, {n[3]}")
    L.append("*ELSET, ELSET=EALL, GENERATE")
    L.append(f"1, {len(tets)}, 1")
    L.append("*NSET, NSET=SABIT")
    for k in range(0, len(fixed_nodes), 8):
        L.append(", ".join(str(int(n)) for n in fixed_nodes[k:k+8]))
    for b in range(nb):
        if not np.any(bins_of == b):
            continue
        e_mpa = max((bin_rho[b] ** penal) * e0_mpa, 1e-6)
        L.append(f"*MATERIAL, NAME=M{b:02d}")
        L.append("*ELASTIC")
        L.append(f"{e_mpa * 1e6:.6e}, {nu}")
        L.append("*DENSITY")
        L.append(f"{density}")
        L.append(f"*SOLID SECTION, ELSET=BIN{b:02d}, MATERIAL=M{b:02d}")
    L.append("*STEP")
    L.append("*STATIC")
    L.append("*BOUNDARY")
    L.append("SABIT, 1, 3, 0.0")
    L.append(cload_block)
    L.append("*EL PRINT, ELSET=EALL")   # CalculiX'te ELSET zorunlu
    L.append("ENER")
    L.append("*NODE FILE")
    L.append("U")
    L.append("*END STEP")
    path.write_text("\n".join(L), encoding="utf-8")
    return path


def _parse_ener(dat_path: Path, n_elem: int) -> np.ndarray | None:
    """ccx .dat ENER çıktısından eleman enerji yoğunluğu (C3D4: 1 int.nokta)."""
    if not dat_path.exists():
        return None
    sed = np.zeros(n_elem)
    in_block = False
    for line in dat_path.read_text(errors="ignore").splitlines():
        low = line.lower()
        if "energy" in low and "density" in low:
            in_block = True
            continue
        if in_block:
            parts = line.split()
            if len(parts) == 3:
                try:
                    ei = int(parts[0]) - 1
                    if 0 <= ei < n_elem:
                        sed[ei] = float(parts[2])
                    continue
                except ValueError:
                    pass
            if line.strip() and not line.strip()[0].isdigit():
                in_block = False
    return sed if sed.any() else None


def _sens_filter(cc, rho, sens, rmin):
    """Klasik duyarlılık filtresi (Sigmund 99-line): ŝ = Σw·ρ·s / (ρ·Σw)."""
    tree = cKDTree(cc)
    pairs = tree.query_ball_tree(tree, rmin)
    out = np.empty_like(sens)
    for i, nb in enumerate(pairs):
        nb = np.asarray(nb)
        w = rmin - np.linalg.norm(cc[nb] - cc[i], axis=1)
        out[i] = (w * rho[nb] * sens[nb]).sum() / (rho[i] * w.sum() + 1e-30)
    return out


def _oc_update(rho, sens, vol, volfrac, passive, move=0.2, eta=0.5):
    """Optimality Criteria + hacim kısıtı (λ bisection)."""
    lo, hi = 1e-12, 1e12
    rho_new = rho.copy()
    for _ in range(80):
        lam = 0.5 * (lo + hi)
        be = np.sqrt(np.maximum(sens / (lam * vol), 1e-30)) ** (2 * eta)
        cand = np.clip(rho * be, np.maximum(rho - move, RHO_MIN),
                       np.minimum(rho + move, 1.0))
        cand[passive] = 1.0
        if (cand * vol).sum() > volfrac * vol.sum():
            lo = lam
        else:
            hi = lam
        rho_new = cand
    return rho_new


def _write_rho_vtk(path: Path, P, tets, rho):
    L = ["# vtk DataFile Version 3.0", "SIMP yogunluk alani", "ASCII",
         "DATASET UNSTRUCTURED_GRID", f"POINTS {len(P)} float"]
    L += [f"{x:.6e} {y:.6e} {z:.6e}" for x, y, z in P]
    L.append(f"CELLS {len(tets)} {len(tets)*5}")
    L += [f"4 {t[0]} {t[1]} {t[2]} {t[3]}" for t in tets]
    L.append(f"CELL_TYPES {len(tets)}")
    L += ["10"] * len(tets)
    L += [f"CELL_DATA {len(tets)}", "SCALARS rho float 1", "LOOKUP_TABLE default"]
    L += [f"{r:.4f}" for r in rho]
    path.write_text("\n".join(L), encoding="utf-8")


def _threshold_stl(path: Path, P, tets, rho, thr=0.5):
    keep = tets[rho >= thr]
    if len(keep) == 0:
        return False
    ftab = {}
    for t in keep:
        for f in ((t[0], t[1], t[2]), (t[0], t[1], t[3]),
                  (t[0], t[2], t[3]), (t[1], t[2], t[3])):
            key = tuple(sorted(f))
            ftab[key] = ftab.get(key, 0) + 1
    bnd = np.array([k for k, c in ftab.items() if c == 1])
    if len(bnd) == 0:
        return False
    trimesh.Trimesh(vertices=P, faces=bnd, process=True).export(str(path))
    return True


# ───────────────────────── ana döngü ─────────────────────────

def _collect_polar_cases(run_dir: Path) -> list[Path]:
    """run_dir içindeki tüm çözülmüş case dizinleri (ana + polar _a* kopyaları)."""
    out = []
    for d in sorted(run_dir.iterdir()):
        if d.is_dir() and (d / "system").exists() and d.name not in ("fea", "topopt"):
            out.append(d)
    return out


def _case_vtk(case_dir: Path) -> Path | None:
    yb = case_dir / "postProcessing" / "yuzeyBasinc"
    hits = sorted(yb.rglob("*.vtk")) if yb.exists() else []
    if hits:
        return hits[-1]
    from vehicle_pipeline import export_surface_vtk
    tris = list((case_dir / "constant" / "triSurface").glob("*.stl"))
    return export_surface_vtk(case_dir, tris[0].stem.replace(" ", "_")) if tris else None


def run_topopt(run_dir, material="aluminum_6061", constraint="y_min",
               volfrac=0.4, penal=3.0, max_iter=30, n_bins=20,
               mesh_div=15, rho_cfd=1.225, multi_load=False, weights=None,
               progress_cb=None) -> dict:
    run_dir = Path(run_dir)
    out_dir = run_dir / "topopt"
    out_dir.mkdir(parents=True, exist_ok=True)

    def cb(p, m):
        if progress_cb:
            progress_cb(p, m)

    # Yük durumu: vehicle_fea ile aynı kaynaklar
    from vehicle_fea import resolve_cp_vtk
    sonuc = json.loads((run_dir / "sonuc.json").read_text(encoding="utf-8"))
    cp_vtk = resolve_cp_vtk(run_dir, sonuc)
    if not cp_vtk:
        return {"status": "FAILED", "error": "Yüzey basınç VTK'sı yok — önce CFD koşusu"}
    stls = sorted(run_dir.glob("*_oriented.stl")) or sorted(run_dir.glob("*_prep.stl"))
    if not stls:
        return {"status": "FAILED", "error": "Hazırlanmış STL yok"}

    cb(2, "Tet mesh (TO çözünürlüğü)...")
    m = trimesh.load(str(stls[0]), force="mesh")
    lmax = float((m.bounds[1] - m.bounds[0]).max())
    tet = generate_tet_mesh(m, target_size=lmax / mesh_div, output_dir=out_dir,
                            second_order=False)
    P, tets = tet.points, tet.tets[:, :4].astype(int)
    n_elem = len(tets)
    vol = _tet_volumes(P, tets)
    cc = P[tets].mean(axis=1)
    rmin = 2.0 * float(np.cbrt(vol.mean()))

    # Yük durumları: tek vaka veya (multi_load) run_dir'deki tüm çözülmüş
    # case'ler (ana + polar _a* kopyaları) — gerçek uçuş zarfı yaklaşımı
    if multi_load:
        case_dirs = _collect_polar_cases(run_dir)
        vtks = [(d.name, _case_vtk(d)) for d in case_dirs]
        vtks = [(n, v) for n, v in vtks if v is not None]
    else:
        vtks = [("ana", Path(cp_vtk))]
    if not vtks:
        return {"status": "FAILED", "error": "Hiç yük durumu bulunamadı"}
    wts = np.asarray(weights if weights else [1.0] * len(vtks), float)
    wts = wts / wts.sum()

    cb(8, f"Yük eşleme: {len(vtks)} yük durumu × {n_elem:,} eleman...")
    cload_blocks = []
    for name, v in vtks:
        mp = _map_pressure_to_tet(v, tet, rho=rho_cfd)
        if mp["status"] != "SUCCESS":
            return {"status": "FAILED", "error": f"yük {name}: {mp.get('error')}"}
        cl = ["*CLOAD"]
        for nid, (fx, fy, fz) in sorted(mp["node_forces"].items()):
            for dof, val in ((1, fx), (2, fy), (3, fz)):
                if abs(val) > 1e-9:
                    cl.append(f"{nid}, {dof}, {val:.6e}")
        cload_blocks.append((name, "\n".join(cl)))
    cload_block = cload_blocks[0][1]   # reanaliz/tekil kullanım için ilk vaka

    _, axis, side = CONSTRAINT_PRESETS[constraint]
    coord = P[:, axis]
    plane = coord.min() if side == "min" else coord.max()
    ext = float(coord.max() - coord.min()) or 1.0
    tol = 0.02 * ext
    fixed = np.where(np.abs(coord - plane) < tol)[0] + 1
    while len(fixed) < 6 and tol < 0.2 * ext:
        tol *= 2
        fixed = np.where(np.abs(coord - plane) < tol)[0] + 1

    # Pasif kabuk: yüzeyde YÜZÜ olan elemanlar katı kalır (form korunur).
    # Düğüm-temas kriteri kabuğu 2-3 kat kalınlaştırıp hacim kısıtını
    # fizibil olmaktan çıkarabiliyordu.
    surf_faces = {tuple(sorted(f)) for f in tet.surface_tris[:, :3].astype(int)}
    def _faces(t):
        return ((t[0], t[1], t[2]), (t[0], t[1], t[3]),
                (t[0], t[2], t[3]), (t[1], t[2], t[3]))
    passive = np.array([any(tuple(sorted(f)) in surf_faces for f in _faces(t))
                        for t in tets])

    pas_frac = float(vol[passive].sum() / vol.sum())
    volfrac_eff = volfrac
    uyari = None
    if volfrac <= pas_frac + 0.02:
        volfrac_eff = min(pas_frac + 0.10, 0.9)
        uyari = (f"Hedef hacim ({volfrac}) pasif kabuk tabanının ({pas_frac:.2f}) "
                 f"altında — fizibil değil; hedef {volfrac_eff:.2f}'ye yükseltildi. "
                 "Daha ince mesh (--mesh-div) iç tasarım alanını büyütür.")

    mat = MATERIAL_LIBRARY[material]
    e0_mpa, nu, dens = mat.youngs_modulus, mat.poisson_ratio, mat.density

    rho = np.full(n_elem, volfrac_eff)
    rho[passive] = 1.0
    hist = []
    cb(12, f"SIMP döngüsü: {n_elem:,} eleman, hedef hacim %{volfrac_eff*100:.0f}, "
           f"pasif kabuk %{pas_frac*100:.0f} (hacim)")
    for it in range(1, max_iter + 1):
        bins_of = np.clip(((rho - RHO_MIN) / (1 - RHO_MIN) * (n_bins - 1)).round(),
                          0, n_bins - 1).astype(int)
        bin_rho = RHO_MIN + (np.arange(n_bins) + 0.0) / (n_bins - 1) * (1 - RHO_MIN)
        rho_eff = bin_rho[bins_of]
        # Ağırlıklı çoklu yük: her vaka ayrı çözülür, enerji/komplians toplanır
        comp = 0.0
        w_total = np.zeros(n_elem)
        for li, (lname, lblock) in enumerate(cload_blocks):
            inp = _write_inp(out_dir / f"to_iter_{li}.inp", P, tets, bins_of, bin_rho,
                             e0_mpa, nu, dens, fixed, lblock, penal)
            ccx = run_ccx(inp, timeout=3600)
            if not ccx.success:
                return {"status": "FAILED",
                        "error": f"ccx iter {it} yük {lname}: {ccx.stderr[-300:]}",
                        "iterasyon": it}
            sed = _parse_ener(ccx.dat_path, n_elem)
            if sed is None:
                return {"status": "FAILED",
                        "error": f"iter {it} yük {lname}: ENER parse edilemedi"}
            w_l = sed * vol
            w_total += wts[li] * w_l
            comp += wts[li] * 2.0 * float(w_l.sum())
        sens = penal * w_total / np.maximum(rho_eff, RHO_MIN)  # -dc/drho ölçüsü
        sens = _sens_filter(cc, rho, sens, rmin)
        rho_new = _oc_update(rho, sens, vol, volfrac, passive)
        change = float(np.abs(rho_new - rho).max())
        rho = rho_new
        hist.append({"iter": it, "komplians": comp,
                     "hacim": float((rho * vol).sum() / vol.sum()),
                     "degisim": round(change, 4)})
        cb(12 + int(80 * it / max_iter),
           f"iter {it}/{max_iter}: C={comp:.4e}, ΔρMAX={change:.3f}")
        if change < 0.02 and it > 3:
            break

    # B2: final tasarımın yeniden-analizi — son yoğunluklarla bir çözüm daha,
    # gerilme çıktısı istenerek; vM yalnız KATI (rho>=0.5) elemanların
    # düğümlerinde değerlendirilir (düşük-yoğunluk eleman gerilmesi anlamsız)
    cb(92, "Final tasarım yeniden-analizi (gerilme)...")
    reanaliz = None
    try:
        bins_of = np.clip(((rho - RHO_MIN) / (1 - RHO_MIN) * (n_bins - 1)).round(),
                          0, n_bins - 1).astype(int)
        bin_rho = RHO_MIN + np.arange(n_bins) / (n_bins - 1) * (1 - RHO_MIN)
        inp = _write_inp(out_dir / "to_final.inp", P, tets, bins_of, bin_rho,
                         e0_mpa, nu, dens, fixed, cload_block, penal)
        txt = inp.read_text(encoding="utf-8").replace(
            "*NODE FILE\nU", "*NODE FILE\nU\n*EL FILE\nS")
        inp.write_text(txt, encoding="utf-8")
        ccx_f = run_ccx(inp, timeout=3600)
        if ccx_f.success:
            from analysis.frd_parser import parse_frd
            frd = parse_frd(ccx_f.frd_path)
            disp = frd.displacement_magnitude()
            vm = frd.von_mises()
            solid_nodes = np.unique(tets[rho >= 0.5])
            nid_to_idx = {int(n): i for i, n in enumerate(frd.node_ids)}
            idx = [nid_to_idx[int(n) + 1] for n in solid_nodes
                   if int(n) + 1 in nid_to_idx]
            # TO geometrisi jagged/sivri köşeli → tepe von Mises büyük olasılıkla
            # TEKİLLİK. Tekillik-dayanıklı değerlendirme (vehicle_fea ile aynı).
            from vehicle_fea import _stress_assessment
            vm_subset = vm[idx] if (vm is not None and idx) else None
            sa = _stress_assessment(vm_subset, mat.yield_strength) or {}
            reanaliz = {
                "max_sehim_mm": round(float(disp.max()) * 1000, 4) if disp is not None else None,
                "max_vm_kati_MPa": sa.get("max_von_mises_MPa"),    # geri-uyum alias
                **sa,
            }
    except Exception as e:
        reanaliz = {"hata": str(e)[:200]}

    cb(95, "Çıktılar yazılıyor...")
    _write_rho_vtk(out_dir / "rho.vtk", P, tets, rho)
    stl_ok = _threshold_stl(out_dir / "tasarim.stl", P, tets, rho)

    fig, ax1 = plt.subplots(figsize=(5, 3))
    ax1.plot([h["iter"] for h in hist], [h["komplians"] for h in hist],
             "o-", color="#1f4e79")
    ax1.set_xlabel("İterasyon"); ax1.set_ylabel("Komplians", color="#1f4e79")
    ax2 = ax1.twinx()
    ax2.plot([h["iter"] for h in hist], [h["hacim"] for h in hist],
             "s--", color="#2e7d32")
    ax2.set_ylabel("Hacim oranı", color="#2e7d32")
    ax2.set_ylim(0, 1)   # hacim sabit hedefte; autoscale 1e-8 gürültüyü büyütüyor
    fig.tight_layout()
    fig.savefig(out_dir / "yakinsama.png", dpi=200)
    plt.close(fig)

    out = {"status": "ok", "iterasyon": len(hist), "eleman": n_elem,
           "hacim_hedef": volfrac_eff, "hacim_hedef_istenen": volfrac,
           "pasif_taban": round(pas_frac, 3), "uyari": uyari,
           "hacim_son": hist[-1]["hacim"],
           "komplians_ilk": hist[0]["komplians"], "komplians_son": hist[-1]["komplians"],
           "pasif_kabuk_orani": round(float(passive.mean()), 3),
           "yuk_durumlari": [n for n, _ in cload_blocks],
           "agirliklar": [round(float(w), 3) for w in wts],
           "tasarim_stl": str(out_dir / "tasarim.stl") if stl_ok else None,
           "rho_vtk": str(out_dir / "rho.vtk"), "yeniden_analiz": reanaliz,
           "gecmis": hist,
           "_not": ("Tek yük durumu, lineer statik, komplians min. Burkulma/"
                    "yorulma kısıtı yok — ön-tasarım. Dış kabuk pasif-katı.")}
    (out_dir / "sonuc_topopt.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    cb(100, "Topoloji optimizasyonu tamamlandı")
    return out


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="CFD-yüklü SIMP topoloji optimizasyonu")
    ap.add_argument("run_dir")
    ap.add_argument("--malzeme", default="aluminum_6061", choices=list(MATERIAL_LIBRARY))
    ap.add_argument("--mesnet", default="y_min", choices=list(CONSTRAINT_PRESETS))
    ap.add_argument("--hacim", type=float, default=0.4)
    ap.add_argument("--iter", type=int, default=30, dest="iters")
    ap.add_argument("--mesh-div", type=int, default=15)
    ap.add_argument("--coklu", action="store_true",
                    help="run_dir'deki TÜM çözülmüş case'leri (ana + polar) yük durumu yap")
    ap.add_argument("--agirlik", type=float, nargs="+", default=None,
                    help="yük durumu ağırlıkları (vaka sayısıyla aynı uzunlukta)")
    args = ap.parse_args()

    def _cb(p, m):
        print(f"[{p:3d}%] {m}", flush=True)

    r = run_topopt(args.run_dir, args.malzeme, args.mesnet, args.hacim,
                   max_iter=args.iters, mesh_div=args.mesh_div,
                   multi_load=args.coklu, weights=args.agirlik, progress_cb=_cb)
    if r["status"] == "ok":
        print(f"\nC: {r['komplians_ilk']:.4e} -> {r['komplians_son']:.4e}  "
              f"hacim: {r['hacim_son']:.3f}  STL: {r['tasarim_stl']}")
    else:
        print("BASARISIZ:", r.get("error", ""))
