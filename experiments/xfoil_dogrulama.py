"""XFOIL MODEL-FORM doğrulaması — deneysel referansa karşı.

NEDEN: `xfoil_kesit` panel-bağımsızlığı ölçüyordu (%0.55) ama o AYRIKLAŞTIRMA
bandıdır; "XFOIL gerçeği ne kadar tutturuyor" sorusunu YANITLAMAZ. Birleştirici
kesit Cd'sini mutlak sürüklemeye katıyor, dolayısıyla model-form hatası bilinmeli.

REFERANS EZBERDEN ALINTILANMAZ: depoda zaten var — `gci_airfoil.json` içindeki
Ladson NACA0012 verisi (Re=3.4e6, α=4°: Cl=0.44, Cd_serbest=0.0064,
Cd_turbulanslı=0.0092). Doğrulama O REYNOLDS'ta yapılır; kullanım Reynolds'u
(3.5e5) farklıdır ve bu fark AÇIKÇA yazılır.

YOL BOYUNCA BULUNAN KUSUR: α=4 süpürmede YAKINSAMIYORDU — yani referansın
tanımlı olduğu tam açı düşüyordu. XFOIL PACC süpürmesinde bir önceki çözümü
başlangıç tahmini olarak taşır; tek başına koşunca yakınsıyor. `xfoil_kesit`
artık yakınsamayan açıyı tek tek yeniden deniyor.

    python experiments/xfoil_dogrulama.py
Çıktı: xfoil_dogrulama.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

ALFA_REF = 4.0


def calistir() -> dict:
    import xfoil_kesit as xk
    ref = json.loads((KOK / "gci_airfoil.json").read_text(encoding="utf-8"))["reference"]
    re_ref = 3.4e6 if "3.4e6" in str(ref.get("kaynak", "")) else None
    if re_ref is None:
        raise ValueError("referans Reynolds'u kaynak metninden okunamadi")

    p = xk.polar("0012", re_ref, 0.0, (0.0, 2.0, ALFA_REF, 6.0, 8.0))
    nokta = next((n for n in p["polar"] if abs(n["alpha"] - ALFA_REF) < 1e-6), None)
    if nokta is None:
        return {"vaka": "XFOIL model-form dogrulamasi", "durum": "REFERANS ACISI YOK",
                "yakinsamayan": p["yakinsamayan_alfa"],
                "verdikt": "⚠️ alpha=4 yakinsamadi — dogrulama YAPILAMADI."}

    cl_h = (nokta["Cl"] - ref["Cl"]) / ref["Cl"] * 100
    cd_h_serbest = (nokta["Cd"] - ref["Cd_free"]) / ref["Cd_free"] * 100
    cd_h_turb = (nokta["Cd"] - ref["Cd_turb"]) / ref["Cd_turb"] * 100

    rec = {
        "vaka": (f"XFOIL model-form dogrulamasi — NACA0012, Re={re_ref:.2g}, "
                 f"alpha={ALFA_REF:g}, referans: {ref.get('kaynak')}"),
        "_neden": ("Panel-bagimsizligi (%0.55) AYRIKLASTIRMA bandidir; XFOIL'in "
                   "gercegi ne kadar tutturdugunu SOYLEMEZ. Birlestirici kesit "
                   "Cd'sini mutlak suruklemeye kattigi icin model-form hatasi "
                   "bilinmeli. Referans depoda zaten var (gci_airfoil.reference), "
                   "ezberden alintilanmadi."),
        "referans": ref, "re": re_ref, "alpha": ALFA_REF,
        "xfoil": {"Cl": nokta["Cl"], "Cd": nokta["Cd"]},
        "sapma_pct": {"Cl": round(cl_h, 2),
                      "Cd_vs_serbest_gecis": round(cd_h_serbest, 2),
                      "Cd_vs_tam_turbulans": round(cd_h_turb, 2)},
        "model_form_band_pct": round(max(abs(cl_h), abs(cd_h_serbest)), 2),
        "_kisit": (f"DOGRULAMA Re={re_ref:.2g}'DA YAPILDI. Birlestiricinin kullandigi "
                   "kesit verisi Re=3.5e5'tedir — bu band oraya ONCUL olarak tasinir, "
                   "OLCUM olarak DEGIL. Dusuk Re'de laminer kabarcik baskin ve XFOIL'in "
                   "hatasi FARKLI olabilir; ayni Re'de deneysel referans bulunursa "
                   "dogrulama orada tekrarlanmalidir. Ayrica N_krit=9 secimi gecis "
                   "yerini belirler ve referans tunelin turbulans seviyesiyle uyumlu "
                   "olmayabilir."),
        "_uretim": "Üretim: python experiments/xfoil_dogrulama.py",
    }
    rec["verdikt"] = (
        f"{'✅' if rec['model_form_band_pct'] < 10 else '⚠️'} XFOIL vs {ref.get('kaynak')}: "
        f"Cl {nokta['Cl']:.4f} vs {ref['Cl']} (%{cl_h:+.2f}), "
        f"Cd {nokta['Cd']:.5f} vs {ref['Cd_free']} serbest-gecis (%{cd_h_serbest:+.2f}) / "
        f"{ref['Cd_turb']} tam-turbulans (%{cd_h_turb:+.2f}). "
        f"Model-form bandi %{rec['model_form_band_pct']} — bu Re'de OLCULDU.")
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "xfoil_dogrulama.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    if "sapma_pct" in rec:
        print(json.dumps(rec["sapma_pct"], indent=2, ensure_ascii=False))
    print("\n" + rec["verdikt"])
    print("-> xfoil_dogrulama.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
