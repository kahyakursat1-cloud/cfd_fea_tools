"""Mesh-GCI kampanyası — gerçek araç STL'inde 3-seviye Cd yakınsaması (ASME V&V 20).
run_vehicle_analysis'i 3 mesh kalitesinde (hizli/standart/hassas) koşar, Cd + hücre
sayısını toplar, report_generator.compute_gci ile discretization belirsizliğini hesaplar.
AĞIR: tam CFD ×3 → saatler (gece-boyu). İlerleme dosyaya yazılır (canlı izlenebilir).
Kullanım: python experiments/mesh_gci_campaign.py <stl> [--tip ucak] [--hiz 30] [--alpha 0]
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from report_generator import compute_gci, gci_verdict  # noqa: E402
from vehicle_pipeline import run_vehicle_analysis  # noqa: E402

LEVELS = ["hizli", "standart", "hassas"]   # kaba → ince (ref_bump -1/0/+1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stl")
    ap.add_argument("--tip", default="ucak")
    ap.add_argument("--hiz", type=float, default=30.0)
    ap.add_argument("--alpha", type=float, default=0.0)
    ap.add_argument("--out", default="mesh_gci_campaign.json")
    args = ap.parse_args()

    log = HERE.parent / "mesh_gci_campaign.log"
    def _log(m):
        line = f"[{time.strftime('%H:%M:%S')}] {m}"
        print(line, flush=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    runs = []
    t0 = time.time()
    for lvl in LEVELS:
        _log(f"=== Seviye '{lvl}' başlıyor (STL={Path(args.stl).name}, tip={args.tip}) ===")
        r = run_vehicle_analysis(
            args.stl, vehicle_type=args.tip, velocity=args.hiz, alpha_deg=args.alpha,
            quality=lvl, out_root="vehicle_runs",
            progress_cb=lambda p, m, _l=lvl: _log(f"  [{_l}] {p}% {m}"))
        cells = (r.mesh or {}).get("cells")
        if r.cd is None or not cells:
            # Seviye başarısız (ör. ince mesh laptop bütçesini aştı → WSL-timeout temiz
            # öldürdü). BAŞARILI seviyeleri KAYBETME: kısmi kayıt yaz + dürüstçe bitir.
            _log(f"!!! Seviye '{lvl}' başarısız (cd={r.cd}, cells={cells}) — "
                 f"{len(runs)}/{len(LEVELS)} seviye tamam, kısmi kayıt yazılıyor")
            partial = {
                "vaka": f"Mesh-GCI kampanyası (KISMİ) — {Path(args.stl).name}",
                "durum": f"{len(runs)}/{len(LEVELS)} seviye başarılı; '{lvl}' başarısız",
                "seviyeler": runs,
                "basarisiz_seviye": lvl,
                "not": ("İnce seviye laptop foamRun bütçesini aşmış olabilir (orphan-önleme "
                        "WSL-timeout ile temiz öldürür). 3-nokta GCI için tüm seviyeler "
                        "tractable olmalı (daha düşük max_cells ya da daha küçük/temiz geometri)."),
            }
            (HERE.parent / args.out).write_text(
                json.dumps(partial, indent=2, ensure_ascii=False), encoding="utf-8")
            return 1
        runs.append({"seviye": lvl, "cd": float(r.cd), "cells": int(cells)})
        _log(f"=== '{lvl}' bitti: Cd={r.cd:.5f}, hücre={cells:,} "
             f"(toplam {(time.time()-t0)/60:.0f} dk) ===")

    # h-temsilcisi: 3B → h ∝ N^(-1/3) (kaba büyük h, ince küçük h)
    h = [run["cells"] ** (-1 / 3) for run in runs]    # [kaba, orta, ince]
    f = [run["cd"] for run in runs]
    gci = compute_gci(h[0], h[1], h[2], f[0], f[1], f[2])
    rec = {
        "vaka": f"Mesh-GCI kampanyası — {Path(args.stl).name} (tip={args.tip}, "
                f"V={args.hiz}, α={args.alpha})",
        "seviyeler": runs,
        "gci": gci,
        "verdict": gci_verdict(gci) if gci else "GCI hesaplanamadı (özdeş Cd?)",
        "sure_dk": round((time.time() - t0) / 60, 1),
        "_not": "ASME V&V 20 discretization belirsizliği. h∝N^(-1/3). compute_gci çekirdeği.",
    }
    (HERE.parent / args.out).write_text(json.dumps(rec, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    _log(f"BİTTİ: {rec['verdict']}  →  {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
