"""Gece-boyu C-grid drag GCI tamamlayıcısı (xfine seviyesi + asimptotik GCI).

Dün (gci_cgrid_finding.json) C-grid base/mid/fine (32k/54k/92k) koşuldu: Cd POZİTİF,
MONOTON, yakınsayan (O-grid patolojisinin tersi). Eksik olan asimptotik teyit için
xfine ~156k seviyesi. Bu sürücü:
  1) xfine'ı (n_air=442 n_wake=132 nj=221, NP=4) paralel koşar — exp_cgrid_run_parallel,
  2) mevcut gci_cgrid_{mid,fine}.json ile asimptotik-uç GCI(mid,fine,xfine) hesaplar,
  3) gci_cgrid_xfine_verdict.json'a DÜRÜST hüküm yazar (yakınsadı / hâlâ asimptotik değil).

NP=4 bilinçli: finding'in negatif-ölçeklemesi 8-rank aşırı-bölünmedendi (19.5k hücre/rank);
156k/4=39k/rank GAMG için sağlıklı. residualControl 1e-6 erken-durdurma → endTime üst-sınır.
Kullanım (arka plan): python experiments/overnight_cgrid_xfine.py
"""
import json
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from report_generator import compute_gci, gci_verdict  # noqa: E402

# xfine mesh + iterasyon (fine ile aynı iter; residualControl erken durdurur)
LBL, N_AIR, N_WAKE, NJ = "xfine", 442, 132, 221
S0, S1, S2 = 500, 5000, 10000
NP = 4


def run_xfine() -> dict:
    cmd = [sys.executable, str(HERE / "exp_cgrid_run_parallel.py"),
           LBL, str(N_AIR), str(N_WAKE), str(NJ), str(S0), str(S1), str(S2), str(NP)]
    print(f"[xfine] başlıyor: {' '.join(cmd)}", flush=True)
    # Toplam üst-sınır 40h (her sh() çağrısı kendi 12h timeout'una sahip).
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=144000)
    print(r.stdout[-2000:], flush=True)
    if r.returncode != 0:
        print("[xfine] STDERR:", (r.stderr or "")[-1000:], flush=True)
    out = ROOT / f"gci_cgridP_{LBL}.json"
    return json.loads(out.read_text()) if out.exists() else {"status": "no_output"}


def main() -> int:
    xf = run_xfine()
    if xf.get("status") != "ok" or "LM" not in xf:
        verdict = {"durum": "xfine_basarisiz", "xfine_ham": xf,
                   "sonuc": "xfine seviyesi yakınsamadı/çöktü — asimptotik GCI tamamlanamadı. "
                            "C-grid topoloji-fix'i hâlâ geçerli (base/mid/fine pozitif/monoton); "
                            "tam asimptotik GCI bu donanımda compute-bound (buluta ertelendi)."}
        (ROOT / "gci_cgrid_xfine_verdict.json").write_text(
            json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")
        print("YAZILDI gci_cgrid_xfine_verdict.json (xfine başarısız)", flush=True)
        return 1

    mid = json.loads((ROOT / "gci_cgrid_mid.json").read_text())
    fine = json.loads((ROOT / "gci_cgrid_fine.json").read_text())
    lv = [("mid", mid, 54080), ("fine", fine, 92480),
          ("xfine", xf, (N_AIR + 2 * N_WAKE) * NJ)]
    # h = 1/sqrt(N) (2D); compute_gci(coarse, med, fine) sırasıyla h büyükten küçüğe
    h = [1.0 / math.sqrt(c) for _, _, c in lv]
    cd = [d["LM"]["Cd"] for _, d, _ in lv]
    gci = compute_gci(h[0], h[1], h[2], cd[0], cd[1], cd[2])

    rec = {
        "vaka": "C-grid 2D NACA0012 drag GCI — asimptotik-uç (mid/fine/xfine)",
        "topology": "C-grid wake-kümelemeli, kOmegaSSTLM geçiş modeli, α=4°",
        "seviyeler": [{"ad": n, "cells": c, "Cd": d["LM"]["Cd"], "Cl": d["LM"]["Cl"]}
                      for n, d, c in lv],
        "gci": gci,
        "strict_gci_verdict": gci_verdict(gci) if gci else "GCI hesaplanamadı",
        "mid_fine_xfine_degisim_pct": [
            round(abs(cd[1] - cd[0]) / abs(cd[0]) * 100, 2),
            round(abs(cd[2] - cd[1]) / abs(cd[1]) * 100, 2)],
        "_not": ("NP=4 (39k hücre/rank, GAMG-sağlıklı). mid/fine seri, xfine paralel — "
                 "yakınsamış steady-state çözümü dekompozisyondan bağımsız. fine→xfine "
                 "değişimi küçükse asimptotik aralık GÖSTERİLDİ → mutlak Cd tasarım-grade "
                 "olabilir; büyükse hâlâ trend-grade (buluta)."),
    }
    (ROOT / "gci_cgrid_xfine_verdict.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print("YAZILDI gci_cgrid_xfine_verdict.json", flush=True)
    if gci:
        print(f"GCI: p={gci['p']} Cd_richardson={gci['f_exact']:.5f} "
              f"GCI_ince={gci['gci_fine_pct']}% | {rec['strict_gci_verdict']}", flush=True)
        print(f"fine→xfine değişim: %{rec['mid_fine_xfine_degisim_pct'][1]}", flush=True)
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
