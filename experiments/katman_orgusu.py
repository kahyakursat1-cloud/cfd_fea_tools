"""Katman örgüsü: kalite ölçütünü gevşetmek katmanları GERÇEKTEN örüyor mu?

VAKA (ölçüldü 2026-08-19, küre çapası): 10 katman istendi, ortalama **0,535**
örüldü — hedef kalınlığın %13,9'u. Ekstrüzyon 1360'tan 600'e çürüdü (1728
yüzün yalnız %34,7'si). log.snappyHexMesh her yinelemede aynı satırı yazıyordu:

    faces with face-decomposition tet quality < 1e-15      : 472

Yani katman eklenince tet-ayrışım ölçütü düşüyor ve snappy katmanı SİLİYOR.
İkinci eksik: `relaxed` alt-sözlüğü hiç yoktu, dolayısıyla snappy ölçütü
gevşetip yeniden deneyemiyordu — elindeki tek seçenek katmanı atmaktı.

KONTROLLÜ DENEY
---------------
Arşivlenmiş küre vakası KOPYALANIR ve snappyHexMeshDict'te YALNIZ üç satır
değişir (minTetQuality, relaxed bloğu, nRelaxedIter). Geometri, alan, iyileştirme
seviyeleri, katman istekleri — hepsi aynı kalır. Yeniden ağ örülür ve aynı
tablo okunur. Böylece fark tek bir nedene bağlanabilir.

BEDELİ DE ÖLÇÜLÜR: minTetQuality'yi kapatmak bir taviz. checkMesh önce ve sonra
koşulur; katman kazanılırken ağ kalitesi bozuluyorsa bu SAYIYLA raporlanır,
"muhtemelen sorun olmaz" denmez.

    python experiments/katman_orgusu.py
Çıktı: katman_orgusu.json
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402

KAYNAK = KOK / "validation_anchors_runs" / "_anchor_sphere" / "_anchor_sphere"
HEDEF = KOK / "vehicle_runs" / "_katman_orgusu_kure"

_TABLO = re.compile(
    r"^(\S+)\s+(\d+)\s+([\d.]+)\s+([\d.eE+-]+)\s+([\d.]+)\s*$", re.M)
_EKSTRUZYON = re.compile(r"Extruding (\d+) out of (\d+) faces")


def son_katman_tablosu(log: str) -> dict | None:
    """log.snappyHexMesh'in SON katman tablosunu oku.

    Log iki tablo yazar: istenen (başta) ve gerçekleşen (sonda). Sondaki
    okunur — "ne istendi" değil "ne örüldü" sorusunun cevabı odur.
    """
    son = None
    for m in _TABLO.finditer(log):
        son = {"yama": m.group(1), "yuz": int(m.group(2)),
               "katman": float(m.group(3)), "kalinlik_m": float(m.group(4)),
               "kalinlik_pct": float(m.group(5))}
    return son


def ekstruzyon_seyri(log: str) -> list[int]:
    return [int(m.group(1)) for m in _EKSTRUZYON.finditer(log)]


def _checkmesh_ozeti(log: str) -> dict:
    from analysis.openfoam_runner import mesh_quality_gate
    g = mesh_quality_gate(log)
    return {k: g.get(k) for k in ("gecti", "maxNonOrtho", "maxSkewness",
                                  "hatali_yuz", "gerekce") if k in g} or g


def dict_gevset(metin: str) -> str:
    """Kalite ölçütünü katman-dostu yap — YALNIZ üç değişiklik."""
    metin = metin.replace("minTetQuality 1e-15;", "minTetQuality -1e30;")
    if "nRelaxedIter" not in metin:
        metin = metin.replace("    nLayerIter 50;\n",
                              "    nLayerIter 50;\n    nRelaxedIter 20;\n")
    if "relaxed" not in metin:
        metin = metin.replace("    errorReduction 0.75;\n",
                              "    errorReduction 0.75;\n"
                              "    relaxed\n    {\n        maxNonOrtho 75;\n    }\n")
    return metin


def main() -> int:
    if not KAYNAK.exists():
        print(f"kaynak vaka yok: {KAYNAK}")
        return 1
    eski_log = (KAYNAK / "log.snappyHexMesh").read_text(errors="replace")
    eski = son_katman_tablosu(eski_log)
    eski_seyir = ekstruzyon_seyri(eski_log)
    eski_check = _checkmesh_ozeti((KAYNAK / "log.checkMesh").read_text(errors="replace"))

    if HEDEF.exists():
        shutil.rmtree(HEDEF)
    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    # Yalnız ağ üretmek için gereken üç dizin. processor*/ ve postProcessing
    # KOPYALANMAZ: 6 GB'lık çözüm çıktısı bu deneyde hiçbir işe yaramaz ve
    # 13,7 GB'lık makinede diski gereksiz doldurur.
    HEDEF.mkdir()
    for alt in ("system", "constant/triSurface"):
        shutil.copytree(KAYNAK / alt, HEDEF / alt)
    shutil.copytree(KAYNAK / "0", HEDEF / "0")

    d = HEDEF / "system" / "snappyHexMeshDict"
    d.write_text(dict_gevset(d.read_text(errors="replace")))

    wsl = windows_to_wsl_path(HEDEF)
    komut = (f"cd '{wsl}' && rm -rf constant/polyMesh && "
             "blockMesh > log.blockMesh 2>&1 && "
             "surfaceFeatures > log.surfaceFeatures 2>&1 && "
             "snappyHexMesh -overwrite > log.snappyHexMesh 2>&1 && "
             "checkMesh > log.checkMesh 2>&1; tail -3 log.snappyHexMesh")
    print("ağ yeniden örülüyor (yalnız mesh, çözücü YOK) ...")
    r = linux_run(komut, 5400)
    if r.returncode != 0:
        print("KOMUT DÜŞTÜ:", (r.stderr or r.stdout)[-800:])

    yeni_log_p = HEDEF / "log.snappyHexMesh"
    if not yeni_log_p.exists():
        print("log üretilmedi")
        return 1
    yeni_log = yeni_log_p.read_text(errors="replace")
    yeni = son_katman_tablosu(yeni_log)
    yeni_seyir = ekstruzyon_seyri(yeni_log)
    yeni_check = _checkmesh_ozeti(
        (HEDEF / "log.checkMesh").read_text(errors="replace")
        if (HEDEF / "log.checkMesh").exists() else "")

    _kaz = (None if not (eski and yeni) else
            round(yeni["katman"] / eski["katman"], 2) if eski["katman"] else None)
    rec = {
        "vaka": "katman örgüsü — kalite ölçütü gevşetmesinin ÖLÇÜLEN etkisi",
        "_tarih": "2026-08-19",
        "_deney": ("Arşivlenmiş küre vakası kopyalandı; snappyHexMeshDict'te "
                   "YALNIZ minTetQuality, relaxed bloğu ve nRelaxedIter değişti. "
                   "Geometri, alan, iyileştirme seviyeleri ve katman isteği aynı."),
        "_taban_notu": ("Karşılaştırma tabanı ARŞİVLENMİŞ koşudur, bu oturumda "
                        "yeniden koşulmamıştır. Aynı vaka ve aynı makine, ama "
                        "eşzamanlı değil."),
        "istenen_katman": 10,
        "onceki": {"katman": eski and eski["katman"],
                   "kalinlik_pct": eski and eski["kalinlik_pct"],
                   "kalinlik_m": eski and eski["kalinlik_m"],
                   "ekstruzyon_seyri": eski_seyir,
                   "yuz": eski and eski["yuz"],
                   "checkMesh": eski_check},
        "sonraki": {"katman": yeni and yeni["katman"],
                    "kalinlik_pct": yeni and yeni["kalinlik_pct"],
                    "kalinlik_m": yeni and yeni["kalinlik_m"],
                    "ekstruzyon_seyri": yeni_seyir,
                    "yuz": yeni and yeni["yuz"],
                    "checkMesh": yeni_check},
        "kazanc_kat": _kaz,
    }
    if yeni:
        rec["verdikt"] = (
            f"katman {eski['katman'] if eski else '?'} → {yeni['katman']}, "
            f"kalınlık %{eski['kalinlik_pct'] if eski else '?'} → "
            f"%{yeni['kalinlik_pct']}. "
            + ("HEDEFE ULAŞILDI" if yeni["katman"] >= 8.0 else
               "İYİLEŞTİ AMA YETMEDİ" if _kaz and _kaz > 1.5 else
               "DEĞİŞMEDİ — kök neden başka"))
    else:
        rec["verdikt"] = "ÖLÇÜLEMEDİ — snappy katman tablosu yazmadı"

    (KOK / "katman_orgusu.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nönce : katman {rec['onceki']['katman']}  "
          f"%{rec['onceki']['kalinlik_pct']}  ekstrüzyon {eski_seyir[:1]}→{eski_seyir[-1:]}")
    print(f"sonra: katman {rec['sonraki']['katman']}  "
          f"%{rec['sonraki']['kalinlik_pct']}  ekstrüzyon {yeni_seyir[:1]}→{yeni_seyir[-1:]}")
    print(f"\n{rec['verdikt']}")
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
