"""Hücre başına bellek katsayısı — KOŞU ARŞİVİNDEN ölçülür, uydurulmaz.

NEDEN: bellek kapısının ihtiyacı olan tek sayı "hücre başına kaç kB". Bu sayı
çözücüye, türbülans modeline ve katman sayısına bağlıdır; literatürden alınan
tek bir değer bu makinede yanlış olur. Çözücü artık koşu boyunca sistem
belleğini örnekliyor (`bellek.artis_gb`), yani sayı ÖLÇÜLEBİLİR.

NE ÖLÇÜLÜR: bellek telemetrisi taşıyan her koşu için artis_gb / cells. Doğrusal
bir uyum değil, ROBUST bir merkez (medyan) alınır — tek bir koşu arka planda
başka bir iş varken ölçülmüş olabilir.

NE ÖLÇÜLMEZ: WSL2 VM'i ayrı bir süreç olmadığı için tek koşunun RSS'i
görülemez; ölçülen, sistem geneli kullanımın koşu boyunca ARTIŞIDIR. Makinede
başka bir şey çalışıyorsa sayı yukarı kayar ve bu bir ÜST SINIRDIR.

    python experiments/bellek_katsayisi.py         # arsivden
    python experiments/bellek_katsayisi.py --olc   # + buyuk olcum kosulari
Çıktı: bellek_katsayisi.json  (bellek_kapisi.py bunu okur)
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))


# GURULTU ESIKLERI. Kucuk kosularda cozucunun kendi bellegi (~0.05 GB) sistem
# geneli olcumun gurultusunun ALTINDA kalir; medyan almak gurultuye katsayi
# demektir. Olculdu (basarim matrisi, 18k-96k hucre): kB/hucre 0.9 ile 9.75
# arasinda sacildi — 10 KAT. Ayni geometri, ayni cozucu, tek degisen cekirdek
# sayisi. Yani sinyal yok.
EN_AZ_ARTIS_GB = 0.5       # bunun altindaki artis sistem gurultusuyle karisir
EN_COK_SACILMA = 3.0       # max/min bundan buyukse dagilim tutarli degil

# OLCUM KOSUSU: arsiv kucuk kaldigi icin katsayi olculemedi. Butceler bilerek
# genis araliklidir — regresyonun egimini SABIT YUKTEN ayirabilmesi icin en
# buyuk kosunun en kucugu belirgin sekilde asmasi gerekir.
OLCUM_BUTCELERI = (300_000, 700_000, 1_400_000)
OLCUM_CEKIRDEK = 4         # SABIT: cekirdek sayisi decomposePar kopyalarini
                           # degistirir, yani bellegi. Degisken tutmak egimi kirletir.
EN_AZ_R2 = 0.90            # dogrusal modelin uymadigi yerde katsayi yazilmaz


def topla() -> list[dict]:
    kayit = []
    for p in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        b = d.get("bellek") or {}
        cells = (d.get("mesh") or {}).get("cells")
        artis = b.get("artis_gb")
        if not cells or not isinstance(artis, (int, float)) or artis <= 0:
            continue
        kayit.append({"kosu": p.parent.name, "cells": cells,
                      "artis_gb": artis, "toplam_gb": b.get("toplam_gb"),
                      "kb_hucre": round(artis * 1e6 / cells, 3)})
    # BASARIM MATRISI de bellek olcumu tasir ve kendi calisma dizinine yazar
    # (vehicle_runs altinda degil). Onu disarida birakmak, elimizdeki en
    # kontrollu olcum setini gormezden gelmek olurdu.
    bm = KOK / "basarim_matrisi.json"
    if bm.exists():
        for r in json.loads(bm.read_text(encoding="utf-8")).get("satirlar", []):
            b2 = r.get("bellek") or {}
            artis, cells = b2.get("artis_gb"), r.get("cells")
            if not cells or not isinstance(artis, (int, float)) or artis <= 0:
                continue
            kayit.append({"kosu": f"basarim/{r['etiket']}", "cells": cells,
                          "artis_gb": artis, "toplam_gb": b2.get("toplam_gb"),
                          "cekirdek": r.get("cekirdek"),
                          "kb_hucre": round(artis * 1e6 / cells, 3)})
    # OLCUM KOSULARI DISKTEN OKUNUR. Aksi hâlde analizdeki her degisiklik
    # saatlerce CFD'yi yeniden kosmayi gerektirirdi; olcum bir kez yapilir,
    # uzerinde defalarca dusunulur.
    om = KOK / "bellek_olcum_kismi.json"
    if om.exists():
        _var = {k["kosu"] for k in kayit}
        for r in json.loads(om.read_text(encoding="utf-8")):
            if r.get("kosu") in _var or not r.get("cells"):
                continue
            if not isinstance(r.get("artis_gb"), (int, float)) or r["artis_gb"] <= 0:
                continue
            kayit.append({k: r.get(k) for k in
                          ("kosu", "cells", "artis_gb", "toplam_gb",
                           "cekirdek", "kb_hucre")})
    return kayit


def regresyon(kayit: list[dict]) -> dict | None:
    """artış_GB = a + b·hücre — b EĞİMİ katsayıdır, a sabit yüktür.

    ORAN (artış/hücre) YANLIŞ MODELDİR ve arşivin neden işe yaramadığını da
    açıklar: WSL2 VM'i, çözücü ikilileri ve decomposePar kopyaları hücre
    sayısından BAĞIMSIZ bir taban tüketir. Bu tabanı hücreye bölmek küçük
    koşularda katsayıyı şişirir --- ölçüldü: 18.462 hücrelik koşuda 9,75
    kB/hücre çıktı, 96.280 hücrelikte 1,66. Aynı geometri, aynı çözücü.
    Eğim bu tabanı ayırır ve geriye gerçekten hücreyle ölçeklenen kısım kalır.
    """
    if len(kayit) < 3:
        return None
    n = len(kayit)
    xs = [float(k["cells"]) for k in kayit]
    ys = [float(k["artis_gb"]) for k in kayit]
    xo, yo = sum(xs) / n, sum(ys) / n
    sxx = sum((x - xo) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b = sum((x - xo) * (y - yo) for x, y in zip(xs, ys)) / sxx
    a = yo - b * xo
    sst = sum((y - yo) ** 2 for y in ys)
    ssr = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ssr / sst if sst > 0 else 0.0
    return {"kb_hucre": round(b * 1e6, 4), "sabit_yuk_gb": round(a, 3),
            "r2": round(r2, 4), "n": n,
            "hucre_araligi": [int(min(xs)), int(max(xs))],
            "_model": "artis_gb = sabit_yuk_gb + (kb_hucre/1e6)·hucre"}


def olcum_kosulari() -> list[dict]:
    """Büyük koşular — arşiv gürültü altında kaldığı için ÖLÇÜM üretilir."""
    import shutil
    import time

    from vehicle_pipeline import run_vehicle_analysis
    stl = KOK / "vehicle_runs" / "gci_kup.stl"
    if not stl.exists():
        print(f"UYARI: {stl} yok — ölçüm koşusu atlandı", flush=True)
        return []
    calisma = KOK / "_bellek_olcum"
    out = []
    for butce in OLCUM_BUTCELERI:
        etiket = f"m{butce // 1000}k"
        kok = calisma / etiket
        if kok.exists():
            shutil.rmtree(kok, ignore_errors=True)
        kok.mkdir(parents=True, exist_ok=True)
        print(f"[{etiket}] bütçe {butce:,} hücre, {OLCUM_CEKIRDEK} çekirdek…",
              flush=True)
        t0 = time.time()
        r = run_vehicle_analysis(
            stl, vehicle_type="genel", velocity=10.0, alpha_deg=0.0,
            quality="standart", out_root=str(kok), n_processors=OLCUM_CEKIRDEK,
            max_cells=butce, ref_bump=0, mesh_sensitivity=False)
        mesh = getattr(r, "mesh", None) or {}
        bellek = getattr(r, "bellek", None) or {}
        kayit = {"kosu": f"olcum/{etiket}", "butce": butce,
                 "cells": mesh.get("cells"), "artis_gb": bellek.get("artis_gb"),
                 "toplam_gb": bellek.get("toplam_gb"),
                 "cekirdek": OLCUM_CEKIRDEK,
                 "durum": getattr(r, "status", "?"),
                 "duvar_s": round(time.time() - t0, 1)}
        if kayit["cells"] and isinstance(kayit["artis_gb"], (int, float)):
            kayit["kb_hucre"] = round(kayit["artis_gb"] * 1e6 / kayit["cells"], 3)
        out.append(kayit)
        print(f"    durum={kayit['durum']} hücre={kayit['cells']} "
              f"bellek+={kayit['artis_gb']} GB  ({kayit['duvar_s']} s)", flush=True)
        (KOK / "bellek_olcum_kismi.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def calistir(olc: bool = False) -> dict:
    kayit = topla()
    if olc:
        kayit += [k for k in olcum_kosulari() if k.get("kb_hucre")]
    rec = {
        "vaka": "Hücre başına bellek katsayısı — koşu arşivinden",
        "_neden": ("Bellek kapisinin ihtiyaci olan tek sayi. Literaturden alinan "
                   "tek bir deger bu makinede yanlis olur; cozucu artik kosu "
                   "boyunca sistem bellegini ornekliyor."),
        "kosular": kayit,
        "_kisit": ("WSL2 VM ayri bir surec olmadigi icin tek kosunun RSS'i "
                   "gorulemez; olculen, sistem geneli kullanimin kosu boyunca "
                   "ARTISIDIR. Makinede baska is varsa sayi yukari kayar — "
                   "yani bu bir UST SINIRDIR."),
        "_uretim": "Üretim: python experiments/bellek_katsayisi.py",
    }
    if not kayit:
        rec["verdikt"] = ("Bellek telemetrisi tasiyan kosu YOK — katsayi "
                          "OLCULEMEDI. bellek_kapisi ONCUL ile calisir ve bunu "
                          "her ciktisinda soyler. Telemetri bu surumde eklendi; "
                          "bundan sonraki kosular olcum uretir.")
        rec["kb_hucre"] = None
        return rec
    d = [k["kb_hucre"] for k in kayit]
    medyan = round(statistics.median(d), 3)
    sacilma = max(d) / min(d) if min(d) > 0 else float("inf")
    zayif = [k for k in kayit if k["artis_gb"] < EN_AZ_ARTIS_GB]
    rec["dagilim"] = {"min": min(d), "max": max(d), "medyan": medyan,
                      "sacilma_katı": round(sacilma, 1),
                      "gurultu_alti_kosu": len(zayif), "n_kosu": len(d)}
    # GURULTUYE KATSAYI DENMEZ. Sacilma buyukse ya da olculen artis gurultu
    # esiginin altindaysa medyan bir merkez DEGILDIR; sayi YAZILMAZ ve kapi
    # onculle calismaya devam eder. Bu, "elimizde veri var" diye gecersiz bir
    # sayi yayimlamaktan iyidir.
    # REGRESYON ONCE DENENIR. Medyan-oran modeli sabit yuku hucreye dagitir ve
    # kucuk kosularda katsayiyi sisirir; egim o tabani ayirir. Ancak egim de
    # ancak GENIS bir hucre araliginda ve iyi bir uyumla anlamlidir.
    # KONTROLLU SET VARSA YALNIZ O KULLANILIR ve "kontrollu" olmak icin ayni
    # cekirdek sayisi YETMEZ — ayni OTURUMDA, arka arkaya kosulmus olmak da
    # gerekir. Olculdu: ayni 18.462 hucrede 1 cekirdek 0.06 GB, 4 cekirdek
    # 0.18 GB (cekirdek decomposePar kopyalarini degistirir). Ama 4-cekirdek
    # arsiv kosulari da olcum kosulariyla tutarsiz: arsiv 96.280 hucrede
    # 0.16 GB derken olcum 76.989 hucrede 0.26 GB veriyor. Ayni cekirdek,
    # farkli oturum, farkli sistem yuku. Iki seti birlestirmek R^2'yi 0,96'dan
    # 0,87'ye dusuruyordu — yani karistirmanin bedeli OLCULDU.
    kontrollu = [k for k in kayit if str(k.get("kosu", "")).startswith("olcum/")]
    kume = kontrollu if len(kontrollu) >= 3 else kayit
    reg = regresyon(kume)
    if reg:
        reg["kume"] = ("kontrollü ölçüm koşuları — tek oturum, sıralı, sabit "
                       f"{OLCUM_CEKIRDEK} çekirdek"
                       if kume is kontrollu else
                       "TÜM arşiv — çekirdek ve oturum DEĞİŞKEN, eğim kirli olabilir")
        rec["regresyon"] = reg
        _aralik = reg["hucre_araligi"][1] / max(reg["hucre_araligi"][0], 1)
        if reg["r2"] >= EN_AZ_R2 and _aralik >= 4.0 and reg["kb_hucre"] > 0:
            rec["kb_hucre"] = reg["kb_hucre"]
            rec["n_kosu"] = reg["n"]
            # ARTISLARIN MUTLAK KUCUKLUGU SUSTURULMAZ. Regresyon uyumu
            # sinyalin gurultuden AYRILDIGINI gosterir (uc nokta ayni dogruda),
            # ama olculen artislar hâlâ gurultu esiginin civarindadir; bu,
            # katsayinin bir UST SINIR oldugunu unutturmamali.
            _en_buyuk = max(k["artis_gb"] for k in kume)
            _uyari = ("" if _en_buyuk >= EN_AZ_ARTIS_GB else
                      f" UYARI: en buyuk olculen artis {_en_buyuk} GB, gurultu "
                      f"esiginin ({EN_AZ_ARTIS_GB} GB) ALTINDA — uyum tutarli "
                      "oldugu icin egim kabul edildi, ama sayi bir UST SINIRDIR.")
            rec["_mutlak_artis_uyarisi"] = _uyari.strip() or None
            rec["verdikt"] = (
                f"{reg['n']} kosudan DOGRUSAL UYUM: {reg['kb_hucre']} kB/hucre "
                f"(egim) + {reg['sabit_yuk_gb']} GB sabit yuk, R^2={reg['r2']}, "
                f"hucre araligi {reg['hucre_araligi'][0]:,}-{reg['hucre_araligi'][1]:,} "
                f"({_aralik:.0f} kat, kume: {reg['kume']}). "
                f"Medyan-oran modeli ({medyan} kB/hucre) "
                "KULLANILMADI: sabit yuku hucreye dagitiyor ve kucuk kosularda "
                "katsayiyi sisiriyor. Bellek kapisi artik OLCULEN katsayiyla "
                "calisir." + _uyari)
            return rec
        rec["_regresyon_reddi"] = (
            f"Dogrusal uyum yetersiz: R^2={reg['r2']} (esik {EN_AZ_R2}), hucre "
            f"araligi {_aralik:.1f} kat (esik 4). Egim yazilmadi.")
    yeterli = sacilma <= EN_COK_SACILMA and len(zayif) < len(kayit)
    if not yeterli:
        rec["kb_hucre"] = None
        rec["n_kosu"] = len(d)
        rec["verdikt"] = (
            f"{len(d)} kosu var ama katsayi OLCULEMEDI: kB/hucre {min(d)}-{max(d)} "
            f"arasinda sacildi ({sacilma:.1f} kat, esik {EN_COK_SACILMA}) ve "
            f"{len(zayif)}/{len(kayit)} kosunun bellek artisi gurultu esiginin "
            f"({EN_AZ_ARTIS_GB} GB) altinda. Kucuk kosularda cozucunun kendi "
            "bellegi sistem geneli olcumun gurultusune gomuluyor. Medyani "
            "katsayi diye yazmak gurultuye katsayi demek olurdu — bellek kapisi "
            "ONCULLE calismaya devam ediyor.")
        return rec
    rec["kb_hucre"] = medyan
    rec["n_kosu"] = len(d)
    rec["verdikt"] = (f"{len(d)} kosudan medyan {medyan} kB/hucre "
                      f"(min {min(d)}, max {max(d)}, sacilma {sacilma:.1f} kat). "
                      "Bellek kapisi artik OLCULEN katsayiyla calisir.")
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir(olc="--olc" in sys.argv[1:])
    (KOK / "bellek_katsayisi.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    for k in rec["kosular"]:
        print(f"  {k['kosu']:<26}{k['cells']:>10,} hücre  "
              f"{k['artis_gb']:>6.2f} GB  →  {k['kb_hucre']:>6.3f} kB/hücre")
    print("\n" + rec["verdikt"])
    print("-> bellek_katsayisi.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
