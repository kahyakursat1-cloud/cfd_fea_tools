"""Gerçek-çözücü regresyonu — gecelik/cron koşusu için tek komut + JSON verdikt.

CI'da OpenFOAM/ccx yok; `external` testler orada atlanıyor. Bu script onları YEREL
makinede (veya docker arka ucunda) koşturur ve makine-okunur bir verdikt bırakır —
böylece hattı bozan bir değişiklik ertesi sabah görülür, saatlik bir koşuda değil.

    python regresyon.py                  # tüm external testler
    python regresyon.py --hizli          # yalnız FEA (saniyeler)

Windows Görev Zamanlayıcı / cron örneği (her gece 03:00):
    python D:\\bilsem_beyin\\cfd_fea_tools\\regresyon.py

Çıkış kodu: 0 = hat sağlam, 1 = regresyon (JSON'da hangi test).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SONUC = ROOT / "regresyon_sonuc.json"
HIZLI_TEST = "tests/test_cozucu_regresyon.py::test_fea_ankastre_kiris_analitige_yakin"


def kos(hizli: bool = False) -> dict:
    hedef = HIZLI_TEST if hizli else "tests/test_cozucu_regresyon.py"
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "-m", "external", hedef,
         "-p", "no:cacheprovider", "--no-header", "-rA"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=10800,
    )
    sure = round(time.time() - t0, 1)
    satirlar = (p.stdout or "").splitlines()
    gorulen: dict[str, str] = {}     # -v satiri + -rA ozeti ayni testi iki kez verir
    for s in satirlar:
        if "::" not in s or not any(k in s for k in ("PASSED", "FAILED", "SKIPPED", "ERROR")):
            continue
        ad = s.split("::")[-1].split(" ")[0]
        gorulen[ad] = ("GECTI" if "PASSED" in s else
                       "ATLANDI" if "SKIPPED" in s else "DUSTU")
    testler = [f"{ad} -> {d}" for ad, d in gorulen.items()]
    dusen = [t for t in testler if "DUSTU" in t]
    return {
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "kapsam": "hizli (yalniz FEA)" if hizli else "tam (FEA + CFD)",
        "sure_s": sure,
        "return_code": p.returncode,
        "verdikt": "SAGLAM" if p.returncode == 0 else "REGRESYON",
        "testler": testler,
        "dusen": dusen,
        "kuyruk": (p.stdout or p.stderr or "")[-1500:] if p.returncode != 0 else "",
    }


def main() -> int:
    r = kos(hizli="--hizli" in sys.argv)
    SONUC.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[{r['verdikt']}] {r['kapsam']} — {r['sure_s']} s")
    for t in r["testler"]:
        print(f"  {t}")
    if r["dusen"]:
        print("\nDUSEN TESTLER — hat bozuldu:")
        print(r["kuyruk"])
    print(f"\n-> {SONUC.name}")
    return 0 if r["verdikt"] == "SAGLAM" else 1


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
