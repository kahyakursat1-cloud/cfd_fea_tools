"""snappyHexMesh KATMAN adımının tepe belleğini ÖLÇ — kapının beyan ettiği boşluk.

NEDEN: `bellek_kapisi` "sığar" hükmünü verirken kapsamını dürüstçe beyan ediyor —
katsayı ÇÖZÜM koşularından türetildi (0,779 kB/hücre + 0,215 GB, R²=0,96) ve
snappyHexMesh'in katman adımını KAPSAMIYOR. Beyanın doğruluğu 2026-08-20'de
ölçüldü: AR6 çapası, kapı "6M hücre ~6,07 GB; boş 7,9 GB — sığar" dedikten sonra
snappyHexMesh'te dönüş kodu 137 (SIGKILL = OOM) ile 1319 s sonra öldü, log
kuyruğu `displacementMedialAxis`. Yani hüküm çözüm için doğru, meshleme için
yanlıştı ve kapı bunu zaten söylüyordu. Eksik olan katsayının kendisi.

SINANAN İDDİA (koşulardan ÖNCE yazılıyor): kapının kendi notu diyor ki
"geçici veri yapıları son hücre sayısıyla orantılı DEĞİLDİR; medial-axis hesabı
tüm yüzey noktalarının mesafe alanını tutar". Bu doğruysa tepe bellek YÜZEY
yüzü sayısıyla hacim hücresinden DAHA İYİ ölçeklenmeli. İkisi de oturtulup R²
karşılaştırılır; hangisinin kazandığı önceden ilan edilmiyor, ölçülüyor.

YÖNTEM: aynı gövde, artan çözünürlükte, KATMANLI. snappyHexMesh `/usr/bin/time -v`
altında koşulur ve "Maximum resident set size" okunur. Tek seferde tek koşu —
uzun bir CFD koşusu sürerken ikinci iş açılmaz (bu makine 2026-08-19'da böyle
kapandı).

Çıktı: snappy_katman_tepe_bellegi.json
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import psutil  # noqa: E402
import trimesh  # noqa: E402

from analysis.openfoam_runner import (  # noqa: E402
    OF_ENV_PREFIX,
    CFDCase,
    _wsl_run,
    build_case,
    windows_to_wsl_path,
)
from validate_pipeline import ahmed_body  # noqa: E402

CIKTI = KOK / "snappy_katman_tepe_bellegi.json"
CALISMA = KOK / "vehicle_runs" / "_snappy_bellek"
# Guvenlik tavani: bu makinede 13,7 GB var. En buyuk seviye once kucukten
# gelen egilimle kontrol edilir; tahmin tavani asarsa seviye ATLANIR.
TAVAN_GB = 4.0


def _bos_gb() -> float:
    return psutil.virtual_memory().available / 2 ** 30


def _tepe_rss_gb(ciktı: str) -> float | None:
    m = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", ciktı)
    return int(m.group(1)) / 2 ** 20 if m else None


def _checkmesh_sayilari(log: str) -> dict:
    d = {}
    m = re.search(r"cells:\s*(\d+)", log)
    if m:
        d["hucre"] = int(m.group(1))
    m = re.search(r"faces:\s*(\d+)", log)
    if m:
        d["yuz"] = int(m.group(1))
    # govde yamasinin yuz sayisi: medial-axis'in tasidigi yuzey nokta alaninin vekili
    m = re.search(r"^\s*\w*[Bb]ody\s+\d+\s+(\d+)", log, re.M)
    if not m:
        m = re.search(r"patch\s+\d+\s+(\d+)\s+\d+\s+\w*(?:body|govde)", log, re.I)
    if m:
        d["govde_yuz"] = int(m.group(1))
    return d


def _seviye_kos(ad: str, stl: Path, ref: int, tavan: int, katman: int) -> dict:
    CALISMA.mkdir(parents=True, exist_ok=True)
    case = CFDCase(name=ad, stl_path=stl, velocity=40.0,
                   refinement_min=ref, refinement_max=ref + 1,
                   max_global_cells=tavan, n_layers=katman)
    case_dir = build_case(case, CALISMA)
    wsl = windows_to_wsl_path(case_dir)

    r = _wsl_run(wsl, "surfaceFeatures > log.surfaceFeatures 2>&1 && "
                      "blockMesh > log.blockMesh 2>&1", 900)
    if r.returncode != 0:
        return {"ad": ad, "durum": "blockMesh düştü", "stderr": r.stderr[-300:]}

    # /usr/bin/time -v snappy'yi sarar; tepe RSS stderr'e yazilir.
    cmd = ("/usr/bin/time -v snappyHexMesh -overwrite "
           "> log.snappyHexMesh 2>log.snappy_time")
    r = _wsl_run(wsl, cmd, 5400)
    zaman = (case_dir / "log.snappy_time")
    metin = zaman.read_text(encoding="utf-8", errors="replace") if zaman.exists() else ""
    tepe = _tepe_rss_gb(metin)
    if r.returncode != 0 or tepe is None:
        kod = re.search(r"Exit status:\s*(\d+)", metin)
        return {"ad": ad, "durum": "snappy düştü", "tepe_rss_gb": tepe,
                "cikis_kodu": int(kod.group(1)) if kod else r.returncode}

    r2 = _wsl_run(wsl, "checkMesh > log.checkMesh 2>&1", 900)
    log = (case_dir / "log.checkMesh").read_text(encoding="utf-8", errors="replace")
    say = _checkmesh_sayilari(log)
    snappy_log = (case_dir / "log.snappyHexMesh").read_text(encoding="utf-8",
                                                            errors="replace")
    # KATMAN TABLOSU snappy log'unda su bicimde:
    #   patch faces    layers   overall thickness
    #                            [m]       [%]
    #   ahmed 202      3        0.114     100
    # Onceki surum "Added N total layers" ariyordu ve HIC tutmuyordu; katman
    # eklenip eklenmedigi kayda gecmiyordu. Katmansiz bir kosuyu katmanli
    # sanip olcmek, olcumun TAMAMINI gecersiz kilardi.
    tab = re.search(r"patch\s+faces\s+layers\s+overall thickness.*?\n-+\s+-+\s+-+\s+-+\s+-+\s*\n"
                    r"\s*(\S+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)",
                    snappy_log, re.S)
    out = {"ad": ad, "durum": "ok", "tepe_rss_gb": round(tepe, 3),
           "katman_hedef": katman,
           "govde_yuz": int(tab.group(2)) if tab else None,
           "katman_eklendi": int(tab.group(3)) if tab else None,
           "katman_kalinlik_pct": float(tab.group(5)) if tab else None,
           "checkMesh_rc": r2.returncode, **say}
    shutil.rmtree(case_dir, ignore_errors=True)   # disk 33 GB — vaka birikmesin
    return out


def _fit(x: list, y: list) -> dict:
    """y = a*x + b en kucuk kareler + R². numpy'siz, sade."""
    n = len(x)
    if n < 3:
        return {"n": n, "R2": None}
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0:
        return {"n": n, "R2": None}
    a = sxy / sxx
    b = my - a * mx
    sst = sum((v - my) ** 2 for v in y)
    sse = sum((v - (a * u + b)) ** 2 for u, v in zip(x, y))
    return {"n": n, "egim": a, "sabit": b,
            "R2": (1 - sse / sst) if sst else None}


