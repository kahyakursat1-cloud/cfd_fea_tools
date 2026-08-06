"""Test kapsamını MANTIKSAL KATMANLARA ayırır.

NEDEN: toplam "%42" tek başına yanıltıcıdır — karar/V&V mantığı ile dış-süreç
sarmalayıcıları ve GUI aynı kaba konur. Katman ayrımı, kapsamın NEREDE düşük
olduğunu gösterir; düşük kapsamı gizlemez, YERİNİ söyler.

    python -m pytest tests/ -q --cov=. --cov-report=json:cov.json
    python experiments/kapsam_katmanlari.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

KATMANLAR: dict[str, list[str] | None] = {
    "Karar & V&V motoru": [
        "validity_envelope.py", "report_generator.py", "polar_birlestirme.py",
        "lifting_line.py", "zarf.py", "gci_advisor.py", "kanit.py",
        "sessiz_yutma.py", "constants.py"],
    "Otomasyon & öğrenme": ["auto_pilot.py", "mentor.py", "kosu_gecmisi.py"],
    "Analiz çekirdeği": None,          # analysis/ altının tamamı
    "Araç hattı": [
        "vehicle_pipeline.py", "vehicle_fea.py", "vehicle_polar.py",
        "vehicle_report.py", "vehicle_topopt.py", "coupling_fsi.py"],
    "Dış-süreç köprüleri": [
        "openvsp_bridge.py", "xfoil_kesit.py", "openrocket_bridge.py",
        "construct2d_bridge.py", "dis_araclar.py", "mesh_generator.py"],
    "Arayüz (GUI)": [
        "app_analyzer.py", "app_parametric.py", "material_editor_gui.py",
        "launcher.py"],
}


def hesapla(cov_json: Path) -> dict:
    d = json.loads(cov_json.read_text(encoding="utf-8"))
    dosyalar = d["files"]
    out = {}
    for ad, uyeler in KATMANLAR.items():
        ifade = kapsanan = 0
        for yol, v in dosyalar.items():
            y = yol.replace("\\", "/")
            uy = (y.startswith("analysis/") if uyeler is None
                  else any(y == m or y.endswith("/" + m) for m in uyeler))
            if uy:
                ifade += v["summary"]["num_statements"]
                kapsanan += v["summary"]["covered_lines"]
        if ifade:
            out[ad] = {"ifade": ifade, "kapsanan": kapsanan,
                       "pct": round(kapsanan / ifade * 100, 1)}
    t = d["totals"]
    out["TOPLAM"] = {"ifade": t["num_statements"],
                     "kapsanan": t["covered_lines"],
                     "pct": round(t["percent_covered"], 1)}
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = KOK / "cov.json"
    if not p.exists():
        print("cov.json yok — önce:\n  python -m pytest tests/ -q "
              "--cov=. --cov-report=json:cov.json")
        return 1
    tablo = hesapla(p)
    for ad, v in tablo.items():
        print(f"{ad:30s} {v['kapsanan']:>6}/{v['ifade']:<6} = %{v['pct']:.0f}")
    (KOK / "kapsam_katmanlari.json").write_text(
        json.dumps({"katmanlar": tablo,
                    "_uretim": ("Üretim: python -m pytest tests/ -q --cov=. "
                                "--cov-report=json:cov.json && python "
                                "experiments/kapsam_katmanlari.py")},
                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("-> kapsam_katmanlari.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
