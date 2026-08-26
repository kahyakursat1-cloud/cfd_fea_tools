"""Deforme yüzeyde eşleme: SABİT mi, her tur YENİDEN mi? — ölçülen kayma.

2-YÖNLÜ FSI'DA TEŞHİS EDİLEN KUSUR (`_fsi_esnek`, üç tur):

    tur 1   F_z(FEA) 0,6615 N   F_z(CFD) 0,6058 N   aktarım artığı %8,4
    tur 2   F_z(FEA) 0,4405 N   F_z(CFD) 0,6065 N   aktarım artığı %27,4

FEA'ya giden kuvvet %33 değişti, CFD yüzeyindeki kuvvet %0,1. Bu aeroelastik
geri besleme DEĞİLDİR; deforme CFD yüzeyi ile referans konumda kalan FEA
yüzeyi arasındaki eşlemenin bozulmasıdır.

BU ÇALIŞMA O BOZULMAYI NİCELİKSEL OLARAK ÖLÇER. Yöntem: aynı basınç alanı,
aynı CFD yüzeyi; FEA düğümleri konsol benzeri bir sehimle deforme ediliyor ve
düğüm kuvveti dağılımı iki yolla hesaplanıyor ---

  SABİT   : eşleme REFERANS konfigürasyonda kurulur, ağırlıklar taşınır
            (malzeme koordinatı; bir CFD yüzü hep AYNI malzeme noktasına)
  YENİDEN : her turda deforme geometride en-yakın-komşu + baryentrik yeniden

TOPLAM KUVVET İKİSİNİ DE AYIRT ETMEZ ve bu ölçülerek görüldü: korunumlu
şemada ağırlıklar 1'e toplandığı için toplam kuvvet HANGİ üçgen seçilirse
seçilsin korunur (ikisi de %0,0000). Ayırt eden nicelik yükün NEREYE
bindiğidir --- düğüm dağılımı.

    python experiments/fsi_deforme_esleme.py
Çıktı: fsi_deforme_esleme.json
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

CIKTI = KOK / "fsi_deforme_esleme.json"
# Konsol ucu sehimleri [mm] — kucukten buyuge, kaymanin DOYUP doymadigi gorunsun
SEHIMLER_MM = (1.0, 5.0, 20.0, 50.0)


def _vaka_verisi(vtk: str, stl: str):
    import numpy as np
    import trimesh

    from coupling_fsi import _parse_legacy_vtk, _poly_geometry
    from fsi_korunumlu_esleme import disa_yonlendir

    pts, polys, p_cell, p_loc = _parse_legacy_vtk(Path(vtk))
    p_poly = (np.array([p_cell[list(q)].mean() for q in polys])
              if (p_loc == "POINT" or len(p_cell) == len(pts)) else p_cell)
    merkez, normal, alan = _poly_geometry(pts, polys)
    m = trimesh.load(stl, force="mesh")
    trimesh.repair.fix_normals(m)
    dugum = np.asarray(m.vertices, float)
    faces = np.asarray(m.faces)
    fc = np.asarray(m.triangles_center, float)
    normal, _ = disa_yonlendir(merkez, normal, fc,
                               np.asarray(m.face_normals, float))
    dF = (-np.asarray(p_poly, float) * 1.225)[:, None] * normal * alan[:, None]
    return merkez, dF, dugum, faces, fc


def olc_vaka(vtk: str, stl: str) -> dict:
    import numpy as np

    from fsi_korunumlu_esleme import esleme_kur, esleme_uygula

    merkez, dF, dugum, faces, fc = _vaka_verisi(vtk, stl)
    esleme = esleme_kur(merkez, dugum, faces, fc)
    F0 = esleme_uygula(esleme, dF, dugum)
    n0 = float(np.linalg.norm(F0)) + 1e-30
    F_cfd = dF.sum(axis=0)
    olcek = float(np.linalg.norm(dF, axis=1).sum()) + 1e-30

    # Konsol benzeri sehim: gomulu uctan uca kadar KARESEL artan.
    x = dugum[:, 0]
    s = (x - x.min()) / (x.max() - x.min() + 1e-30)
    adimlar = []
    for mm in SEHIMLER_MM:
        yeni = dugum.copy()
        yeni[:, 2] += s ** 2 * mm * 1e-3
        sabit = esleme_uygula(esleme, dF, yeni)
        yfc = yeni[faces].mean(axis=1)
        e2 = esleme_kur(merkez, yeni, faces, yfc)
        yeniden = esleme_uygula(e2, dF, yeni)
        adimlar.append({
            "sehim_mm": mm,
            "sabit_dugum_kaymasi_pct": round(
                100.0 * float(np.linalg.norm(sabit - F0)) / n0, 4),
            "yeniden_dugum_kaymasi_pct": round(
                100.0 * float(np.linalg.norm(yeniden - F0)) / n0, 4),
            "ucgen_atamasi_degisen": int(
                (e2["ucgen"] != esleme["ucgen"]).any(axis=1).sum()),
            # TOPLAM KUVVET IKISINDE DE KORUNUR — ayirt etmez, ama YAZILIR ki
            # "olculdu ve ayirt etmedi" ile "olculmedi" karismasin.
            "sabit_toplam_kuvvet_hatasi_pct": round(
                100.0 * float(np.linalg.norm(sabit.sum(axis=0) - F_cfd)) / olcek, 6),
            "yeniden_toplam_kuvvet_hatasi_pct": round(
                100.0 * float(np.linalg.norm(yeniden.sum(axis=0) - F_cfd)) / olcek, 6),
        })
    return {"n_cfd_yuz": esleme["n_cfd_yuz"],
            "n_fea_dugum": esleme["n_fea_dugum"], "adimlar": adimlar}


def olc() -> dict:
    from fsi_korunum import _vakalar

    t0 = time.time()
    kayit, dusen = [], []
    for v in _vakalar():
        try:
            r = olc_vaka(v["vtk"], v["stl"])
        except Exception as e:          # noqa: BLE001 — sebep KAYDEDILIYOR
            dusen.append(f"{v['ad']}: {type(e).__name__}: {e}"[:160])
            continue
        kayit.append({"vaka": v["ad"], **r})
        en = max(a["yeniden_dugum_kaymasi_pct"] for a in r["adimlar"])
        print(f"  {v['ad'][:26]:28s} yeniden-arama kayması en çok %{en:.2f}",
              flush=True)
    return _ozetle(kayit, dusen, time.time() - t0)


def _ozetle(kayit: list[dict], dusen: list[str], sure_s: float) -> dict:
    if not kayit:
        return {"vaka": "FSI deforme eşleme", "verdikt": "ÖLÇÜLEMEDİ",
                "dusen": dusen,
                "_uretim": "Üretim: python experiments/fsi_deforme_esleme.py"}
    y_max = max(a["yeniden_dugum_kaymasi_pct"]
                for k in kayit for a in k["adimlar"])
    s_max = max(a["sabit_dugum_kaymasi_pct"]
                for k in kayit for a in k["adimlar"])
    kuv = max(max(a["sabit_toplam_kuvvet_hatasi_pct"],
                  a["yeniden_toplam_kuvvet_hatasi_pct"])
              for k in kayit for a in k["adimlar"])
    return {
        "vaka": "FSI deforme yüzeyde eşleme — SABİT vs her tur YENİDEN",
        "_neden": ("2-yonlu FSI'da FEA'ya giden kuvvet %33 degisirken CFD "
                   "yuzeyindeki %0,1 degisiyordu. Bu aeroelastik geri besleme "
                   "degil, eslemenin bozulmasi."),
        "olculen_vaka": len(kayit), "dusen": dusen,
        "sehimler_mm": list(SEHIMLER_MM), "vakalar": kayit,
        "ozet": {"sabit_kayma_en_kotu_pct": s_max,
                 "yeniden_kayma_en_kotu_pct": y_max,
                 "toplam_kuvvet_hatasi_en_kotu_pct": kuv},
        "verdikt": (
            f"{len(kayit)} vakada ölçüldü. Her turda yeniden arama, düğüm "
            f"yükünün en çok %{y_max:.2f}'ini YALNIZCA deformasyondan "
            f"dolayı yeniden dağıtıyor; sabit eşlemede kayma %{s_max:.4f}. "
            f"TOPLAM KUVVET İKİSİNİ DE AYIRT ETMİYOR (en kötü "
            f"%{kuv:.4f}) --- korunumlu şemada ağırlıklar 1'e toplandığı "
            f"için toplam, hangi üçgen seçilirse seçilsin korunur. Ayırt eden "
            f"nicelik yükün NEREYE bindiğidir. Üçgen ataması değişmese bile "
            f"kayma oluşuyor: baryentrik ağırlıklar DEFORME üçgene göre "
            f"yeniden hesaplanıyor."),
        "sure_dk": round(sure_s / 60, 1),
        "_kisit": (
            "TEK TARAF DEFORME EDILDI: FEA dugumleri hareket ediyor, CFD yuzu "
            "referansta kaliyor. Gercek dongude CFD yuzu de hareket eder --- "
            "ve sabit eslemenin DOGRU olmasinin sebebi tam budur: iki tarafin "
            "AYNI MALZEME NOKTASINDA kalmasi gerekir. Sehim profili konsol "
            "benzeri KARESEL secildi; baska bir profil baska bir kayma verir "
            "ve bu sayi bir MERTEBE gostergesidir, evrensel bir sabit degil."),
        "_uretim": "Üretim: python experiments/fsi_deforme_esleme.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