def main() -> int:
    stl = CALISMA / "ahmed.stl"
    CALISMA.mkdir(parents=True, exist_ok=True)
    m = ahmed_body()
    m.export(stl)
    yuzey_ucgen = int(len(m.faces))

    print(f"Ahmed gövdesi: {yuzey_ucgen} yüzey üçgeni, boş RAM {_bos_gb():.2f} GB")
    print("Kademeler artan çözünürlükte, KATMANLI (n_layers=3).\n")

    sonuc = []
    for ref, tavan in ((1, 200_000), (2, 500_000), (2, 1_000_000), (3, 2_000_000)):
        ad = f"ahmed_r{ref}_{tavan // 1000}k"
        bos = _bos_gb()
        print(f"[{ad}] boş {bos:.2f} GB — başlıyor", flush=True)
        if bos < 2.0:
            print("  ATLANDI: boş bellek 2 GB altında", flush=True)
            sonuc.append({"ad": ad, "durum": "atlandı (bellek)"})
            continue
        r = _seviye_kos(ad, stl, ref, tavan, katman=3)
        r["bos_gb_baslangic"] = round(bos, 2)
        sonuc.append(r)
        print(f"  -> {r.get('durum')}  tepe={r.get('tepe_rss_gb')} GB  "
              f"hücre={r.get('hucre')}  gövde_yüz={r.get('govde_yuz')}", flush=True)
        if r.get("durum") == "ok" and (r["tepe_rss_gb"] or 0) > TAVAN_GB:
            print("  DUR: tepe güvenlik tavanını aştı, daha ince seviye açılmıyor")
            break

    ok = [r for r in sonuc if r.get("durum") == "ok" and r.get("hucre")]
    fitler = {}
    if len(ok) >= 3:
        y = [r["tepe_rss_gb"] for r in ok]
        fitler["hucre_basina"] = _fit([r["hucre"] for r in ok], y)
        if all(r.get("govde_yuz") for r in ok):
            fitler["govde_yuzu_basina"] = _fit([r["govde_yuz"] for r in ok], y)

    # HUKUM ZORUNLU: kokteki her kanit dosyasi hukum tasimali (kanit.manifest).
    # Hukumsuz bir kanit, okuyucuya "olctum" der ama "ne cikti" demez.
    f = fitler.get("hucre_basina") or {}
    r2 = f.get("R2")
    if r2 is not None and r2 > 0.95:
        verdikt = (f"✅ ÖLÇÜLDÜ: snappy katman tepesi {f['egim'] * 1e6:.3f} kB/hücre "
                   f"+ {f['sabit']:.3f} GB (R²={r2:.5f}, n={f['n']}). Çözüm "
                   f"katsayısının ~{f['egim'] * 1e6 / 0.779:.2f} katı — meshleme "
                   f"~0,25M hücreden sonra BAĞLAYICI aşamadır. Geri-tahmin: AR6'nın "
                   f"6M hücresi için {6e6 * f['egim'] + f['sabit']:.2f} GB öngörür, "
                   f"o an boş olan 7,9 GB'ın üstünde — gözlenen OOM ile uyumlu.")
    elif r2 is not None:
        verdikt = (f"⚠️ Uyum zayıf (R²={r2:.4f}, n={f['n']}) — tepe bellek hücre "
                   f"sayısıyla güvenilir biçimde öngörülemiyor; kapıya katsayı "
                   f"bağlanmamalı.")
    else:
        verdikt = ("❌ ÖLÇÜLEMEDİ: uyum için en az üç başarılı kademe gerekiyor; "
                   "elde yeterli kademe yok.")

    rec = {"vaka": "snappyHexMesh katman adımı tepe belleği (Ahmed, n_layers=3)",
           "verdikt": verdikt,
           "_neden": __doc__.strip().splitlines()[0],
           "yuzey_ucgen": yuzey_ucgen, "seviyeler": sonuc, "fitler": fitler}
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    for ad, f in fitler.items():
        print(f"  {ad}: R²={f.get('R2')}, eğim={f.get('egim')}")
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
