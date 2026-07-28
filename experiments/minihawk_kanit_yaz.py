"""MiniHawk kampanya sonucunu KANIT dosyasına çevirir (elle düzenleme yerine).

`gci_minihawk_arac.json` bugüne dek ELLE yazılmıştı: vehicle_pipeline sonucu
`vehicle_runs/<ad>/sonuc.json` içine koyar, kök dizindeki kanıt dosyasını kimse
üretmezdi. `kanit.py --eksik` bu sınıfı "ÜRETİCİ KOD DEPODA YOK — yeniden üretilemez"
diye işaretliyor; bu script o boşluğu kapatır.

    python vehicle_pipeline.py vehicle_runs/minihawk.stl --tip ucak --hiz 15 \
        --kalite standart --duyarlilik --seviyeler 4
    python experiments/minihawk_kanit_yaz.py

Çıktı: gci_minihawk_arac.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

KOSU = HERE.parent / "vehicle_runs" / "minihawk" / "sonuc.json"
KANIT = HERE.parent / "gci_minihawk_arac.json"
KOMUT = ("python vehicle_pipeline.py vehicle_runs/minihawk.stl --tip ucak --hiz 15 "
         "--kalite standart --duyarlilik --seviyeler 4 && "
         "python experiments/minihawk_kanit_yaz.py")


def _verdikt(md: dict, yp: dict | None, cl: float | None) -> str:
    p = []
    g = md.get("gci") or {}
    if g.get("gci_fine_pct", 1e9) < 5 and g.get("monotonic") and g.get("p_in_range"):
        p.append(f"Mesh bagimsizligi GOSTERILDI (GCI %{g['gci_fine_pct']:.2f})")
    else:
        p.append(f"⚠️ Mesh bagimsizligi GOSTERILEMEDI: GCI %{g.get('gci_fine_pct', 0):.0f}"
                 + ("" if g.get("monotonic") else ", seri MONOTON DEGIL"))
    if md.get("fizik_disi_seviyeler"):
        s = md["fizik_disi_seviyeler"][0]
        p.append(f"en kaba seviye ({s['cells']:,} hucre) FIZIK KAPISINDA reddedildi: "
                 f"{s['gerekce']}")
    if yp and yp.get("ort"):
        p.append(f"olculen y+ ortalama {yp['ort']:.0f} (hedef bandi 30-300) — duz levha "
                 "capasinda ilk hucre sinir tabakayi yuttugunda cilt surtunmesi %40 "
                 "eksik olculmustu; burada y+ daha da yuksek, SURTUNME COZULMUYOR")
    if cl is not None:
        p.append(f"Cl={cl:.4f} oysa NACA2412 alpha=0'da 2B beklenti ~0.25 — KAMBURLUK "
                 "hala cozulmuyor (geometri artik dogru; sinir mesh cozunurlugunde)")
    return ". ".join(p) + "."


def main() -> int:
    if not KOSU.exists():
        print(f"{KOSU} yok — once kampanyayi kosun:\n  {KOMUT.split(' && ')[0]}")
        return 1
    d = json.loads(KOSU.read_text(encoding="utf-8"))
    md = d.get("mesh_duyarlilik") or {}
    if not md.get("seviyeler"):
        print("sonuc.json'da mesh_duyarlilik yok — --duyarlilik ile kosuldu mu?")
        return 1
    yp = d.get("sinir_tabaka", {}).get("yplus") or d.get("yplus")
    if yp and yp.get("olculemedi"):
        yp = {"olculemedi": True, "neden": yp.get("neden")}

    out = {
        "vaka": ("MiniHawk UAV (govde 0.8 m, kanat 1.5 m) — arac hatti 4-seviye mesh "
                 "yakinsama, V=15 m/s, alpha=0"),
        "_geometri": ("2026-07-28: SU GECIRMEZ ve GERCEK NACA2412 kanatli STL "
                      "(shapely + mapbox_earcut + manifold3d kurulduktan sonra). Onceki "
                      "kampanyalar kanadi DUZ KUTU olan ve govdeleri BIRLESMEMIS bir STL "
                      "uzerinde kosulmustu — gci_minihawk_arac.ONCEKI_GECERSIZ.json"),
        "Cd": d.get("cd"), "Cl": d.get("cl"),
        "aref_m2": d.get("aref_m2"), "aref_mode": d.get("aref_mode"),
        "seviyeler": md["seviyeler"], "gci": md.get("gci"),
        "fizik_disi_seviyeler": md.get("fizik_disi_seviyeler"),
        "basarisiz_seviyeler": md.get("basarisiz_seviyeler"),
        "yplus": yp, "convergence": d.get("convergence"),
        "verdikt": _verdikt(md, yp, d.get("cl")),
        "_uretim": f"Üretim: {KOMUT}",
    }
    KANIT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out["verdikt"])
    print("->", KANIT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
