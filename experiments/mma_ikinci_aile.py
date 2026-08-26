"""MMA kararı İKİNCİ bir problem ailesinde sınanır — L-braket'e özgü müydü?

DIŞ HAKEM P2 (2026-08-26): ``MMA'yı başka geometri/problem ailesinde sınama
--- L-bracket ile sınırlı.'' Haklı, ve kısıt zaten `mma_bolum10.json`da
yazılıydı: tek problem ailesi, tek çözünürlük.

SORU KEŞKİN VE FİZİKSELDİR, ``bir vaka daha koşalım'' değil. L-braketin
gerilme tasarımını GİRİNTİLİ KÖŞEDEKİ TEKİLLİK yönetir: optimizasyon
malzemeyi o köşeyi yuvarlamak için taşır. MMA'nın kazancı bu yeniden-dağıtım
davranışına mı özgü, yoksa güncelleyicinin kendisinde mi?

İKİNCİ AİLE: MBB kiriş --- topoloji optimizasyonunun kanonik ikinci
benchmark'ı ve L-braketten YAPISAL OLARAK farklı: girintili köşe YOK, yani
gerilme tekilliği tasarımı sürüklemiyor; yük tek noktada, mesnetler simetri
+ kayar. Eğer MMA'nın üstünlüğü tekillik-sürümlü yeniden-dağıtımdan
geliyorsa burada KAYBOLMALI.

ÜÇ ÖLÇÜ, ÜÇÜ DE BÖLÜM 10'DAKİYLE AYNI:
  1. Tepe gerilme (kalite)
  2. Kendi durma ölçütüyle durma (kararlılık)
  3. EŞİT HESAP MALİYETİNDE kıyas --- MMA iterasyonu pahalıysa sabit-iterasyon
     kıyası ona daha büyük bütçe verir; bu yanlılık Bölüm 10'da ölçülüp
     giderilmişti ve burada da giderilir.

    python experiments/mma_ikinci_aile.py [--hizli]
Çıktı: mma_ikinci_aile.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from stress_topopt2d import StressTopo2D  # noqa: E402

CIKTI = KOK / "mma_ikinci_aile.json"
NELX, NELY = 90, 30
VF = 0.40
KOMP_ITER = 70
GERILME_ITER = 80
YAKINSAMA_TAVANI = 2000


def build_mbb() -> StressTopo2D:
    """MBB kiriş (yarım model, simetri).

    Sol kenar: x-simetri (u_x = 0, tüm düğümler).
    Sağ-alt köşe: kayar mesnet (u_y = 0).
    Sol-üst köşe: düşey tekil yük.

    Bu KANONIK kurulumdur (Sigmund'un 99-satirlik kodundaki MBB) ve
    L-braketten yapisal olarak farkli: girintili kose YOK, pasif bolge YOK.
    """
    fixed: list[int] = []
    for j in range(NELY + 1):                    # sol kenar: u_x = 0
        fixed.append(2 * (j * (NELX + 1) + 0))
    sag_alt = 0 * (NELX + 1) + NELX              # sag-alt: u_y = 0
    fixed.append(2 * sag_alt + 1)
    sol_ust = NELY * (NELX + 1) + 0              # sol-ust: dusey yuk
    return StressTopo2D(NELX, NELY, sorted(set(fixed)),
                        [2 * sol_ust + 1], [-1.0], rmin=2.0)


def peak(t: StressTopo2D, rho) -> float:
    u, _ = t.solve(rho)
    _, vm = t.elem_stress(u)
    return float((rho ** t.q * vm).max())


def _kosu(guncelleyici: str, tavan: int | None = None,
          olc_sure: bool = False) -> dict:
    t = build_mbb()
    t0 = time.perf_counter()
    rho_c, _ = t.optimize(VF, "compliance", max_iter=KOMP_ITER,
                          guncelleyici=guncelleyici)
    pc = peak(t, rho_c)
    it = tavan or GERILME_ITER
    t1 = time.perf_counter()
    rho_s, h = t.optimize(VF, "stress", max_iter=it, tol=0.01,
                          guncelleyici=guncelleyici)
    sure = time.perf_counter() - t1
    o = [q["obj"] for q in h][-20:]
    net = abs(o[-1] - o[0]) if len(o) > 1 else 0.0
    top = sum(abs(b - a) for a, b in zip(o, o[1:])) if len(o) > 1 else 0.0
    kayit = {
        "peak_komp": round(pc, 4), "peak_gerilme": round(peak(t, rho_s), 4),
        "azalma_pct": round(100 * (pc - peak(t, rho_s)) / pc, 2),
        "iterasyon": len(h), "tavan": it, "durdu_mu": len(h) < it,
        "son_ch": round(h[-1]["ch"], 5),
        "bosa_giden_hareket_pct": (round(100 * (1 - net / top), 1)
                                   if top > 0 else None),
        "toplam_sure_s": round(time.perf_counter() - t0, 2),
    }
    if olc_sure:
        kayit["gerilme_iter_basi_ms"] = round(1000 * sure / max(len(h), 1), 1)
    return kayit


def olc(hizli: bool = False) -> dict:
    r = {
        "OC": _kosu("oc", olc_sure=True),
        "MMA": _kosu("mma", olc_sure=True),
    }
    oran = (r["MMA"]["gerilme_iter_basi_ms"]
            / max(r["OC"]["gerilme_iter_basi_ms"], 1e-9))
    # YANLILIK GIDERME: OC'ye MMA'nin GERILME iterasyonlariyla esit maliyet
    # veren adim sayisi. Bolum 10'da bu adim atlanmisti ve 3B'de kiyas MMA
    # lehine yanliydi; ayni hatayi burada tekrarlamamak icin en bastan var.
    esit_iter = int(round(GERILME_ITER * oran))
    r["OC_esit_maliyet"] = _kosu("oc", tavan=esit_iter)
    if not hizli:
        r["MMA_yakinsama"] = _kosu("mma", tavan=YAKINSAMA_TAVANI)
        r["OC_yakinsama"] = _kosu("oc", tavan=YAKINSAMA_TAVANI)
    return _ozetle(r, oran, esit_iter, hizli)


def _ozetle(r: dict, oran: float, esit_iter: int, hizli: bool) -> dict:
    mma, oc_esit = r["MMA"], r["OC_esit_maliyet"]
    fark = 100 * (oc_esit["peak_gerilme"] - mma["peak_gerilme"]) \
        / max(abs(oc_esit["peak_gerilme"]), 1e-12)
    return {
        "vaka": "MMA ikinci problem ailesinde — MBB kiriş",
        "_neden": ("MMA karari YALNIZ L-braket ailesinde olculmustu (dis "
                   "hakem P2). L-braketin gerilme tasarimini GIRINTILI KOSE "
                   "tekilligi yonetir; MBB'de oyle bir kose YOK. MMA'nin "
                   "kazanci algoritmanin mi, o problemin mi?"),
        "problem": {"ad": "MBB kiriş (yarım model, simetri)",
                    "grid": f"{NELX}x{NELY}", "volfrac": VF,
                    "pasif_bolge": False, "girintili_kose": False,
                    "_fark": ("L-braket: girintili kose + pasif bolge, "
                              "tasarimi gerilme tekilligi surukler. MBB: "
                              "tekillik yok, tasarimi yuk yolu surukler.")},
        "kosular": r,
        "maliyet_orani_MMA_bolu_OC": round(oran, 3),
        "esit_maliyet_iterasyonu": esit_iter,
        # BENCHMARK'IN KENDI OLCUTU --- kiyastan ONCE gelir.
        # `stress_topopt_lbracket` basariyi soyle tanimliyor:
        # peak_vm(stress) < peak_vm(compliance). Iki guncelleyiciyi
        # birbiriyle kiyaslamadan ONCE her birinin BU olcutu gecip
        # gecmedigi sorulmali --- gecemeyen bir kosuyu "%X geride" diye
        # raporlamak, basarisizligi bir derece farkina cevirir.
        "amaci_GERCEKTEN_dusurdu_mu": {ad: k["azalma_pct"] > 0
                                       for ad, k in r.items()},
        "esit_maliyette_MMA_onde_mi": bool(fark > 0),
        "esit_maliyette_fark_pct": round(fark, 2),
        "MMA_kendi_olcutuyle_durdu": (None if hizli
                                      else r["MMA_yakinsama"]["durdu_mu"]),
        "OC_kendi_olcutuyle_durdu": (None if hizli
                                     else r["OC_yakinsama"]["durdu_mu"]),
        "verdikt": _hukum(r, oran, esit_iter, fark, hizli),
        "_kisit": ("Iki aile de 2B ve ayni motordur; ucuncu bir aile ya da 3B "
                   "MBB SINANMADI. MMA'nin asimptot katsayilari Svanberg'in "
                   "onerdigi degerlerde ve HICBIR probleme gore ayarlanmadi "
                   "--- bu, iki ailede de ayni kosullarda kiyas demektir ama "
                   "MMA'nin ayarlanmis halini temsil etmez."),
        "_uretim": "Üretim: python experiments/mma_ikinci_aile.py",
    }


def _hukum(r: dict, oran: float, esit_iter: int, fark: float,
           hizli: bool) -> str:
    oc, mma, oc_e = r["OC"], r["MMA"], r["OC_esit_maliyet"]
    # OC BU AILEDE AMACI TERSINE CEVIRIYOR --- once bu soylenir.
    if oc["azalma_pct"] <= 0:
        s = (f"OC BU AİLEDE BAŞARISIZ: gerilme-min tepe gerilmeyi "
             f"DÜŞÜRMEK yerine ARTIRDI ({oc['peak_komp']} -> "
             f"{oc['peak_gerilme']}, %{-oc['azalma_pct']:.2f} KÖTÜLEŞME) --- "
             f"benchmark'ın kendi ölçütü peak(stress) < peak(compliance) ve "
             f"OC onu geçemiyor. MMA aynı problemde {mma['peak_komp']} -> "
             f"{mma['peak_gerilme']} (%{mma['azalma_pct']:.2f} iyileşme). "
             f"Yani bulgu bir DERECE farkı değil: bir güncelleyici amacı "
             f"tersine çeviriyor. ")
    else:
        s = ""
    s += (f"MBB kirişte tepe gerilme: OC {oc['peak_gerilme']}, MMA "
         f"{mma['peak_gerilme']}. Boşa giden hareket "
         f"%{oc['bosa_giden_hareket_pct']} vs %{mma['bosa_giden_hareket_pct']}. "
         f"MMA iterasyonu {oran:.3f}x maliyetli; eşit maliyet için OC'ye "
         f"{esit_iter} iterasyon verildi ve tepe {oc_e['peak_gerilme']} oldu "
         f"--- ")
    s += (f"MMA %{fark:.2f} ÖNDE. " if fark > 0
          else f"MMA ÖNDE DEĞİL (%{fark:.2f}). ")
    if not hizli:
        m, o = r["MMA_yakinsama"], r["OC_yakinsama"]
        s += (f"DURMA: MMA {m['iterasyon']} iterasyonda kendi toleransıyla "
              f"{'DURDU' if m['durdu_mu'] else 'DURMADI'}; OC "
              f"{o['iterasyon']} iterasyonda "
              f"{'durdu' if o['durdu_mu'] else 'DURMADI'} (son adım "
              f"{o['son_ch']}). ")
    if fark > 0:
        return s + ("Bölüm 10'un bulgusu İKİNCİ AİLEDE DE geçerli: MMA'nın "
                    "üstünlüğü L-braketin girintili köşesine özgü değil.")
    return s + ("Bölüm 10'un bulgusu İKİNCİ AİLEDE ÇIKMADI: MMA'nın "
                "üstünlüğü L-braket ailesine özgü olabilir ve üretim kararı "
                "bu ışıkta yeniden okunmalıdır.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc("--hizli" in sys.argv)
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
