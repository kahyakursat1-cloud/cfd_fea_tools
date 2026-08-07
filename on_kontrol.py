"""Ön-kontrol (doctor) — "ortamım gerçekten analiz koşacak durumda mı?" tek kapıdan.

Bu bilgi eskiden üç yere dağılmıştı (launcher GUI rozeti, verify_system.py, check_*.py) ve
hiçbiri ÇÖZÜCÜNÜN GERÇEKTEN KULLANDIĞI yolu denemiyordu. Buradaki kontroller
`analysis.backend` üzerinden geçer: CFD_BACKEND=wsl|docker hangisiyse o denenir. Amaç,
mühendisin saatlik bir koşuyu başlatmadan ÖNCE eksiği görmesi.

    python on_kontrol.py          # veya: python pipeline.py doctor
Çıkış kodu: 0 = analiz koşabilir, 1 = zorunlu bileşen eksik.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

# pyproject'te ZORUNLU olan her paket burada da olmalı. `rtree` eksikti: yokluğunda
# ray-tabanlı et-kalınlığı ölçümü sessizce bbox yedeğine düşüyor ve çağıran bunu ÖLÇÜM
# sanıyordu (MiniHawk'ta "ince özellik 80 mm" aslında gövde çapıydı).
ZORUNLU_PY = ["numpy", "scipy", "matplotlib", "trimesh", "gmsh", "yaml",
              "rtree", "shapely", "mapbox_earcut", "manifold3d",
              # psutil: kuyruk kilidinin sahibi PID hala yasiyor mu. Yoksa
              # "sorulamadi" donulur ve BAYAT KILIT DEVRALINMAZ — makine
              # kapanmasindan sonra kuyruk kalici bloke kalir.
              "psutil"]
SECMELI_PY = {"PySide6": "GUI (app_analyzer / launcher)",
              "pandas": "tablo/rapor yardımcıları",
              "plotly": "etkileşimli figürler"}


def _py_modul(ad: str) -> bool:
    try:
        return importlib.util.find_spec(ad) is not None
    # sessiz-yutma: kabul — soru "modul kurulu mu"; find_spec bozuk/kismi
    # kurulumda atar ve o da "kullanilamaz" demektir. Cagiran zaten eksigi
    # kurulum raporunda gosteriyor, yani sonuc gorunur.
    except (ImportError, ValueError):
        return False


def _linux_komut(bash_cmd: str, timeout: int = 60):
    """Çözücünün kullandığı arka uçta komut koş; (rc, cikti) döner, rc=None → ulaşılamadı."""
    from analysis.backend import linux_run
    try:
        r = linux_run(bash_cmd, timeout)
        return r.returncode, (r.stdout or "").strip()
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def kontroller() -> list[dict]:
    """Her kontrol: {ad, durum: 'ok'|'eksik'|'uyari', detay, zorunlu}"""
    from analysis.backend import backend, container

    out = []
    _NEDEN = {
        "rtree": "yoksa et-kalınlığı ölçümü sessizce bbox yedeğine düşer "
                 "(ince-özellik uyarıları ölçüme değil kutuya dayanır)",
        "shapely": "yoksa NACA profil ekstrüzyonu düşer ve kanat DÜZ KUTU olur — "
                   "tüm aerodinamik sonuç profili temsil etmez",
        "mapbox_earcut": "yoksa kanat kesit kapakları üçgenlenemez, geometri açık kalır",
        "manifold3d": "yoksa katı boolean birleşim düşer; kanat/gövde/kuyruk AYRI "
                      "cisimler kalır ve STL su-geçirmez olmaz",
    }
    for m in ZORUNLU_PY:
        var = _py_modul(m)
        out.append({"ad": f"python: {m}", "zorunlu": True,
                    "durum": "ok" if var else "eksik",
                    "detay": "" if var else
                             (f"pip install {m} — {_NEDEN[m]}" if m in _NEDEN
                              else "pip install -e .")})
    for m, nicin in SECMELI_PY.items():
        var = _py_modul(m)
        out.append({"ad": f"python: {m}", "zorunlu": False,
                    "durum": "ok" if var else "uyari",
                    "detay": "" if var else f"yok — {nicin} çalışmaz"})

    bk = backend()
    ek = f" (konteyner: {container()})" if bk == "docker" else ""
    rc, cikti = _linux_komut("echo hazir", 60)
    ulasti = rc == 0 and "hazir" in cikti
    out.append({"ad": f"linux arka uç: {bk}{ek}", "zorunlu": True,
                "durum": "ok" if ulasti else "eksik",
                "detay": "" if ulasti else f"ulaşılamadı — {cikti[:120]}"})

    if ulasti:
        rc, _ = _linux_komut("test -d /opt/openfoam11", 60)
        out.append({"ad": "OpenFOAM 11 (CFD)", "zorunlu": False,
                    "durum": "ok" if rc == 0 else "uyari",
                    "detay": "" if rc == 0 else "/opt/openfoam11 yok — CFD koşamaz (FEA çalışır)"})
        # `ccx -version` rc=201 döner ve ilk satırı boştur; varlık hükmü `which`e dayanmalı
        rc, ver = _linux_komut("which ccx >/dev/null 2>&1 && (ccx -v 2>&1 | grep -m1 -i version)",
                               60)
        bulundu = rc == 0
        out.append({"ad": "CalculiX ccx (FEA)", "zorunlu": False,
                    "durum": "ok" if bulundu else "uyari",
                    "detay": ver[:60] if bulundu else "bulunamadı — FEA koşamaz"})
    else:
        for ad in ("OpenFOAM 11 (CFD)", "CalculiX ccx (FEA)"):
            out.append({"ad": ad, "zorunlu": False, "durum": "uyari",
                        "detay": "arka uç ulaşılamadığı için denenemedi"})

    try:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            (Path(d) / "t").write_text("x")
        yazilir = True
    except Exception:
        yazilir = False
    out.append({"ad": "çalışma dizini yazılabilir", "zorunlu": True,
                "durum": "ok" if yazilir else "eksik",
                "detay": "" if yazilir else f"{Path.cwd()} yazılamıyor"})

    serbest_gb = shutil.disk_usage(Path.cwd()).free / 1e9
    yeterli = serbest_gb >= 10
    out.append({"ad": "disk alanı", "zorunlu": False,
                "durum": "ok" if yeterli else "uyari",
                "detay": f"{serbest_gb:.0f} GB serbest" + ("" if yeterli else " — case'ler GB'lar tutar")})

    if os.environ.get("CFD_EXT4") == "1" and bk != "wsl":
        out.append({"ad": "CFD_EXT4", "zorunlu": False, "durum": "uyari",
                    "detay": "yalnız wsl arka ucunda etkili — yok sayılıyor"})
    return out


def rapor(ks: list[dict]) -> str:
    im = {"ok": "✅", "uyari": "⚠️ ", "eksik": "❌"}
    sat = ["Ön-kontrol — analiz ortamı", "=" * 46]
    sat += [f"{im[k['durum']]} {k['ad']}" + (f"  — {k['detay']}" if k["detay"] else "") for k in ks]
    eksik = [k for k in ks if k["zorunlu"] and k["durum"] == "eksik"]
    uyari = [k for k in ks if k["durum"] == "uyari"]
    sat.append("-" * 46)
    if eksik:
        sat.append(f"❌ ANALİZ KOŞAMAZ — {len(eksik)} zorunlu bileşen eksik.")
    elif uyari:
        sat.append(f"⚠️  Koşabilir; {len(uyari)} yetenek kısıtlı (yukarıdaki uyarılar).")
    else:
        sat.append("✅ Ortam tam — CFD + FEA koşabilir.")
    return "\n".join(sat)


def main() -> int:
    ks = kontroller()
    print(rapor(ks))
    return 1 if any(k["zorunlu"] and k["durum"] == "eksik" for k in ks) else 0


if __name__ == "__main__":
    sys.exit(main())
