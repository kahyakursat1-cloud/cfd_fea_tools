"""Harici araç keşfi — OpenVSP, OpenRocket ve JVM için TEK KAYNAK.

NEDEN: bu araçların yolları dört ayrı dosyaya mutlak Windows yolu olarak gömülüydü
(`pipeline.py`, `openvsp_bridge.py`, `openrocket_bridge.py`, `mesh_generator.py`).
Hepsi bu makineye özgü: `C:\\Users\\Victus\\...`. Uygulama Docker imajında Linux'ta
koşacağı için bunların TAMAMI orada kırılır — üstelik SESSİZCE: `pipeline.py`
"openvsp conda env bulunamadi — atlandi" deyip None döner, boru hattı devam eder ve
raporda VSPAERO bölümü yalnızca EKSİK görünür, HATALI değil.

Bu modül aramayı sıraya koyar ve NEREDE ARADIĞINI HER ZAMAN söyler:
  1. ortam değişkeni (Docker'da tek yapılandırma noktası)
  2. PATH (Linux paket kurulumu / imaj)
  3. platforma özgü bilinen varsayılanlar (geliştirme makinesi)

Hiçbir yol "sessizce yok" olmaz: `bul()` daima nereye baktığını ve neden bulamadığını
döner. Kurulum doğrulaması için:

    python dis_araclar.py            # tablo, eksikse çıkış kodu 1
    python dis_araclar.py --json     # dis_araclar.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

WINDOWS = os.name == "nt"

# Her araç: ortam değişkeni + PATH'te aranacak isimler + platform varsayılanları.
# `dizin=True` olanlar dosya değil KLASÖR bekler (DLL dizini, JAVA_HOME).
ARACLAR: dict[str, dict] = {
    "openvsp_python": {
        "aciklama": "OpenVSP API'sini içeren Python yorumlayıcısı (ayrı ortam)",
        "env": "OPENVSP_PYTHON",
        "path_isim": [],
        "varsayilan": ([r"C:\Users\Victus\miniconda3\envs\openvsp\python.exe"] if WINDOWS
                       else ["/opt/conda/envs/openvsp/bin/python", "/usr/bin/python3"]),
    },
    "openvsp_dll": {
        "aciklama": "OpenVSP paylaşımlı kitaplık dizini (Windows'ta add_dll_directory)",
        "env": "OPENVSP_DIR", "dizin": True, "zorunlu": WINDOWS,
        "path_isim": [],
        "varsayilan": ([r"C:\Users\Victus\Desktop\OpenVSP\OpenVSP-3.50.4-win64"] if WINDOWS
                       else ["/opt/OpenVSP"]),
    },
    "vspaero": {
        "aciklama": "VSPAERO çözücü ikilisi",
        "env": "VSPAERO_EXE",
        "path_isim": ["vspaero"],
        "varsayilan": ([r"C:\Users\Victus\Desktop\OpenVSP\OpenVSP-3.50.4-win64\vspaero.exe"]
                       if WINDOWS else ["/opt/OpenVSP/vspaero"]),
    },
    "openrocket_python": {
        "aciklama": "orhelper + jpype içeren Python yorumlayıcısı",
        "env": "OPENROCKET_PYTHON",
        "path_isim": [],
        "varsayilan": ([r"C:\Users\Victus\miniconda3\envs\orenv\python.exe"] if WINDOWS
                       else ["/opt/conda/envs/orenv/bin/python"]),
    },
    "openrocket_jar": {
        "aciklama": "OpenRocket.jar (JPype ile sürülür)",
        "env": "OPENROCKET_JAR",
        "path_isim": [],
        "varsayilan": ([r"C:\Program Files\OpenRocket\OpenRocket.jar"] if WINDOWS
                       else ["/opt/openrocket/OpenRocket.jar"]),
    },
    "xfoil": {
        # NEDEN EKLENDİ: düşük-Re geçişli 2B kesit poları RANS'la üretilemedi.
        # ÖLÇÜLDÜ (Re=3.5e5, C-grid): ilk hücre 3e-5 → yakınsıyor ama Cl 0.17-0.32
        # (beklenen ~0.44); 8e-6 → IRAKSIYOR (Cd=-691205). Kurulumun relaxation'ı
        # Re=3.4e6 için elle ayarlanmış ve 10 kat farklı Re'ye taşınmıyor.
        # XFOIL'in panel + e^N yöntemi tam bu rejim için tasarlandı.
        # WSL'de: sudo apt install xfoil   (Debian/Ubuntu paketi, 6.99)
        "aciklama": "XFOIL 6.99 — 2B kesit poları (panel + e^N geçiş)",
        "env": "XFOIL_EXE",
        "path_isim": ["xfoil"],
        # Windows'ta da varsayilan VERILIR: bu makinede XFOIL WSL icinde kurulu ve
        # `\\wsl$` UNC yolu Windows tarafindan gorulebilir. Bos birakmak "aranacak
        # yer yok" demek olurdu; `bul()` NEREYE BAKTIGINI her zaman soylemeli.
        "varsayilan": ([r"\\wsl$\Ubuntu\usr\bin\xfoil"] if WINDOWS
                       else ["/usr/bin/xfoil", "/usr/local/bin/xfoil"]),
        "wsl": True,          # Windows'ta WSL üzerinden sürülür
        "zorunlu": False,
    },
    "java_home": {
        "aciklama": "JVM kökü — orhelper JAVA_HOME ister",
        "env": "JAVA_HOME", "dizin": True,
        "path_isim": [],
        "varsayilan": ([r"C:\Users\Victus\miniconda3\envs\orenv\Library\lib\jvm"] if WINDOWS
                       else ["/usr/lib/jvm/java-17-openjdk-amd64", "/opt/java/openjdk"]),
    },
}


def _uygun(yol: str | os.PathLike, dizin: bool) -> bool:
    p = Path(yol)
    return p.is_dir() if dizin else p.is_file()


def bul(arac: str) -> dict:
    """Aracı sırayla ara. HER ZAMAN nereye bakıldığını döndürür.

    Dönen: {'arac', 'yol'|None, 'kaynak', 'aranan': [...], 'neden': str|None,
            'zorunlu': bool}
    `yol is None` iken `neden` ve `aranan` DOLUDUR — "bulunamadı" tek başına
    eyleme geçirilebilir bilgi değildir.
    """
    if arac not in ARACLAR:
        raise KeyError(f"tanimsiz arac {arac!r}; bilinenler: {sorted(ARACLAR)}")
    t = ARACLAR[arac]
    dizin = bool(t.get("dizin"))
    aranan: list[str] = []

    ev = os.environ.get(t["env"])
    if ev:
        aranan.append(f"{t['env']}={ev}")
        if _uygun(ev, dizin):
            return {"arac": arac, "yol": str(Path(ev)), "kaynak": "ENV",
                    "aranan": aranan, "neden": None, "zorunlu": t.get("zorunlu", True)}

    for isim in t.get("path_isim", []):
        aranan.append(f"PATH:{isim}")
        w = shutil.which(isim)
        if w and _uygun(w, dizin):
            return {"arac": arac, "yol": w, "kaynak": "PATH",
                    "aranan": aranan, "neden": None, "zorunlu": t.get("zorunlu", True)}

    for v in t.get("varsayilan", []):
        aranan.append(str(v))
        if _uygun(v, dizin):
            return {"arac": arac, "yol": str(Path(v)), "kaynak": "VARSAYILAN",
                    "aranan": aranan, "neden": None, "zorunlu": t.get("zorunlu", True)}

    return {"arac": arac, "yol": None, "kaynak": None, "aranan": aranan,
            "neden": (f"{t['aciklama']} bulunamadi. {t['env']} ortam degiskenini "
                      f"ayarlayin (Docker'da tek yapilandirma noktasi budur)."),
            "zorunlu": t.get("zorunlu", True)}


def yol(arac: str) -> str | None:
    return bul(arac)["yol"]


def rapor() -> dict:
    kayit = {a: bul(a) for a in ARACLAR}
    eksik = [a for a, k in kayit.items() if k["yol"] is None and k["zorunlu"]]
    return {"platform": "windows" if WINDOWS else "posix",
            "araclar": kayit, "eksik": eksik, "hazir": not eksik}


def main() -> int:
    r = rapor()
    print(f"platform: {r['platform']}\n")
    for a, k in r["araclar"].items():
        im = "✓" if k["yol"] else ("✗" if k["zorunlu"] else "-")
        print(f"{im} {a:20} {k['kaynak'] or 'YOK':11} {k['yol'] or ''}")
        if not k["yol"]:
            print(f"    arandi: {', '.join(k['aranan']) or '(hicbir yer)'}")
            print(f"    {k['neden']}")
    print(f"\nhazir: {r['hazir']}" + (f"  eksik: {r['eksik']}" if r["eksik"] else ""))
    if "--json" in sys.argv:
        Path(__file__).with_name("dis_araclar.json").write_text(
            json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("-> dis_araclar.json")
    return 0 if r["hazir"] else 1


if __name__ == "__main__":
    sys.exit(main())
