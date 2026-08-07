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
    """OpenFOAM ve CalculiX sürümleri (arka uç üzerinden). Ulaşılamıyorsa None.

    OPENFOAM SÜRÜMÜ SESSİZCE KAYITSIZ KALIYORDU. Sonda `foamRun -help`
    çağırıyordu ama OpenFOAM ortamını SOURCE ETMEDEN — o kabukta `foamRun`
    PATH'te yok ve komut `command not found` veriyordu. Sonuç: kanıt
    dosyalarında `openfoam: null`, yani en kritik çözücünün sürümü hiç
    kaydedilmiyordu. Yayımlanan bir GCI bandı, altındaki çözücü değiştiğinde
    sessizce geçersizleşebilir; kaydın amacı tam olarak buydu.

    Artık ortam öneki (`OF_ENV_PREFIX`) kullanılıyor ve BUILD HASH yakalanıyor:
    "Build: 11-e1fc8c682ae6" — yalnız ana sürüm değil, derleme kimliği.
    """
    out: dict[str, str | None] = {"openfoam": None, "calculix": None}
    if platform.system() != "Windows":
        return out
    from analysis.backend import linux_run
    from analysis.openfoam_runner import OF_ENV_PREFIX
    for anahtar, komut, desen in (
        # `blockMesh -help` basligi "Build: <surum>-<hash>" tasir; foamVersion
        # yalniz "OpenFOAM-11" verir ve derleme kimligini kaybeder.
        # `head` KULLANILMAZ: Build satiri yardim ciktisinin SONUNDA ve ilk
        # alti satirin disinda kaliyor — ilk duzeltmede tam da bu yuzden yine
        # null dondu. grep, satirin yerinden bagimsiz bulur.
        ("openfoam", f"{OF_ENV_PREFIX}blockMesh -help 2>&1 | grep -i '^Build' || true",
         "build"),
        ("calculix", "ccx -v 2>&1 | head -3 || true", "version"),
    ):
        r = linux_run(komut, 60)
        metin = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
        for satir in metin.splitlines():
            if desen in satir.lower():
                out[anahtar] = satir.strip()[:120]
                break
    return out


def damgala(kanit: dict, cozucu: bool = True) -> dict:
    """Kanıt sözlüğüne ortam parmak izini ÜRETİM ANINDA basar.

    Damga şimdiye kadar yalnız `kanit.py --dogrula` yolundan ekleniyordu, yani
    bir kanıt ancak SONRADAN doğrulanırsa ortamını taşıyordu. Ölçüldü: kökteki
    95 JSON'un HİÇBİRİ damga taşımıyordu. "Kanıtın ortamı da kanıtın
    parçasıdır" iddiası, damgayı üretenin kanıtı üreten kod olmasını gerektirir
    --- sonradan eklenen damga, o sayının hangi yığında doğduğunu değil, en son
    ne zaman bakıldığını söyler.

    `cozucu=True` varsayılan: CFD/FEA kanıtlarında çözücü sürümü en kritik
    bileşendir ve arka uca bir çağrı (~1 s) onun yanında ihmal edilebilir.
    """
    kanit["_ortam"] = parmak_izi(cozucu=cozucu)
    return kanit


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
        # EKSIK COZUCU SURUMU SESSIZ GECIYORDU: `if a and b` koşulu, biri None
        # olduğunda ne fark ne de karşılaştırılamaz sayıyordu — yani "çözücü
        # sürümü bilinmiyor" hâli "aynı" gibi okunuyordu. Paket alanlarında bu
        # ayrım zaten yapılıyordu; çözücüde yapılmıyordu ve çözücü daha kritik.
        if a is None or b is None:
            yok.append(f"cozucu:{ad}")
        elif a != b:
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
