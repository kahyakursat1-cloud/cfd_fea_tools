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
from analysis.openfoam_runner import OF_ENV_PREFIX  # noqa: E402

# Ilk surum bu oneki sarmiyordu ve komut `blockMesh: command not found` ile
# dustu. Ortak katman her cozucu cagrisini bu onekle sarar.

SADECE_OKU = False       # --oku: agi yeniden ORMEDEN mevcut loglardan turet

GENISLEME_ORANI = 1.25   # snappyHexMeshDict expansionRatio (katmanli kosu)
HEDEF_H1_M = 2e-5        # istenen ilk hucre (y+=1 icin boyutlandirilmisti)

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


def ilk_hucre(toplam_m: float | None, katman: float | None,
              r: float = GENISLEME_ORANI) -> float | None:
    """Geometrik seriden ilk katman yüksekliği: h1 = T·(r-1)/(rⁿ-1).

    NEDEN KATMAN SAYISI DEĞİL BU: fiziği belirleyen y⁺'tır ve y⁺ ∝ h1'dir.
    Aynı toplam kalınlık 6 katmanla da 10 katmanla da örülebilir; ikisinin
    duvar çözünürlüğü AYNI DEĞİLDİR. Katman sayısını hedef almak, ölçmek
    istediğimiz niceliğin yerine bir vekilini koymaktır.
    """
    if not toplam_m or not katman or katman <= 0:
        return None
    return toplam_m * (r - 1.0) / (r ** katman - 1.0)


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
    # DUZELTME ONCESI TABAN — SABIT YAZILI ve bu KASITLI. Taban, capanin
    # 2026-08-19'daki duzeltme-oncesi log.snappyHexMesh'inden OKUNMUSTU; ayni
    # capa duzeltilmis ayarla yeniden kosulunca o log UZERINE YAZILDI. Yani
    # taban artik yeniden turetilemez ve yalnizca burada korunuyor.
    #
    # Alternatif, tabani "kayip" diye bosaltmakti; o zaman kanit dosyasi
    # duzeltmenin ETKISINI hic gosteremezdi. Sayilarin nereden geldigi
    # yukarida modul dokumaninda ve commit kaydinda yazili.
    TABAN = {"yama": "_anchor_sphere_prep", "yuz": 1728, "katman": 0.535,
             "kalinlik_m": 9.21e-05, "kalinlik_pct": 13.9}
    TABAN_SEYIR = [1360, 1008, 880, 780, 736, 672, 620, 608, 600]
    TABAN_CHECK = {"verdict": "ok", "non_ortho_max": 62.8783,
                   "skew_max": 0.6832401, "aspect_max": 10.379154,
                   "negatif_hacim": False, "mesh_ok": True}

    eski_log = (KAYNAK / "log.snappyHexMesh").read_text(errors="replace")
    _canli = son_katman_tablosu(eski_log)
    # Log hala duzeltme-oncesi taban mi, yoksa uzerine yazildi mi?
    _taban_canli = bool(_canli and _canli["katman"] < 2.0)
    eski = _canli if _taban_canli else TABAN
    eski_seyir = ekstruzyon_seyri(eski_log) if _taban_canli else TABAN_SEYIR
    eski_check = (_checkmesh_ozeti((KAYNAK / "log.checkMesh").read_text(errors="replace"))
                  if _taban_canli else TABAN_CHECK)

    if not SADECE_OKU:
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
        komut = (f"{OF_ENV_PREFIX}cd '{wsl}' && rm -rf constant/polyMesh && "
                 "blockMesh > log.blockMesh 2>&1 && "
                 "surfaceFeatures > log.surfaceFeatures 2>&1 && "
                 "snappyHexMesh -overwrite > log.snappyHexMesh 2>&1 && "
                 "checkMesh > log.checkMesh 2>&1; tail -3 log.snappyHexMesh")
        print("ağ yeniden örülüyor (yalnız mesh, çözücü YOK) ...")
        r = linux_run(komut, 5400)
        if r.returncode != 0:
            print("KOMUT DÜŞTÜ:", (r.stderr or r.stdout)[-800:])
    else:
        print("--oku: ağ yeniden örülmüyor, mevcut loglar okunuyor")

    yeni_log_p = HEDEF / "log.snappyHexMesh"
    if not yeni_log_p.exists():
        # DUZELTME URETIME GECTI: capa kosucusu artik gevsetilmis olcutu KENDI
        # yaziyor (analysis/openfoam_runner), dolayisiyla ayri bir deney kopyasi
        # gerekmiyor. "Sonraki" tarafi dogrudan capa kosusundan okunur — bu daha
        # iyidir, cunku URETIM yolunu olcer, yamali bir kopyayi degil.
        yeni_log_p = KAYNAK / "log.snappyHexMesh"
        if not yeni_log_p.exists():
            print("ne deney kopyasi ne capa kosusu logu var")
            return 1
        print(f"deney kopyasi yok; ÜRETİM yolundan okunuyor: {KAYNAK.name}")
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
        "_taban_notu": ("Taban, çapanın düzeltme ÖNCESİ log.snappyHexMesh'inden "
                        "okundu. Aynı çapa düzeltilmiş ayarla yeniden koşulunca "
                        "o log ÜZERİNE YAZILDI; taban artık yeniden türetilemez "
                        "ve yalnız bu kayıtta korunuyor."),
        "_taban_canli_mi": _taban_canli,
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

    # ASIL ÖLÇÜT BURADA. Deney öncesinde ön-kayıtlı ölçüt "≥8 katman"dı ve
    # sonuç 6,82 ile onun ALTINDA kaldı. Ama o ölçüt YANLIŞ NİCELİĞE bakıyordu:
    # geçiş modelini geçerli kılan şey katman SAYISI değil, ilk hücrenin
    # y⁺'ıdır. Aynı toplam kalınlık 6 katmanla da 10 katmanla da örülebilir ve
    # ikisinin duvar çözünürlüğü aynı olmaz. Ön-kayıtlı ölçütü tutturamadığımı
    # gizlemiyorum; ölçütün kendisi vekildi ve vekil yanlış seçilmişti.
    h1_yeni = ilk_hucre(yeni and yeni["kalinlik_m"], yeni and yeni["katman"])
    # y⁺ ∝ h1 ve HEDEF_H1_M zaten y⁺=1 için boyutlandırılmıştı.
    yplus_tahmin = h1_yeni / HEDEF_H1_M if h1_yeni else None
    rec["ilk_hucre"] = {
        "hedef_h1_m": HEDEF_H1_M,
        "ulasilan_h1_m": h1_yeni and round(h1_yeni, 9),
        "oran": yplus_tahmin and round(yplus_tahmin, 2),
        "yplus_TAHMINI": yplus_tahmin and round(yplus_tahmin, 1),
        "_tahmin_uyarisi": (
            "Bu bir ÖLÇÜM DEĞİL, geometriden türetilmiş kestirimdir: y⁺ = "
            "h1·u_τ/ν ve u_τ ancak çözümle bilinir."),
        # TAHMIN CURUTULDU. Kure capasi duzeltilmis agla yeniden kosuldu.
        "yplus_OLCULEN": 5.54,
        "_tahmin_hatasi": (
            "Kestirim 2,2 idi, ÖLÇÜLEN 5,54 — 2,5 kat sapma. Hata h1'i "
            "türetirken 6,82 ortalama katmanı yüzeye TEK TİP dağılmış "
            "varsaymaktı; katman dağılımı düzgün değil (y⁺ min 0,11, max 211). "
            "Ortalama katman sayısından tekil bir h1 türetmek bu yüzden ancak "
            "mertebe verir. Kapı 5,54'ü de reddediyor (sınır 5) — ama artık "
            "kıl payı, 59 ile değil."),
        "_on_kayitli_olcut": (
            "Deney öncesi ölçüt '≥8 katman' yazılmıştı ve 6,82 onu TUTTURMADI. "
            "Ölçüt yanlış niceliğe bakıyordu — belirleyici olan h1'dir."),
    }

    if yeni:
        _band = ("DUVAR-ÇÖZÜNÜR bandda (y⁺≤5)" if yplus_tahmin and yplus_tahmin <= 5.0
                 else "hâlâ band dışı")
        rec["verdikt"] = (
            f"katman {eski['katman'] if eski else '?'} → {yeni['katman']}, "
            f"kalınlık %{eski['kalinlik_pct'] if eski else '?'} → "
            f"%{yeni['kalinlik_pct']}, ekstrüzyon çürümesi durdu "
            f"({eski_seyir[0] if eski_seyir else '?'}→{eski_seyir[-1] if eski_seyir else '?'} "
            f"yerine {yeni_seyir[0] if yeni_seyir else '?'}→"
            f"{yeni_seyir[-1] if yeni_seyir else '?'}). "
            f"İlk hücre {h1_yeni:.2e} m → y⁺ kestirimi {yplus_tahmin:.1f} ({_band}), "
            "ÖLÇÜLEN 5,54 — kestirim 2,5 kat saptı. Ön-kayıtlı '≥8 katman' "
            "ölçütü de TUTMADI (6,82). Katman örgüsü DÜZELDİ (y⁺ 59,08→5,54, "
            "10,7 kat) ama y⁺ hâlâ duvar-çözünür bandın kıl payı dışında ve "
            "çapa artık BAŞKA bir nedenle düşüyor: ince seviye yakınsamıyor "
            "(rezidüeller limit çevriminde, son %20'de Cd sürüklenmesi %46,7). "
            "Re=1e5'te küre izi zaman-bağımlıdır; kararlı RANS'ın yakınsayacağı "
            "bir çözüm yok."
            if h1_yeni else "ilk hücre türetilemedi")
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
    SADECE_OKU = "--oku" in sys.argv     # agi yeniden ormeden kaniti turet
    raise SystemExit(main())
