"""Silent-failure assay — guard katmanını koşu-geçerliliğinin İKİLİ DETEKTÖRÜ olarak
nicelleştir (Paper 1 özgünlük yükseltme, Path A). Detection-theory: her (vaka, knob)
hücresi {silent-failure var/yok} × {guard flag attı/atmadı} → TP/FP/TN/FN →
sensitivity / specificity / prevalence, ve τ taranarak mini-ROC.

PILOT: korpus, aracın ZATEN ürettiği gerçek V&V çıktılarından tohumlandı (fea_validation_*.json,
tmr_gci_verdict*.json, gci_airfoil, supersonic_validation + oturum sonuçları) — sıfır yeni compute.
Tam sistematik tarama (knob-uzayı + bırak-bir-vaka CV) sonraki faz (solver matrisi).

Kullanım: python experiments/silent_failure_assay.py [--tau 0.05]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (vaka, knob, nicelik, naive_out, truth, guard_flagged, guard_class, kaynak)
# guard_flagged = guard "design-grade" SERTİFİKASI VERMEDİ mi (trend/out-of-envelope/GCI-withheld)?
# truth = bilinen referans (closed-form / Ladson / TMR-CFL3D / Charters–Thomas / OpenRocket).
def _c(case, knob, q, naive, truth, flagged, gclass, src):
    return {"case": case, "knob": knob, "q": q, "naive": naive, "truth": truth,
            "flagged": flagged, "gclass": gclass, "src": src}


CORPUS = [
    # ── FEA closed-form (truth = analitik) ──
    _c("cantilever", "C3D8I, 24x4x4", "deflection", 9.051, 9.143, False, "design", "fea_validation.json"),
    _c("cantilever", "C3D8I", "stress", 49.8, 48.0, False, "design", "fea_validation.json"),
    _c("thick-cylinder", "C3D10 consistent-load (FIX)", "hoop", 21.31, 21.03, False, "design", "fea_validation_cyl.json"),
    _c("thick-cylinder", "corner-lumping (DEFECT)", "hoop", 22.55, 21.03, True, "verification-caught", "paper §3 / Lamé"),
    _c("plate-hole", "C3D10 gmsh", "Kt-stress", 159.7, 157.0, False, "design", "fea_validation_hole.json"),
    _c("buckling", "*BUCKLE C3D10", "P_cr", 9227.4, 9211.6, False, "design", "fea_validation_buckling.json"),
    _c("plate-hole-GCI", "3-mesh non-monotonic", "peak-vM", 159.4, 157.0, True, "trend(GCI-withheld)", "fea_stress_gci.json"),
    # ── CFD airfoil (truth = Ladson / TMR-CFL3D) ──
    _c("naca0012-drag", "bespoke O-grid (non-asymptotic)", "Cd", 0.0131, 0.00890, True, "trend(p~0.2)", "gci_airfoil.json"),
    _c("naca0012-drag", "TMR grids a=0 (asymptotic)", "Cd", 0.00837, 0.00809, False, "design(GCI1.71%)", "tmr_gci_verdict.json"),
    _c("naca0012-lift", "a=10 residual-stopped", "Cl", 1.031, 1.078, True, "trend(not-force-conv)", "oturum/tmr a=10"),
    _c("naca0012-lift", "a=10 force-plateau", "Cl", 1.0644, 1.078, True, "trend(GCI-withheld)", "tmr_gci_verdict_a10.json"),
    _c("naca0012-lift", "a=12 stall (2D RANS)", "Cl", 0.82, 1.49, True, "out-of-envelope", "transition_results / Ladson"),
    # ── Süpersonik (truth = Charters–Thomas / OpenRocket) ──
    _c("sphere-M2", "shockFluid inviscid", "Cd", 1.135, 1.00, True, "trend(inviscid~15%)", "supersonic_validation.json"),
    _c("rocket-finned", "blunt-box fins (geometry)", "Cd", 1.007, 0.617, False, "design(no-guard)", "oturum rocket-fin/OpenRocket"),
]


def classify(cell, tau):
    """Bir hücreyi TP/FP/TN/FN'e ata. silent = |naive−truth|/|truth| > tau (yanlış-ama-uyarısız);
    caught = guard design-grade vermedi (flagged)."""
    err = abs(cell["naive"] - cell["truth"]) / abs(cell["truth"])
    silent = err > tau
    caught = cell["flagged"]
    if silent and caught:
        return "TP", err
    if silent and not caught:
        return "FN", err
    if not silent and caught:
        return "FP", err
    return "TN", err


def confusion(corpus, tau):
    c = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    for cell in corpus:
        lab, _ = classify(cell, tau)
        c[lab] += 1
    tp, fp, tn, fn = c["TP"], c["FP"], c["TN"], c["FN"]
    sens = tp / (tp + fn) if (tp + fn) else None
    spec = tn / (tn + fp) if (tn + fp) else None
    prev = (tp + fn) / len(corpus)
    return {**c, "sensitivity": sens, "specificity": spec, "prevalence": prev}


def main():
    tau = next((float(sys.argv[i + 1]) for i, a in enumerate(sys.argv) if a == "--tau"), 0.05)
    print(f"=== Silent-failure assay (PILOT, n={len(CORPUS)}, τ={tau:.0%}) ===")
    res = confusion(CORPUS, tau)
    print(f"  TP={res['TP']} FP={res['FP']} TN={res['TN']} FN={res['FN']}")
    print(f"  sensitivity (recall) = {res['sensitivity']:.2f}  "
          f"specificity = {res['specificity']:.2f}  prevalence = {res['prevalence']:.2f}")
    # per-hücre liste
    print("  --- hücreler ---")
    for cell in CORPUS:
        lab, err = classify(cell, tau)
        print(f"   [{lab}] {cell['case']:16s} {cell['knob']:32s} err={err:5.1%} "
              f"guard={cell['gclass']}")
    # mini-ROC: τ tara
    roc = [{"tau": t, **{k: confusion(CORPUS, t)[k] for k in ("sensitivity", "specificity")}}
           for t in (0.02, 0.03, 0.05, 0.10, 0.15)]
    out = ROOT / "silent_failure_assay_pilot.json"
    out.write_text(json.dumps({"tau": tau, "n": len(CORPUS), "confusion": res,
                               "roc_tau_sweep": roc, "corpus": CORPUS}, indent=2,
                              ensure_ascii=False), encoding="utf-8")
    print(f"\n  YAZILDI {out.name}")
    print("  NOT: PILOT — küratör korpus (gerçek V&V çıktıları); tam sistematik tarama sonraki faz.")
    print("  Dürüst bulgu: FN=rocket-fin (geometri-fidelity, otomatik guard YOK); "
          "FP=non-asimptotik-ama-referans-yakın (guard konservatif).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
