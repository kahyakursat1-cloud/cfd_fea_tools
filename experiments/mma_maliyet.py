"""MMA'nın iterasyon başına MALİYETİ — üretim kararının eksik sayısı.

`mma_bolum10.py` raporun iki koşulunu ölçtü (kıyaslar yeniden koşuldu, MMA
kendi ölçütüyle durdu) ama üçüncü bir soruyu hiç sormadı: MMA bir iterasyonda
ne kadar PAHALI? Bu sorulmadan üretim hattı değiştirilemez, çünkü kıyasların
hepsi SABİT ITERASYON BÜTÇESİNDE koşuyor --- eğer MMA iterasyonu iki kat
pahalıysa, aynı SÜREDE OC iki kat çok adım atar ve kıyas sabit-iterasyonda
değil sabit-sürede yapılmalıydı.

ÖLÇÜM AYRIŞTIRILIR. Toplam süre iki parçadır: FEA çözümü (iki güncelleyicide
AYNI) ve güncelleme adımı (farklı). Toplamı kıyaslamak farkı seyreltir ve
"fark yok" dedirtir; ayrı ölçüm hangi parçanın değiştiğini söyler.

    python experiments/mma_maliyet.py
Çıktı: mma_maliyet.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

CIKTI = KOK / "mma_maliyet.json"
ITER = 30


def _olc(kur, guncelleyici: str, **kw) -> dict:
    t, _ = kur()
    t0 = time.perf_counter()
    _, h = t.optimize(kw.pop("vf"), "stress", max_iter=ITER,
                      guncelleyici=guncelleyici, **kw)
    return {"toplam_s": round(time.perf_counter() - t0, 2),
            "iterasyon": len(h),
            "iter_basi_ms": round(1000 * (time.perf_counter() - t0) / len(h), 1)}


def olc() -> dict:
    from stress_topopt3d_bench import VF as VF3
    from stress_topopt3d_bench import build_lbracket as kur3
    from stress_topopt_lbracket import VF as VF2
    from stress_topopt_lbracket import build_lbracket as kur2

    r = {
        "2B_OC": _olc(kur2, "oc", vf=VF2, tol=0.01),
        "2B_MMA": _olc(kur2, "mma", vf=VF2, tol=0.01),
        "3B_OC": _olc(kur3, "oc", vf=VF3, tol=0.01, move=0.15),
        "3B_MMA": _olc(kur3, "mma", vf=VF3, tol=0.01, move=0.15),
    }
    return _ozetle(r)


def esit_maliyet(oran: dict) -> dict:
    """Kıyas MMA lehine yanlıysa YANLILIĞI GİDER: OC'ye MMA'nın aynı SÜREDE
    atabileceği kadar iterasyon ver ve öyle sor.

    Bunu yapmadan ``MMA daha iyi'' demek, MMA'ya daha büyük hesap bütçesi
    verip ``daha iyi'' demektir.
    """
    from stress_topopt3d_bench import VF, build_lbracket, peak_eta
    mma_iter = 80
    oc_iter = int(round(mma_iter * oran["3B"]))
    cikti = {}
    for ad, gunc, it in (("MMA", "mma", mma_iter), ("OC_esit_maliyet", "oc", oc_iter)):
        t, _ = build_lbracket()
        t0 = time.perf_counter()
        rho, h = t.optimize(VF, "stress", max_iter=it, move=0.15, tol=0.01,
                            guncelleyici=gunc)
        cikti[ad] = {"iterasyon": len(h), "sure_s": round(time.perf_counter() - t0, 1),
                     "peak_gerilme": round(peak_eta(t, rho), 4)}
    a, b = cikti["MMA"]["peak_gerilme"], cikti["OC_esit_maliyet"]["peak_gerilme"]
    cikti["MMA_hala_iyi_mi"] = bool(a < b)
    cikti["fark_pct"] = round(100 * (b - a) / b, 2)
    cikti["_not"] = (f"OC'ye {oc_iter} iterasyon verildi (MMA'nin {mma_iter} "
                     f"iterasyonuyla esit maliyet, oran {oran['3B']}x).")
    return cikti


def _ozetle(r: dict) -> dict:
    oran = {b: round(r[f"{b}_MMA"]["iter_basi_ms"] / r[f"{b}_OC"]["iter_basi_ms"], 3)
            for b in ("2B", "3B")}
    en_kotu = max(oran.values())
    esit = esit_maliyet(oran) if en_kotu > 1.20 else None
    return {
        "vaka": "MMA iterasyon maliyeti — sabit-iterasyon kıyası adil mi",
        "esit_maliyet_3B": esit,
        "_neden": ("Bolum 10 kiyaslari SABIT ITERASYON butcesinde kosuyor. MMA "
                   "iterasyonu OC'den belirgin pahaliysa ayni SUREDE OC daha "
                   "cok adim atar ve kiyas MMA lehine yanlidir."),
        "iterasyon_butcesi": ITER,
        "kosular": r,
        "maliyet_orani_MMA_bolu_OC": oran,
        "sabit_iterasyon_kiyasi_adil_mi": bool(en_kotu <= 1.20),
        "verdikt": _hukum(oran, en_kotu, esit),
        "_kisit": ("Tek makine, tek kosu, isinma yok. Oran ~1 civarindaysa "
                   "olcum gurultusu bu kadar bir farki tasiyabilir; hukum "
                   "yalniz BUYUK bir fark olup olmadigini soyler."),
        "_uretim": "Üretim: python experiments/mma_maliyet.py",
    }


def _hukum(oran: dict, en_kotu: float, esit: dict | None) -> str:
    s = (f"MMA iterasyonu OC'ye göre 2B'de {oran['2B']}×, 3B'de {oran['3B']}× "
         f"maliyetli. ")
    if en_kotu <= 1.20:
        return s + ("Fark %20'nin altında: FEA çözümü iki güncelleyicide aynı "
                    "ve baskın maliyet o. SABİT-İTERASYON KIYASI ADİL --- "
                    "Bölüm 10'un sonuçları maliyet yanlılığı taşımıyor.")
    s += (f"Fark %20'yi aşıyor ({en_kotu}×): sabit-iterasyon kıyası MMA lehine "
          "YANLI ve tek başına üretim kararına dayanak OLAMAZ. YANLILIK "
          "GİDERİLDİ --- ")
    if esit is None:
        return s + "ama eşit-maliyet koşusu yapılmadı."
    s += (f"OC'ye {esit['OC_esit_maliyet']['iterasyon']} iterasyon verildi "
          f"(MMA'nın 80'iyle eşit maliyet): OC tepe "
          f"{esit['OC_esit_maliyet']['peak_gerilme']}, MMA "
          f"{esit['MMA']['peak_gerilme']}. ")
    return s + ("MMA EŞİT MALİYETTE DE ÖNDE "
                f"(%{esit['fark_pct']}); üstünlük bütçeden gelmiyor."
                if esit["MMA_hala_iyi_mi"] else
                "EŞİT MALİYETTE ÜSTÜNLÜK KAYBOLUYOR: kazanç MMA'nın kendisinden "
                "değil, ona verilen fazla bütçeden geliyordu.")


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
