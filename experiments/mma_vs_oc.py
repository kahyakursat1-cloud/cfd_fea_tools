"""OC ile MMA yan yana — gerilme-minimizasyonunda hangisi kararlı.

NEDEN: `stress_topopt3d` OC ile güncelleniyor ve kodun kendi yorumu
"OC stress'te tek-başına kararsız/salınımlı, iyi topoloji başlangıcı şart"
diyor. Warm-start bir ÇARE; bu deney sebebi ve MMA'nın onu kaldırıp
kaldırmadığını ölçer.

SEBEP ÖLÇÜLDÜ: OC adımı `np.maximum(-dx, 0)` ile pozitif duyarlılığı SIFIRLAR.
L-braketde aktif elemanların %12,8--65,7'si her adımda pozitif duyarlılık
taşıyor; gradyan BÜYÜKLÜĞÜNÜN atılan payı bir adımda %96,9'a çıkıyor ve amaç
tam o adımda 12,95 → 97,54 sıçrıyor.

ADİL KIYAS: aynı problem, aynı başlangıç (soğuk --- warm-start YOK, çünkü
sınanan şey tam olarak warm-start'a duyulan ihtiyaç), aynı hacim kısıtı, aynı
iterasyon sayısı, aynı filtre. Tek değişen GÜNCELLEME KURALI.

    python experiments/mma_vs_oc.py [--iter 40]
Çıktı: mma_vs_oc.json
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

CIKTI = KOK / "mma_vs_oc.json"


def _kos(t, volfrac, max_iter, kural, move=0.2):
    """Tek bir optimizasyon koşusu; `kural` ∈ {"oc","mma"}."""
    from mma import MMADurum, mma_adim

    x = np.full(t.ne, volfrac)
    x[t.passive] = t.emin
    aktif = ~t.passive
    xmin = np.full(t.ne, 1e-3)
    xmax = np.ones(t.ne)
    durum = MMADurum()
    hist = []
    t0 = time.time()
    for it in range(1, max_iter + 1):
        rho = t.filt(x)
        rho[t.passive] = t.emin
        u, K = t.solve(rho)
        obj, drho = t.pnorm_sens(rho, u, K)
        _, vm = t.elem_stress(u)
        tepe = float((rho ** t.q * vm).max())
        dx = t._chain_filter(drho)
        if kural == "oc":
            xnew = t._oc_step(x, dx, volfrac, move)
        else:
            # Hacim kisiti: sum(x_aktif)/n_aktif - volfrac <= 0
            n_akt = int(aktif.sum())
            f1 = float(x[aktif].sum() / n_akt - volfrac)
            df1 = np.where(aktif, 1.0 / n_akt, 0.0)
            xnew = mma_adim(x, dx, df1, f1, xmin, xmax, durum, move=move)
            xnew[t.passive] = t.emin
        ch = float(np.abs(xnew - x).max())
        x = xnew
        hist.append({"it": it, "obj": float(obj), "tepe_vm": tepe,
                     "degisim": round(ch, 4),
                     "hacim": float(x[aktif].mean())})
    return {"kural": kural, "gecmis": hist, "sure_s": round(time.time() - t0, 1),
            "son_obj": hist[-1]["obj"], "son_tepe_vm": hist[-1]["tepe_vm"],
            "en_iyi_obj": min(h["obj"] for h in hist),
            "en_kotu_obj": max(h["obj"] for h in hist),
            "son_hacim": hist[-1]["hacim"]}


def _salinim_olcusu(h, son: int = 20):
    """Kararlılık ölçüleri — SON DEĞER TEK BAŞINA YANILTIR.

    Ölçüldü: OC son değeri MMA'nınkinden düşük (0,8565 vs 0,9018) ama OC bir
    LİMİT ÇEVRİMİNDE dönüyor --- son 20 iterasyonda hareketinin %47'si boşa
    gidiyor (ileri-geri) ve raporlanan değer hangi iterasyonda durulduğuna
    bağlı (%2,83 yayılım). MMA'nın boşa giden hareketi %5 ve hâlâ iniyor.

    Yani "daha düşük sayı" ile "savunulabilir sayı" farklı şeyler. Üç ölçü
    birlikte durur:
      isaret_degisimi        — kaç kez yön değişti
      en_buyuk_sicrama_kat   — en kötü tek adım
      bosa_giden_hareket_pct — geç dönemde ileri-geri oranı (asıl ölçüt)
    """
    o = [x["obj"] for x in h]
    d = np.diff(o)
    gecis = int((np.sign(d[:-1]) * np.sign(d[1:]) < 0).sum())
    sicrama = float(max((o[i + 1] / max(o[i], 1e-30)) for i in range(len(o) - 1)))
    g = o[-son:] if len(o) > son else o
    ort = sum(g) / len(g)
    yukari = sum(max(g[i + 1] - g[i], 0.0) for i in range(len(g) - 1))
    asagi = sum(max(g[i] - g[i + 1], 0.0) for i in range(len(g) - 1))
    return {
        "isaret_degisimi": gecis, "en_buyuk_sicrama_kat": round(sicrama, 2),
        "son_pencere": son,
        "bosa_giden_hareket_pct": round(100 * yukari / (yukari + asagi + 1e-30), 1),
        "net_ilerleme_pct": round(100 * (g[0] - g[-1]) / ort, 2),
        "durma_noktasi_yayilimi_pct": round(100 * (max(g) - min(g)) / ort, 2),
    }


def olc(max_iter: int = 40, volfrac: float = 0.4) -> dict:
    from stress_topopt3d_bench import build_lbracket

    t, _passive = build_lbracket()
    sonuc = {}
    for kural in ("oc", "mma"):
        r = _kos(t, volfrac, max_iter, kural)
        r.update(_salinim_olcusu(r["gecmis"]))
        sonuc[kural] = r
        print(f"{kural.upper():>4}: son obj={r['son_obj']:.5f}  "
              f"en iyi={r['en_iyi_obj']:.5f}  en kötü={r['en_kotu_obj']:.4g}  "
              f"işaret değişimi={r['isaret_degisimi']}  "
              f"en büyük sıçrama={r['en_buyuk_sicrama_kat']}×  "
              f"{r['sure_s']}s", flush=True)

    oc, mma = sonuc["oc"], sonuc["mma"]
    kazanc = (oc["son_obj"] - mma["son_obj"]) / max(oc["son_obj"], 1e-30) * 100
    return {
        "vaka": "OC vs MMA — gerilme-minimizasyonunda kararlılık",
        "_neden": ("stress_topopt3d OC ile guncelleniyor ve kodun kendi yorumu "
                   "'OC stress'te tek-basina kararsiz/salinimli, iyi topoloji "
                   "baslangici sart' diyor. Warm-start bir CARE; bu deney "
                   "sebebi ve MMA'nin onu kaldirip kaldirmadigini olcer."),
        "problem": {"vaka": "L-braket 3B", "eleman": int(t.ne),
                    "volfrac": volfrac, "iterasyon": max_iter,
                    "baslangic": "SOĞUK (warm-start YOK — sınanan şey tam olarak "
                                 "warm-start'a duyulan ihtiyaç)"},
        "oc": oc, "mma": mma,
        "kazanc_pct": round(kazanc, 1),
        "verdikt": (
            f"SON DEĞER: OC {oc['son_obj']:.4f}, MMA {mma['son_obj']:.4f} "
            f"(MMA %{-kazanc:+.1f} daha yüksek). AMA SON DEĞER TEK BAŞINA "
            f"YANILTIR: OC bir LİMİT ÇEVRİMİNDE dönüyor — son "
            f"{oc['son_pencere']} iterasyonda hareketinin "
            f"%{oc['bosa_giden_hareket_pct']}'i boşa gidiyor ve raporlanan "
            f"değer durma noktasına %{oc['durma_noktasi_yayilimi_pct']} "
            f"duyarlı. MMA'da boşa giden hareket "
            f"%{mma['bosa_giden_hareket_pct']}, net ilerleme "
            f"%{mma['net_ilerleme_pct']} (OC'de %{oc['net_ilerleme_pct']}) — "
            f"yani MMA hâlâ VERİMLİ iniyor. İşaret değişimi "
            f"{oc['isaret_degisimi']} → {mma['isaret_degisimi']}, en büyük "
            f"tek-adım sıçraması {oc['en_buyuk_sicrama_kat']}× → "
            f"{mma['en_buyuk_sicrama_kat']}×. "
            + ("MMA daha DÜŞÜK sayı vermiyor ama SAVUNULABİLİR sayı veriyor: "
               "sonucu hangi iterasyonda durduğuna bağlı değil."
               if mma["bosa_giden_hareket_pct"] < 0.5 * oc["bosa_giden_hareket_pct"]
               else "MMA'nın kararlılık üstünlüğü bu problemde GÖSTERİLEMEDİ.")),
        "_kisit": (
            "TEK problem (L-braket) ve TEK cozunurluk. Optimizasyon "
            "algoritmalarinin kiyasi probleme baglidir; bu sonuc genel bir "
            "ustunluk iddiasi DEGILDIR. Ayrica MMA'nin asimptot katsayilari "
            "(0,7/1,2) Svanberg'in onerdigi degerlerdir ve BU probleme gore "
            "AYARLANMADI — ayarlanirsa sonuc degisebilir, ki bu da kiyasi "
            "adaletsiz yapardi."),
        "_uretim": "Üretim: python experiments/mma_vs_oc.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    it = 40
    if "--iter" in sys.argv:
        it = int(sys.argv[sys.argv.index("--iter") + 1])
    r = olc(it)
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
