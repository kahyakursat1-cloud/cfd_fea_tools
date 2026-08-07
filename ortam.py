"""Ortam parmak izi — bir sayının hangi sürümlerle üretildiği kanıtın parçasıdır.

NEDEN: bu depo her sayının yeniden üretilebilir olmasını savunuyor ve kanıt
dosyaları üretim KOMUTUNU taşıyor. Ama komut yetmez: aynı komut farklı bir
OpenFOAM ya da numpy sürümüyle farklı bir sayı verebilir ve hiçbir şey bunu
söylemez. GCI %1,7 diye yayımlanmış bir band, altındaki çözücü değiştiğinde
sessizce geçersizleşir.

NE KAYDEDİLİR: yalnız SONUCU DEĞİŞTİREBİLECEK olanlar — Python, sayısal
kütüphaneler, çözücü sürümleri, işletim sistemi ve çekirdek sayısı (paralel
ayrıştırma sonucu mikro-etkiler). Paket listesinin tamamı değil: gürültü,
gerçek bir değişikliği görünmez yapar.

NE KAYDEDİLMEZ: makine adı, kullanıcı adı, yol — kanıt dosyaları paylaşılıyor.

    python ortam.py            # şu anki parmak izi
    python ortam.py --fark <kanit.json>   # kanıtın ortamı ile bugünkü fark
"""
from __future__ import annotations

import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Sonucu degistirebilecek kutuphaneler. Genisletirken olcut: "bu paketin surumu
# degisirse yayimlanan bir sayi degisebilir mi?"
IZLENEN_PAKETLER = ("numpy", "scipy", "trimesh", "gmsh", "matplotlib", "psutil")


def _paket_surumleri() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for ad in IZLENEN_PAKETLER:
        if importlib.util.find_spec(ad) is None:
            out[ad] = None
            continue
        mod = __import__(ad)
        out[ad] = str(getattr(mod, "__version__", "?"))
    return out


def _komut_surumu(argv: list[str], desen: str) -> str | None:
    """Bir dış aracın sürümü. Araç yoksa None — 'yok' ile 'okunamadı' ayrılmaz,
    ikisi de bilinmiyordur ve öyle yazılır."""
    r = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    metin = (r.stdout or "") + (r.stderr or "")
    for satir in metin.splitlines():
        if desen.lower() in satir.lower():
            return satir.strip()[:120]
    return None


def cozucu_surumleri() -> dict[str, str | None]:
    """OpenFOAM ve CalculiX sürümleri (WSL üzerinden). Ulaşılamıyorsa None."""
    out: dict[str, str | None] = {"openfoam": None, "calculix": None}
    if platform.system() != "Windows":
        return out
    from analysis.backend import linux_run
    for anahtar, komut, desen in (
        ("openfoam", "foamRun -help 2>&1 | head -5 || true", "openfoam"),
        ("calculix", "ccx -v 2>&1 | head -3 || true", "version"),
    ):
        r = linux_run(komut, 30)
        metin = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
        for satir in metin.splitlines():
            if desen in satir.lower():
                out[anahtar] = satir.strip()[:120]
                break
    return out


def parmak_izi(cozucu: bool = False) -> dict:
    """Şu anki ortam. `cozucu=True` WSL'e gider (yavaş); varsayılan hızlıdır."""
    d = {
        "python": platform.python_version(),
        "paketler": _paket_surumleri(),
        "os": f"{platform.system()} {platform.release()}",
        "cekirdek": _cekirdek(),
    }
    if cozucu:
        d["cozucu"] = cozucu_surumleri()
    return d


def _cekirdek() -> int | None:
    import os
    return os.cpu_count()


def fark(eski: dict | None, yeni: dict | None = None) -> dict:
    """İki parmak izi arasındaki SONUÇ-ETKİLEYEBİLİR farklar.

    Döner: {"ayni": bool, "farklar": [...], "karsilastirilamaz": [...]}
    Eksik alan farksızlık SAYILMAZ: eski kanıtta o alan yoksa
    'karşılaştırılamaz' listesine girer.
    """
    yeni = yeni or parmak_izi()
    if not isinstance(eski, dict) or not eski:
        return {"ayni": None, "farklar": [],
                "karsilastirilamaz": ["kanıtta ortam parmak izi YOK — bu kanıt "
                                      "ortam damgası eklenmeden önce üretilmiş"]}
    farklar, yok = [], []
    for alan in ("python", "os", "cekirdek"):
        a, b = eski.get(alan), yeni.get(alan)
        if a is None or b is None:
            yok.append(alan)
        elif str(a) != str(b):
            farklar.append(f"{alan}: {a} → {b}")
    ep, yp = eski.get("paketler") or {}, yeni.get("paketler") or {}
    for ad in IZLENEN_PAKETLER:
        a, b = ep.get(ad), yp.get(ad)
        if a is None or b is None:
            yok.append(f"paket:{ad}")
        elif a != b:
            farklar.append(f"{ad}: {a} → {b}")
    ec, yc = eski.get("cozucu") or {}, yeni.get("cozucu") or {}
    for ad in ("openfoam", "calculix"):
        a, b = ec.get(ad), yc.get(ad)
        if a and b and a != b:
            farklar.append(f"{ad}: {a} → {b}")
    return {"ayni": not farklar, "farklar": farklar,
            "karsilastirilamaz": yok}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if args and args[0] == "--fark":
        if len(args) < 2:
            print("kullanım: python ortam.py --fark <kanit.json>")
            return 2
        d = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        f = fark(d.get("_ortam"))
        print(json.dumps(f, indent=2, ensure_ascii=False))
        return 0 if f["ayni"] is not False else 1
    print(json.dumps(parmak_izi(cozucu="--cozucu" in args),
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
