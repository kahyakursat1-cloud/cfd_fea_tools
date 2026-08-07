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

from validity_envelope import YPLUS_BANDI  # noqa: E402

KOSU = HERE.parent / "vehicle_runs" / "minihawk" / "sonuc.json"
KANIT = HERE.parent / "gci_minihawk_arac.json"
KOMUT = ("python vehicle_pipeline.py vehicle_runs/minihawk.stl --tip ucak --hiz 15 "
         "--kalite standart --duyarlilik --seviyeler 4 && "
         "python experiments/minihawk_kanit_yaz.py")


def _verdikt(md: dict, yp: dict | None, cl: float | None,
             band_yok: str | None = None, yuzey: dict | None = None) -> str:
    p = []
    g = md.get("gci") or {}
    if band_yok:
        p.append(f"⚠️ Mesh bagimsizlik BANDI YOK — {band_yok}")
    elif g.get("gci_fine_pct", 1e9) < 5 and g.get("monotonic") and g.get("p_in_range"):
        p.append(f"Mesh bagimsizligi GOSTERILDI (GCI %{g['gci_fine_pct']:.2f})")
    else:
        p.append(f"⚠️ Mesh bagimsizligi GOSTERILEMEDI: GCI %{g.get('gci_fine_pct', 0):.0f}"
                 + ("" if g.get("monotonic") else ", seri MONOTON DEGIL"))
    if yuzey and yuzey.get("yuzey_yuz"):
        p.append(f"govde yuzeyi {yuzey['yuzey_yuz']:,} yuz ile cozuldu"
                 if yuzey.get("cozuldu") else
                 f"govde yuzeyi YALNIZ {yuzey['yuzey_yuz']:,} yuz")
    if md.get("fizik_disi_seviyeler"):
        s = md["fizik_disi_seviyeler"][0]
        p.append(f"en kaba seviye ({s['cells']:,} hucre) FIZIK KAPISINDA reddedildi: "
                 f"{s['gerekce']}")
    # Y+ METNI OLCUMDEN TURETILIR, SABIT YAZILMAZ. Eski surum her kosuda
    # "y+ daha da yuksek, SURTUNME COZULMUYOR" diyordu; ref_bump duzeltmesinden
    # sonra y+ 5399 -> 129'a indi ve o cumle veriyle CELISIR hale geldi.
    if yp and yp.get("ort"):
        _o = yp["ort"]
        if YPLUS_BANDI[0] <= _o <= YPLUS_BANDI[1]:
            p.append(f"olculen y+ ortalama {_o:.0f} — duvar-fonksiyonu bandi "
                     f"({YPLUS_BANDI[0]:.0f}-{YPLUS_BANDI[1]:.0f}) ICINDE"
                     + (f", ancak yerel max {yp['max']:.0f} bandin ustunde"
                        if yp.get("max", 0) > YPLUS_BANDI[1] else ""))
        else:
            p.append(f"olculen y+ ortalama {_o:.0f} (hedef bandi "
                     f"{YPLUS_BANDI[0]:.0f}-{YPLUS_BANDI[1]:.0f}) — duz levha "
                     "capasinda ilk hucre sinir tabakayi yuttugunda cilt "
                     "surtunmesi %40 eksik olculmustu; SURTUNME COZULMUYOR")
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
    # BAND YOKSA DA KAYIT YAZILIR. Eski surum burada RET verip cikiyordu ve
    # sonuc: depoda GECERSIZ eski kayit DURUYORDU, tuketiciler (delta_entegrasyon)
    # onu okumaya devam ediyordu. Bandsiz ama GUNCEL bir kayit, bandli ama
    # gecersiz bir kayittan iyidir — yeter ki bandin YOKLUGU ve NEDENI yazili olsun.
    band_yok = None
    if not md.get("seviyeler"):
        band_yok = md.get("durum") or ("mesh_duyarlilik yok — --duyarlilik ile "
                                       "kosulmamis olabilir")
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
        "seviyeler": md.get("seviyeler"), "gci": md.get("gci"),
        "band_yok_nedeni": band_yok,
        # KOSU AYARI VE YUZEY COZUNURLUGU KAYDA GECER: bandin yoklugu kadar,
        # govdenin mesh'te GERCEKTEN temsil edilip edilmedigi de tuketiciyi
        # ilgilendirir (eski kayit 74 yuzle uretilmisti).
        "yuzey_cozunurlugu": (d.get("sinir_tabaka") or {}).get("yuzey_cozunurlugu"),
        "ref_bump": ((d.get("sinir_tabaka") or {}).get("ref_bump_onerisi") or {}
                     ).get("kullanilan"),
        "hucre": (d.get("mesh") or {}).get("cells"),
        "belirsizlik": d.get("belirsizlik"),
        "fizik_disi_seviyeler": md.get("fizik_disi_seviyeler"),
        "basarisiz_seviyeler": md.get("basarisiz_seviyeler"),
        "yplus": yp, "convergence": d.get("convergence"),
        "verdikt": _verdikt(md, yp, d.get("cl"), band_yok,
                            (d.get("sinir_tabaka") or {}).get("yuzey_cozunurlugu")),
        "_uretim": f"Üretim: {KOMUT}",
    }
    KANIT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out["verdikt"])
    print("->", KANIT.name)
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
