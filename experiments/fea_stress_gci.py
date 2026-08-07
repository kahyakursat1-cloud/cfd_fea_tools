"""FEA gerilme mesh-yakınsaması (GCI) — delikli-plaka tepe von Mises.
CFD-GCI'nin yapısal karşılığı (yol haritası 1.2): gerilme en mesh-duyarlı niceliktir;
SF ancak mesh-bağımsızsa savunulabilir. Delik kenarı DÜZGÜN eğri → tepe SONLU/YAKINSAK
(monoton, p≈2) olmalı — bu, gerçek konsantrasyonu sivri-köşe TEKİLLİĞİNDEN (ıraksar, GCI
patlar) ayırır. ASME V&V 20 / Roache GCI; report_generator.compute_gci yeniden kullanılır.
Kullanım: python experiments/fea_stress_gci.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fea_validation_hole as fh  # noqa: E402

from report_generator import compute_gci, gci_verdict  # noqa: E402

LEVELS = [4.0, 6.0, 9.0]   # vin_div: h = R/vin_div → kaba, orta, ince (sabit r=1.5)


def main():
    work = HERE.parent / "_fea_val_hole"
    work.mkdir(exist_ok=True)
    runs = []
    for vd in LEVELS:
        r = fh.run_case(work, vd)
        if r is None:
            print(f"CCX FAILED @ vin_div={vd}"); return 1
        runs.append(r)
        print(f"  h={r['h'] * 1e3:.3f} mm ({r['nodes']:,} düğüm): "
              f"σ_tepe={r['peak_MPa']:.2f} MPa, tepe/temsili={r['sa']['tepe_temsili_orani']}×",
              flush=True)

    h = [x["h"] for x in runs]                  # [kaba, orta, ince]
    f = [x["peak_MPa"] for x in runs]
    gci = compute_gci(h[0], h[1], h[2], f[0], f[1], f[2])
    if gci is None:
        print("GCI hesaplanamadı (özdeş değerler)"); return 1
    verdict = gci_verdict(gci)
    spread = (max(f) - min(f)) / (sum(f) / len(f)) * 100      # tepe-değer yayılımı %
    # Fiziksel sonuç: tekillik tepe-vM'yi ıraksatır; burada yayılım <%1 → YAKINSAK.
    # Strict-GCI "salınımlı" diyebilir çünkü değer gürültü-tabanında oynar (zaten yakınsamış).
    # GCI BANDI YOKSA "YAKINSADI" DENEMEZ. compute_gci artık p≤0 (ıraksayan
    # seri) durumunda band ÜRETMİYOR ve None dönüyor; eskiden NEGATİF bir sayı
    # dönüyordu ve bu eşik onu SESSİZCE geçiriyordu — ıraksayan bir dizi
    # "yakınsadı" sayılırdı.
    _g = gci.get("gci_fine_pct")
    converged = spread < 2.0 and _g is not None and _g < 1.0
    fiziksel = ("✅ Tepe gerilme YAKINSADI (gerçek konsantrasyon, tekillik DEĞİL): "
                f"6× düğümde yayılım %{spread:.2f}, GCI_ince %{_g:.2f}. "
                "Tekillik olsaydı tepe ıraksardı." if converged else
                "⚠ Tepe yakınsamadı — tekillik şüphesi (mesh inceldikçe ıraksıyor).")
    _fx = gci.get("f_exact")
    print(f"\nGCI: p={gci['p']}, "
          + (f"σ_richardson={_fx:.2f} MPa, " if _fx is not None
             else "σ_richardson=YOK (seri ıraksıyor), ")
          + f"GCI_ince={_g}%, tepe-yayılım=%{spread:.2f}")
    print(f"     monoton={gci['monotonic']}, asimptotik_oran={gci['asymptotic']}")
    print("STRICT-GCI:", verdict)
    print("FİZİKSEL:", fiziksel)
    print(f"Analitik (Heywood Kt): σ_tepe={fh.SIG_MAX_AN / 1e6:.1f} MPa "
          f"→ Richardson sapması %{abs(gci['f_exact'] - fh.SIG_MAX_AN / 1e6) / (fh.SIG_MAX_AN / 1e6) * 100:.1f}")

    rec = {
        "vaka": "Delikli-plaka tepe von Mises — FEA gerilme GCI (3 mesh)",
        "yontem": "C3D10, delik-çevresi h=R/{4,6,9} sabit r=1.5; tepe vM Richardson",
        "seviyeler": [{"h_mm": round(x["h"] * 1e3, 4), "dugum": x["nodes"],
                       "sigma_tepe_MPa": round(x["peak_MPa"], 3),
                       "tepe_temsili": x["sa"]["tepe_temsili_orani"]} for x in runs],
        "gci": gci, "strict_gci_verdict": verdict,
        "tepe_yayilim_pct": round(spread, 3),
        "fiziksel_sonuc": fiziksel,
        "analitik_Kt_MPa": round(fh.SIG_MAX_AN / 1e6, 2),
        "_not": ("Tepe vM 6× düğümde <%1 oynar → gerçek konsantrasyon YAKINSAK (tekillik "
                 "DEĞİL; o ıraksardı). Strict-GCI 'salınımlı' diyebilir çünkü değer gürültü-"
                 "tabanında. Üretim: python experiments/fea_stress_gci.py"),
    }
    out = HERE.parent / "fea_stress_gci.json"
    out.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Kayıt:", out.name)
    return 0 if converged else 2


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
