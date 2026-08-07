"""Başarım matrisi — hücre × çekirdek, ÖLÇÜLEN süre ve bellek.

NEDEN: rapordaki tek başarım verisi tek bir koşudan gelen aşama dağılımıydı.
"Ne kadar sürer?" ve "bu makinede kaç hücre kaldırır?" sorularının cevabı yoktu.
Aşama telemetrisi ve bellek örneklemesi eklendiğine göre ikisi de ölçülebilir.

BU BİR KIYASLAMA (benchmark) DEĞİLDİR: tek geometri (küp), tek makine, tek
çözücü ayarı. Ölçülen şey bu platformun bu donanımdaki ÖLÇEKLENME EĞİLİMİDİR;
başka bir makinede sayılar değişir. Amaç mutlak hız iddiası değil, planlama
için taban vermek ve bellek katsayısını ölçüme bağlamak.

TASARIM: koşular SIRAYLA yapılır. Paralel koşmak çekirdek ve bellek-bant
rekabeti yaratır ve tam da ölçmek istediğimiz şeyi bozar.

    python experiments/basarim_matrisi.py            # tam matris
    python experiments/basarim_matrisi.py --hizli    # tek satır (duman testi)
Çıktı: basarim_matrisi.json
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

STL = KOK / "vehicle_runs" / "gci_kup.stl"
CIKTI = KOK / "basarim_matrisi.json"
CALISMA = KOK / "_basarim"

HUCRE_BUTCELERI = (60_000, 150_000, 350_000)
CEKIRDEKLER = (1, 4, 8)


def _tek_kosu(butce: int, cekirdek: int, etiket: str) -> dict:
    from vehicle_pipeline import run_vehicle_analysis
    kok = CALISMA / etiket
    if kok.exists():
        shutil.rmtree(kok, ignore_errors=True)
    kok.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = run_vehicle_analysis(
        STL, vehicle_type="genel", velocity=10.0, alpha_deg=0.0,
        quality="standart", out_root=str(kok), n_processors=cekirdek,
        max_cells=butce, ref_bump=0, mesh_sensitivity=False)
    duvar_s = time.time() - t0
    mesh = getattr(r, "mesh", None) or {}
    bellek = getattr(r, "bellek", None) or {}
    asama = getattr(r, "asama_sureleri", None) or []
    return {
        "etiket": etiket, "butce": butce, "cekirdek": cekirdek,
        "durum": getattr(r, "status", "?"),
        "cells": mesh.get("cells"),
        "duvar_s": round(duvar_s, 1),
        "asama_sureleri": asama,
        "cozucu_s": round(sum(a["sure_s"] for a in asama
                              if "foamRun" in a.get("asama", "")), 1) or None,
        "mesh_s": round(sum(a["sure_s"] for a in asama
                            if "snappy" in a.get("asama", "").lower()), 1) or None,
        "bellek": bellek,
        "cd": getattr(r, "cd", None),
    }


def calistir(hizli: bool = False) -> dict:
    kombinasyon = ([(HUCRE_BUTCELERI[0], CEKIRDEKLER[0])] if hizli else
                   [(b, c) for b in HUCRE_BUTCELERI for c in CEKIRDEKLER])
    satirlar = []
    for i, (b, c) in enumerate(kombinasyon, 1):
        etiket = f"b{b // 1000}k_c{c}"
        print(f"[{i}/{len(kombinasyon)}] {etiket} — bütçe {b:,}, {c} çekirdek…",
              flush=True)
        s = _tek_kosu(b, c, etiket)
        satirlar.append(s)
        print(f"    durum={s['durum']} hücre={s['cells']} "
              f"duvar={s['duvar_s']}s çözücü={s['cozucu_s']}s "
              f"bellek+={(s['bellek'] or {}).get('artis_gb')}GB", flush=True)
        (KOK / "basarim_matrisi_kismi.json").write_text(
            json.dumps(satirlar, indent=2, ensure_ascii=False), encoding="utf-8")

    ok = [s for s in satirlar if s["durum"] == "ok" and s["cells"]]
    rec = {
        "vaka": "Başarım matrisi — hücre × çekirdek (küp, tek makine)",
        "_neden": ("Rapordaki tek basarim verisi TEK kosudan gelen asama "
                   "dagilimiydi; 'ne kadar surer' ve 'kac hucre kaldirir' "
                   "sorularinin olculmus cevabi yoktu."),
        "kurulum": {"geometri": STL.name, "tip": "genel", "hiz_m_s": 10.0,
                    "kalite": "standart", "butceler": list(HUCRE_BUTCELERI),
                    "cekirdekler": list(CEKIRDEKLER),
                    "sirali": "koşular SIRAYLA — paralel koşu ölçümü bozar"},
        "satirlar": satirlar,
        "_kisit": ("KIYASLAMA DEGILDIR: tek geometri, tek makine, tek cozucu "
                   "ayari. Bellek olcumu sistem GENELIDIR (WSL2 VM ayri surec "
                   "degil) ve kosu oncesi tabana gore artistir — yani UST SINIR."),
        "_uretim": "Üretim: python experiments/basarim_matrisi.py",
    }
    if ok:
        rec["olcek"] = _olcekleme(ok)
        rec["verdikt"] = rec["olcek"]["ozet"]
    else:
        rec["verdikt"] = "Hicbir kosu tamamlanmadi — matris URETILEMEDI."
    return rec


def _olcekleme(ok: list[dict]) -> dict:
    """Çekirdek ölçeklenmesi ve hücre başına maliyet — ölçülenden."""
    out: dict = {"cekirdek_hizlanmasi": {}, "hucre_basina_ms": {}}
    for b in sorted({s["butce"] for s in ok}):
        grup = sorted((s for s in ok if s["butce"] == b), key=lambda s: s["cekirdek"])
        taban = next((s for s in grup if s["cekirdek"] == 1), None)
        if taban and taban["cozucu_s"]:
            out["cekirdek_hizlanmasi"][f"{b // 1000}k"] = {
                str(s["cekirdek"]): round(taban["cozucu_s"] / s["cozucu_s"], 2)
                for s in grup if s["cozucu_s"]}
        for s in grup:
            if s["cozucu_s"] and s["cells"]:
                out["hucre_basina_ms"][s["etiket"]] = round(
                    s["cozucu_s"] * 1000 / s["cells"], 4)
    en_buyuk = max(ok, key=lambda s: s["cells"])
    out["ozet"] = (
        f"{len(ok)} kosu tamamlandi. En buyuk: {en_buyuk['cells']:,} hucre, "
        f"{en_buyuk['cekirdek']} cekirdek, cozucu {en_buyuk['cozucu_s']}s, "
        f"bellek +{(en_buyuk['bellek'] or {}).get('artis_gb')} GB.")
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir(hizli="--hizli" in sys.argv)
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print("\n" + rec["verdikt"])
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
