"""Başarım matrisi — hücre × çekirdek, ÖLÇÜLEN süre ve bellek.

NEDEN: rapordaki tek başarım verisi tek bir koşudan gelen aşama dağılımıydı.
"Ne kadar sürer?" ve "bu makinede kaç hücre kaldırır?" sorularının cevabı yoktu.
Aşama telemetrisi ve bellek örneklemesi eklendiğine göre ikisi de ölçülebilir.

BU BİR KIYASLAMA (benchmark) DEĞİLDİR: tek makine, tek çözücü ayarı. Ölçülen
şey bu platformun bu donanımdaki ÖLÇEKLENME EĞİLİMİDİR; başka bir makinede
sayılar değişir. Amaç mutlak hız iddiası değil, planlama için taban vermek ve
bellek katsayısını ölçüme bağlamak.

GEOMETRİ KISITI (2026-08-11): matris ilk sürümde TEK geometriyle (küp)
ölçülmüştü ve rapor bunu sınır olarak yazıyordu. Küp, snappyHexMesh'e yüzey
işi neredeyse hiç vermez (12 üçgen); ölçülen ölçeklenme eğrisinin gerçek bir
gövdede aynı kalıp kalmadığı BİLİNMİYORDU. `--geometri` ile ikinci bir gövde
(MiniHawk) aynı matriste koşulur ve eğilim karşılaştırılabilir. Tek makine
kısıtı DEVAM EDER --- ikinci donanım yok, bu sınır kapatılmadı.

TASARIM: koşular SIRAYLA yapılır. Paralel koşmak çekirdek ve bellek-bant
rekabeti yaratır ve tam da ölçmek istediğimiz şeyi bozar.

    python experiments/basarim_matrisi.py                    # küp (varsayılan)
    python experiments/basarim_matrisi.py --geometri minihawk
    python experiments/basarim_matrisi.py --hizli            # tek satır (duman)
Çıktı: basarim_matrisi.json  /  basarim_matrisi_<geometri>.json
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

GEOMETRILER = {
    "kup": KOK / "vehicle_runs" / "gci_kup.stl",
    "minihawk": KOK / "vehicle_runs" / "minihawk.stl",
}
STL = GEOMETRILER["kup"]
CIKTI = KOK / "basarim_matrisi.json"
CALISMA = KOK / "_basarim"

HUCRE_BUTCELERI = (60_000, 150_000, 350_000)
CEKIRDEKLER = (1, 4, 8)


def _cozucu_exec_s(kok: Path) -> float | None:
    """foamRun'un KENDİ bildirdiği ExecutionTime — aşama duvar süresi değil.

    NEDEN AYRI ÖLÇÜLÜR: aşama süresi WSL süreç başlatma, ortam kurulumu ve
    `mpirun` açılışını içerir ve bu yük hücre sayısından BAĞIMSIZDIR (~8-10 s).
    Küçük ağlarda o sabit yük çözüm süresini gölgeler; ondan hesaplanan
    "hızlanma" paralelliği değil, sabit yükün seyrelmesini ölçer. İlk sürüm
    tam bu hatayı yapmıştı (2026-08-11 düzeltmesi).
    """
    en_son = None
    for log in kok.rglob("log.foamRun"):
        for satir in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if satir.startswith("ExecutionTime = "):
                try:
                    en_son = float(satir.split("=")[1].split("s")[0])
                # sessiz-yutma: kabul — bozuk log satırı atlanır; okunabilen SON
                # ExecutionTime yine döner, hiç okunamazsa fonksiyon None verir
                # ve hızlanma hesabı o koşuyu DIŞARIDA bırakır (uydurma yok).
                except (ValueError, IndexError):
                    pass
    return round(en_son, 2) if en_son is not None else None


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
        "cozucu_exec_s": _cozucu_exec_s(kok),
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
              f"duvar={s['duvar_s']}s aşama={s['cozucu_s']}s "
              f"exec={s['cozucu_exec_s']}s "
              f"bellek+={(s['bellek'] or {}).get('artis_gb')}GB", flush=True)
        (CIKTI.with_name(CIKTI.stem + "_kismi.json")).write_text(
            json.dumps(satirlar, indent=2, ensure_ascii=False), encoding="utf-8")

    ok = [s for s in satirlar if s["durum"] == "ok" and s["cells"]]
    rec = {
        "vaka": f"Başarım matrisi — hücre × çekirdek ({STL.stem}, tek makine)",
        "_neden": ("Rapordaki tek basarim verisi TEK kosudan gelen asama "
                   "dagilimiydi; 'ne kadar surer' ve 'kac hucre kaldirir' "
                   "sorularinin olculmus cevabi yoktu."),
        "kurulum": {"geometri": STL.name, "tip": "genel", "hiz_m_s": 10.0,
                    "kalite": "standart", "butceler": list(HUCRE_BUTCELERI),
                    "cekirdekler": list(CEKIRDEKLER),
                    "sirali": "koşular SIRAYLA — paralel koşu ölçümü bozar"},
        "satirlar": satirlar,
        "_kisit": ("KIYASLAMA DEGILDIR: TEK MAKINE, tek cozucu ayari. Bellek "
                   "olcumu sistem GENELIDIR (WSL2 VM ayri surec degil) ve kosu "
                   "oncesi tabana gore artistir — yani UST SINIR. Geometri "
                   "kisiti ayrica olculdu (bkz. basarim_geometri_bagimliligi)."),
        "_uretim": (f"Üretim: python experiments/basarim_matrisi.py "
                    f"--geometri {STL.stem.replace('gci_', '')}"),
    }
    if ok:
        rec["olcek"] = _olcekleme(ok)
        rec["verdikt"] = rec["olcek"]["ozet"]
    else:
        rec["verdikt"] = "Hicbir kosu tamamlanmadi — matris URETILEMEDI."
    return rec


def _olcekleme(ok: list[dict]) -> dict:
    """Çekirdek ölçeklenmesi ve hücre başına maliyet — ölçülenden.

    İKİ hızlanma birden verilir ve karıştırılmaz:
      `cekirdek_hizlanmasi`      — aşama duvar süresinden; KULLANICININ gördüğü
      `cekirdek_hizlanmasi_exec` — foamRun ExecutionTime'dan; PARALELLİĞİN kendisi
    """
    out: dict = {"cekirdek_hizlanmasi": {}, "cekirdek_hizlanmasi_exec": {},
                 "hucre_basina_ms": {}}
    for b in sorted({s["butce"] for s in ok}):
        grup = sorted((s for s in ok if s["butce"] == b), key=lambda s: s["cekirdek"])
        taban = next((s for s in grup if s["cekirdek"] == 1), None)
        if taban and taban["cozucu_s"]:
            out["cekirdek_hizlanmasi"][f"{b // 1000}k"] = {
                str(s["cekirdek"]): round(taban["cozucu_s"] / s["cozucu_s"], 2)
                for s in grup if s["cozucu_s"]}
        if taban and taban.get("cozucu_exec_s"):
            out["cekirdek_hizlanmasi_exec"][f"{b // 1000}k"] = {
                str(s["cekirdek"]): round(taban["cozucu_exec_s"] / s["cozucu_exec_s"], 2)
                for s in grup if s.get("cozucu_exec_s")}
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
    global STL, CIKTI, CALISMA
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--geometri" in sys.argv:
        ad = sys.argv[sys.argv.index("--geometri") + 1]
        if ad not in GEOMETRILER:
            print(f"bilinmeyen geometri: {ad} — {list(GEOMETRILER)}")
            return 1
        STL = GEOMETRILER[ad]
        if not STL.exists():
            print(f"STL yok: {STL}")
            return 1
        if ad != "kup":
            CIKTI = KOK / f"basarim_matrisi_{ad}.json"
            CALISMA = KOK / f"_basarim_{ad}"
    rec = calistir(hizli="--hizli" in sys.argv)
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print("\n" + rec["verdikt"])
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
