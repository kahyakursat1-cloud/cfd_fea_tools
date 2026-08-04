"""NACA0012 2B kesit kampanyası — MiniHawk'ın UÇUŞ Reynolds'unda (Re≈3.5e5).

NEDEN: `polar_birlestirme` 3B kanat polarını VLM taşıması + 2B kesit sürüklemesi
+ indüklenen dirençten kuruyor, ama depodaki 2B veri Re=3.4e6'da koşulmuştu.
MiniHawk 15 m/s'te kiriş 0.353 m ile Re=3.5e5 uçuyor — 9.6 KAT fark. Türbülanslı
sürtünme Cd~Re^-0.2 ile ölçeklenir, yani profil sürüklemesinde ~%57 sistematik
sapma. Birleştirici bu yüzden MUTLAK sürüklemeyi yayınlamayı reddediyordu.

İKİNCİ ENGEL: mevcut 2B Cd mesh-bağımsız değildi (gci_airfoil: kaba gridlerde
NEGATİF, en incede 163k hücrede hâlâ tırmanıyor). Bu kampanya dört seviyeli bir
aile koşup bandı ÖLÇER.

2B'YE ÖZGÜ TUZAK: temsili hücre boyu h = N^(-1/2), N^(-1/3) DEĞİL. Aynı veride
3B formülü U=%19.9, doğru 2B formülü U=%9.8 verdi — iki kat. `band_from_levels`
`boyut=2` ile çağrılır.

Kurulum: kOmegaSSTLM (Re=3.5e5 GEÇİŞ-baskındır; tam-türbülans sınır tabakayı
aşırı kalınlaştırır), ilk hücre 3e-5 kiriş → y⁺≈0.5.

    python experiments/kesit_re35e4.py [--pilot]

Çıktı: kesit_re35e4.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

V, KIRIS = 50.0, 1.0
RE_HEDEF = 3.5e5
NU = V * KIRIS / RE_HEDEF          # 1.4286e-4
ILK_HUCRE = 3.0e-5                 # y⁺≈0.5 (Re=3.5e5'te 8e-6 gereksiz ince: y⁺=0.13)
FARFIELD_R, WAKE_L = 15.0, 20.0

# r≈1.3 (Celik 2008) — 2B'de h = N^(-1/2) olduğu için boyutlar 1.3 katlanır.
SEVIYELER = [("re35_L1", 200, 60, 100),
             ("re35_L2", 260, 78, 130),
             ("re35_L3", 338, 101, 169),
             ("re35_L4", 440, 132, 220)]
ALFA_GCI = 4.0
ALFA_POLAR = [0.0, 8.0]            # en ince seviyede
S1, S2 = 3000, 6000                # SST ön-koşu + LM


def kos(lbl, na, nw, nj, alfa, s1=S1, s2=S2) -> dict | None:
    komut = [sys.executable, str(HERE / "exp_cgrid_run.py"), lbl,
             str(na), str(nw), str(nj), str(s1), str(s2),
             str(FARFIELD_R), str(WAKE_L), str(NU), str(ILK_HUCRE), str(alfa)]
    t0 = time.time()
    r = subprocess.run(komut, cwd=KOK, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=14400)
    dk = (time.time() - t0) / 60
    son = (r.stdout or "").strip().splitlines()[-3:]
    print(f"  [{lbl} α={alfa}] {dk:.1f} dk  " + " | ".join(son), flush=True)
    p = KOK / f"gci_cgrid_{lbl}.json"
    if not p.exists():
        print(f"  [{lbl}] ÇIKTI YOK — stderr: {(r.stderr or '')[-300:]}", flush=True)
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d["_dk"] = round(dk, 1)
    return d


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pilot = "--pilot" in sys.argv
    print(f"Kesit kampanyası: Re={RE_HEDEF:.2e} (nu={NU:.4e}), "
          f"ilk hücre={ILK_HUCRE:.1e}, model=kOmegaSSTLM", flush=True)

    seviyeler = SEVIYELER[:1] if pilot else SEVIYELER
    s1, s2 = (400, 800) if pilot else (S1, S2)
    gci_kayit = []
    for lbl, na, nw, nj in seviyeler:
        d = kos(lbl, na, nw, nj, ALFA_GCI, s1, s2)
        if d and d.get("status") == "ok":
            gci_kayit.append({"ad": lbl, "cells": d.get("cells"),
                              "Cd": d["LM"]["Cd"], "Cl": d["LM"]["Cl"],
                              "dk": d["_dk"]})
        elif d:
            gci_kayit.append({"ad": lbl, "cells": d.get("cells"),
                              "durum": d.get("status")})

    polar = [{"alpha": ALFA_GCI, **{k: v for k, v in (gci_kayit[-1] if gci_kayit
                                                      else {}).items()
                                    if k in ("Cd", "Cl")}}]
    if not pilot:
        en_ince = SEVIYELER[-1]
        for a in ALFA_POLAR:
            d = kos(f"{en_ince[0]}_a{int(a)}", *en_ince[1:], a)
            if d and d.get("status") == "ok":
                polar.append({"alpha": a, "Cd": d["LM"]["Cd"], "Cl": d["LM"]["Cl"]})

    from report_generator import band_from_levels
    gecerli = [k for k in gci_kayit if k.get("Cd") is not None and k.get("cells")]
    band = (band_from_levels([k["cells"] for k in gecerli],
                             [k["Cd"] for k in gecerli], boyut=2)
            if len(gecerli) >= 2 else None)

    rec = {
        "vaka": (f"NACA0012 2B kesit — Re={RE_HEDEF:.2e} (MiniHawk uçuş Re'si), "
                 f"kOmegaSSTLM, C-grid ailesi"),
        "_neden": ("polar_birlestirme 3B polari 2B kesit surukleme verisinden "
                   "kuruyor; depodaki veri Re=3.4e6 idi (9.6 kat fark, ~%57 "
                   "sistematik sapma) ve mesh-bagimsiz DEGILDI. Bu kampanya "
                   "kanadin kendi Re'sinde ve bandiyla birlikte olcer."),
        "re": RE_HEDEF, "nu": NU, "ilk_hucre_kiris": ILK_HUCRE,
        "model": "kOmegaSSTLM (2-asamali SST->LM)",
        "boyut_notu": ("h = N^(-1/2) — 2B. N^(-1/3) kullanmak ayni veride bandi "
                       "iki kat sisiriyordu (%9.8 -> %19.9)."),
        "seviyeler": gci_kayit, "band": band, "polar": polar,
        "_uretim": "Üretim: python experiments/kesit_re35e4.py",
    }
    rec["verdikt"] = (
        f"{len(gecerli)}/{len(gci_kayit)} seviye tamamlandi. "
        + (f"Sayisal band: {band['kaynak']} -> U=%{band['u_pct']}. "
           if band else "Band hesaplanamadi (yeterli seviye yok). ")
        + ("MUTLAK Cd birlestiriciye verilebilir." if band and band["u_pct"] < 15
           else "Band genis ya da yok — birlestirici mutlak Cd yayinlamamali."))
    (KOK / "kesit_re35e4.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + rec["verdikt"])
    print("-> kesit_re35e4.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
