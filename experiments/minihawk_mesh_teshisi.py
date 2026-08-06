"""MiniHawk RANS'i neden savunulamaz — KÖK NEDEN, meshin LOGLARINDAN.

Δ_entegrasyon üç kapıya takıldı (GCI %379, y⁺ 5399, Cl uyuşmazlığı). Üçü de
BELİRTİ. Kök neden, koşunun kendi loglarında duruyor: araç yüzeyi mesh'te
neredeyse YOK.

    seviye      taban hücre    ARAÇ YÜZEY YÜZÜ
    çokkaba          50.880    (patch yok)
    kaba            165.440              8
    orta            549.780            144
    ince          3.943.350             74

En ince seviye, ortadan 7 KAT fazla taban hücreyle DAHA AZ yüzey yüzü veriyor.
Bu bir iyileştirme ailesi değildir; 8 yüzle temsil edilen bir uçağın Cd'si sayı
değildir. Boru hattının kendi eşiği ≥500 yüz (YUZEY_YUZ_ESIGI) — dört seviyenin
DÖRDÜ de bunun altında.

NEDEN: alan (-10.38,-11.25,-10.54)–(27.82,11.25,10.54) = 38.2×22.5×21.1 m, yani
1.5 m açıklıklı bir uçak için ~17.955 m³. Arka plan mesh'i bu hacme DÜZGÜN
seriliyor; en ince seviyede 3.94M taban hücre demek 0.164 m hücre demek. Hücre
bütçesi (maxGlobalCells) arka planda tükeniyor ve snappyHexMesh yüzeyi
inceltemiyor.

MAKİNE DEĞİL, DAĞITIM SORUNU: gövde çevresine hedefli bir refinement KUTUSU
konsaydı aynı bütçeyle yüzey çözülebilirdi. `CFDCase.refinement_regions` zaten
var ama araç yolu HİÇ KULLANMIYOR (varsayılan None).

    python experiments/minihawk_mesh_teshisi.py
Çıktı: minihawk_mesh_teshisi.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

KOSU = KOK / "vehicle_runs" / "minihawk"
SEVIYELER = ("minihawk_cokkaba", "minihawk_kaba", "minihawk_orta", "minihawk")
YAMA = "minihawk_prep"


def _log_oku(dizin: Path) -> dict:
    kayit: dict = {"ad": dizin.name}
    cm = dizin / "log.checkMesh"
    bm = dizin / "log.blockMesh"
    if bm.exists():
        m = re.search(r"nCells:\s*(\d+)", bm.read_text(errors="ignore"))
        if m:
            kayit["taban_hucre"] = int(m.group(1))
    if cm.exists():
        t = cm.read_text(errors="ignore")
        m = re.search(rf"^\s*{YAMA}\s+(\d+)\s+(\d+)", t, re.M)
        kayit["yuzey_yuz"] = int(m.group(1)) if m else None
        b = re.search(r"Overall domain bounding box \(([-\d.eE ]+)\) \(([-\d.eE ]+)\)", t)
        if b:
            mn = [float(x) for x in b.group(1).split()]
            mx = [float(x) for x in b.group(2).split()]
            kayit["alan_boyut_m"] = [round(a - b_, 3) for a, b_ in zip(mx, mn)]
    return kayit


def calistir() -> dict:
    from analysis.openfoam_runner import YUZEY_YUZ_ESIGI
    kayitlar = [_log_oku(KOSU / s) for s in SEVIYELER if (KOSU / s).is_dir()]
    if not kayitlar:
        return {"vaka": "MiniHawk mesh teshisi", "durum": "KOSU DIZINI YOK",
                "verdikt": f"⚠️ {KOSU} bulunamadi — teshis LOGLARDAN uretilir."}

    yuzler = [(k["ad"], k.get("yuzey_yuz")) for k in kayitlar]
    olculen = [y for _, y in yuzler if y]
    esik_alti = [ad for ad, y in yuzler if y is None or y < YUZEY_YUZ_ESIGI]
    # AILE MONOTON MU: hucre artarken yuzey yuzu de artmali. Artmıyorsa
    # kademeler AYNI geometrinin farkli cozunurlukleri DEGILDIR.
    sirali = [y for _, y in yuzler if y]
    monoton = all(a <= b for a, b in zip(sirali, sirali[1:]))

    alan = next((k.get("alan_boyut_m") for k in kayitlar if k.get("alan_boyut_m")), None)
    hacim = (alan[0] * alan[1] * alan[2]) if alan else None
    en_ince = max((k for k in kayitlar if k.get("taban_hucre")),
                  key=lambda k: k["taban_hucre"], default=None)
    bg_hucre = ((hacim / en_ince["taban_hucre"]) ** (1 / 3)
                if hacim and en_ince else None)

    rec = {
        "vaka": "MiniHawk RANS — mesh kok-neden teshisi (kosunun kendi loglarindan)",
        "_neden": ("Delta_entegrasyon uc kapiya takildi (GCI %379, y+ 5399, Cl "
                   "uyusmazligi). Ucu de BELIRTI; kok neden meshte."),
        "kosu": str(KOSU),
        "seviyeler": kayitlar,
        "yuzey_yuz_esigi": YUZEY_YUZ_ESIGI,
        "esik_altinda_seviyeler": esik_alti,
        "yuzey_yuz_monoton": monoton,
        "alan_boyut_m": alan,
        "alan_hacim_m3": round(hacim, 1) if hacim else None,
        "en_ince_taban_hucre": en_ince.get("taban_hucre") if en_ince else None,
        "arka_plan_hucre_m": round(bg_hucre, 4) if bg_hucre else None,
        "_kok_neden": (
            "Arka plan mesh'i tum alana DUZGUN seriliyor. Alan 1.5 m acikliktaki "
            "bir ucak icin ~17.955 m3; en ince seviyede 3.94M taban hucre = "
            "0.164 m hucre. Hucre butcesi (maxGlobalCells) arka planda tukeniyor "
            "ve snappyHexMesh yuzeyi inceltemiyor. MAKINE DEGIL, DAGITIM sorunu: "
            "govde cevresine hedefli refinement KUTUSU konsaydi ayni butceyle "
            "yuzey cozulurdu. `CFDCase.refinement_regions` ZATEN VAR ama arac "
            "yolu hic kullanmiyor (varsayilan None)."),
        "_kisit": ("Bu teshis MESH loglarindan uretildi; polyMesh diskte yok "
                   "(temizlikte silindi). Yuzey yuz sayilari checkMesh'in patch "
                   "tablosundan, taban hucre blockMesh'ten okundu. Cozucu "
                   "sonuclari (Cd/Cl) YENIDEN HESAPLANMADI — bu dosya onlarin "
                   "NEDEN kullanilamaz oldugunu soyler, yerlerine sayi koymaz."),
        "_uretim": "Üretim: python experiments/minihawk_mesh_teshisi.py",
    }
    rec["verdikt"] = (
        "⛔ ARAC YUZEYI MESH'TE YOK: yuzey yuzleri "
        + ", ".join(f"{ad}={y}" for ad, y in yuzler)
        + f" — esik {YUZEY_YUZ_ESIGI}. "
        + ("Dizi MONOTON DEGIL: en ince seviye ortadan DAHA AZ yuzey yuzu "
           "veriyor, yani kademeler ayni geometrinin farkli cozunurlukleri "
           "DEGIL. " if not monoton else "")
        + f"En kotu {min(olculen) if olculen else 0} yuz. Bu kademelerden gelen "
          "Cd/Cl sayi degildir; GCI %379 ve y+ 5399 bunun SONUCUDUR, sebebi degil.")
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "minihawk_mesh_teshisi.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    if "seviyeler" in rec:
        print(f"{'seviye':>20} {'taban hucre':>13} {'yuzey yuz':>10}")
        for k in rec["seviyeler"]:
            # None DA BASILIR: "yama yok" ile "0 yuz" ayni sey degil, ikisi de
            # gorunmeli.
            print(f"{k['ad']:>20} {str(k.get('taban_hucre') or '-'):>13} "
                  f"{str(k.get('yuzey_yuz') if k.get('yuzey_yuz') is not None else 'YAMA YOK'):>10}")
        print(f"\nalan {rec['alan_boyut_m']} m = {rec['alan_hacim_m3']} m³, "
              f"arka plan hucresi ~{rec['arka_plan_hucre_m']} m")
    print("\n" + rec["verdikt"])
    if "_kok_neden" in rec:
        print("\nKOK NEDEN: " + rec["_kok_neden"])
    print("-> minihawk_mesh_teshisi.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
