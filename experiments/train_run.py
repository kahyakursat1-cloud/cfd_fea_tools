"""Otopilot kapalı-döngü eğitimi: bir geometride otopilotun SEÇTİĞİ analizi
gerçekten koşar (OpenFOAM/WSL), sonucu (mesh kalitesi, yakınsama, Cd) değerlendirir
ve MEMORY'ye kaydeder (aykırılık-öğrenmesi + tip kütüphanesi büyür).

Kullanım: python experiments/train_run.py <kanonik_stl> <tip> [mach]
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auto_pilot as ap  # noqa: E402


def main():
    stl = sys.argv[1]
    tip_hint = sys.argv[2] if len(sys.argv) > 2 else None
    mach = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0

    cfg = ap.auto_configure(stl, out_dir="vehicle_runs/_train")
    tip = tip_hint or cfg["tip"]
    print(f"[otopilot] tip={cfg['tip']} kalite={cfg['kalite']} rejim={cfg['rejim']} "
          f"analiz={cfg.get('analiz')} lmax={cfg['lmax_m']:.2f}m")
    print(f"[plan] {cfg['plan']}")

    from supersonic_cfd import run_supersonic
    out = run_supersonic(cfg["stl"], mach=mach,
                         vehicle_type=cfg.get("vehicle_preset", "roket"),
                         quality=cfg["kalite"],
                         progress_cb=lambda p, m: print(f"  [{p:3d}%] {m}"))

    cd = out.get("Cd_toplam")
    print(f"\n[sonuç] Cd_toplam={cd}  Cd_basinc_dalga={out.get('Cd_basinc_dalga')} "
          f"Cd_surtunme={out.get('Cd_surtunme')}  Re={out.get('Re')}")
    mq = out.get("mesh_kalite") or out.get("mesh_quality") or {}
    print(f"[mesh] {mq}")
    print(f"[yakınsama] {out.get('yakinsama') or out.get('converged')}")

    flag = ap.cd_outlier(tip, cd)
    print(f"[aykırılık] {flag or 'yok (tutarlı)'}")

    gate = ap.record_case(cfg["metrik"], cfg["tip"], tip,
                          {**out, "rejim": cfg["rejim"]},
                          dosya=f"run:{os.path.basename(stl)}@M{mach}")
    if gate["suspect"]:
        print(f"[hakem-kapısı] C_D ŞÜPHELİ → çapa alınmadı; tip etiketi öğrenildi. "
              f"Neden: {'; '.join(gate['gerekce'])}")
    else:
        print("[hakem-kapısı] C_D güvenilir → temiz çapa olarak kaydedildi.")
    print(f"[kayıt] MEMORY'ye yazıldı → {ap.MEMORY.name}")
    json.dump(out, open("vehicle_runs/_train/last_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
