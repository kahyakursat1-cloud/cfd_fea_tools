"""Koşu-tekrar gürültü tabanı — girdi UQ'nun ölçtüğü şey gerçekten girdi mi.

NEDEN: LHS taraması u_girdi = %0,95 verdi. Ama duyarlılıklar şüpheli çıktı ---
üç girdinin Pearson r'si benzer (V −0,315, α −0,207, ρ −0,310) ve İKİSİ NULL
DEĞİŞKEN:

  * ρ  — Cd boyutsuzdur ve çözücü SABİT kinematik viskoziteyle koşar
         (nu = 1,5e-5). Re = V·L/ν, yani ρ'ya bağlı DEĞİL; ve
         Cd = F/(½ρV²A) ifadesinde ρ pay ve paydada birlikte gider.
         Matematiksel olarak Cd, ρ'dan BAĞIMSIZDIR.
  * α  — taban vaka bir KÜREdir, eksenel simetrik. Hücum açısı bir simetri
         işlemidir; Cd değişemez.

İki null değişkenin korelasyonu gerçek değişkeninkiyle aynı mertebedeyse,
ölçülen saçılma GİRDİDEN değil KOŞU TEKRARSIZLIĞINDAN geliyor olabilir.

BU BETİK ONU DOĞRUDAN ÖLÇER: aynı girdiyle N kez koşar. Ağ da sabit
(LHS taramasında 30/30 koşu 316.514 hücre verdi), çözücü de deterministik
görünüyor --- ama paralel indirgeme sırası ve Cd-yakınsama erken-durdurması
koşudan koşuya küçük fark bırakabilir. Fark VARSA, u_girdi'nin ne kadarının
girdi olduğunu ancak bu taban söyler.

    python experiments/girdi_uq_gurultu_tabani.py [--n 6]
Çıktı: girdi_uq_gurultu_tabani.json
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "girdi_uq_gurultu_tabani.json"


def olc(n: int = 6) -> dict:
    from girdi_uq_kos import TABAN

    from vehicle_pipeline import run_vehicle_analysis

    cd, hucre, dusen = [], [], []
    t0 = time.time()
    for i in range(1, n + 1):
        try:
            r = run_vehicle_analysis(
                str(TABAN["stl"]), vehicle_type=TABAN["vehicle_type"],
                velocity=TABAN["velocity"], alpha_deg=TABAN["alpha_deg"],
                quality=TABAN["quality"], rho=TABAN["rho"],
                out_root=str(KOK / "_uq_gurultu"), n_processors=4)
        except Exception as e:      # noqa: BLE001 — sebep KAYDEDILIYOR
            dusen.append(f"{i}: {type(e).__name__}: {e}"[:120])
            continue
        if r.status != "ok" or r.cd is None:
            dusen.append(f"{i}: {(r.error or 'cd yok')[:100]}")
            continue
        cd.append(r.cd)
        hucre.append((r.mesh or {}).get("cells"))
        print(f"[{i}/{n}] Cd={r.cd:.6f}  hücre={hucre[-1]}", flush=True)

    if len(cd) < 3:
        return {"vaka": "Koşu-tekrar gürültü tabanı",
                "verdikt": f"ÖLÇÜLEMEDİ — yalnız {len(cd)} koşu tamamlandı",
                "dusen": dusen,
                "_uretim": "Üretim: python experiments/girdi_uq_gurultu_tabani.py"}

    ort = sum(cd) / len(cd)
    sd = math.sqrt(sum((x - ort) ** 2 for x in cd) / (len(cd) - 1))
    taban_pct = 200.0 * sd / ort if ort else None

    # LHS taramasindan gelen u_girdi ile KIYAS
    uq = KOK / "girdi_uq_sonuc.json"
    u_girdi = None
    if uq.exists():
        u_girdi = json.loads(uq.read_text(encoding="utf-8")).get("u_girdi_pct")
    pay = (round(100.0 * taban_pct / u_girdi, 1)
           if (u_girdi and taban_pct is not None and u_girdi > 0) else None)

    return {
        "vaka": "Koşu-tekrar gürültü tabanı — aynı girdi, N koşu",
        "_neden": ("LHS taramasinda iki NULL degiskenin (kure icin alpha, "
                   "boyut analizi geregi rho) korelasyonu gercek degiskeninkiyle "
                   "AYNI mertebede cikti. Olculen sacilmanin ne kadari girdiden, "
                   "ne kadari kosu tekrarsizligindan?"),
        "n_istenen": n, "n_tamamlanan": len(cd), "dusen": dusen,
        "sure_dk": round((time.time() - t0) / 60, 1),
        "cd": [round(x, 6) for x in cd],
        "cd_ort": round(ort, 6), "cd_sd": round(sd, 7),
        "hucre_benzersiz": sorted({h for h in hucre if h}),
        "gurultu_tabani_pct": round(taban_pct, 3) if taban_pct is not None else None,
        "u_girdi_pct": u_girdi,
        "tabanin_u_girdideki_payi_pct": pay,
        "verdikt": (
            (f"GÜRÜLTÜ TABANI = %{taban_pct:.3f} (2σ/ortalama, {len(cd)} tekrar, "
             f"AYNI girdi). LHS taramasının verdiği u_girdi = %{u_girdi:.2f} ile "
             f"kıyaslandığında taban, ölçülen bandın ~%{pay:.0f}'ini açıklıyor. "
             + ("Yani u_girdi ÇOĞUNLUKLA girdi yanıtı DEĞİL koşu tekrarsızlığıdır "
                "ve bir ÜST SINIR olarak okunmalıdır."
                if (pay or 0) >= 50 else
                "Yani bandın baskın kısmı gerçekten girdiden geliyor."))
            if (taban_pct is not None and u_girdi) else
            f"gürültü tabanı %{taban_pct:.3f} (LHS sonucu yok, kıyas yapılamadı)"),
        "_kisit": (
            "Taban AYNI vakada olculdu; baska geometri/agda farkli olabilir. "
            "Ayrica tekrarsizligin KAYNAGI burada ayristirilmadi (paralel "
            "indirgeme sirasi mi, Cd-yakinsama erken-durdurmasi mi) — olculen "
            "sey yalnizca BUYUKLUGU. Null-degisken akil yurutmesi kureye "
            "OZGUDUR: alpha ancak eksenel simetrik govdede nulldur."),
        "_uretim": "Üretim: python experiments/girdi_uq_gurultu_tabani.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    n = 6
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    r = olc(n)
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
