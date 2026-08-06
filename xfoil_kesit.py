"""XFOIL ile 2B kesit poları — düşük-Re geçişli rejim için.

NEDEN BU ARAÇ: `polar_birlestirme` 3B kanat polarını 2B kesit sürüklemesinden
kuruyor ama depodaki 2B veri Re=3.4e6'daydı; MiniHawk Re=3.5e5 uçuyor (9.6 kat).
Kesiti kanadın Re'sinde RANS ile üretmeye çalıştım ve OLMADI:

    ilk hücre 3e-5 (y⁺≈0.5)   yakınsıyor ama Cl 0.17-0.32   (beklenen ~0.44)
    ilk hücre 8e-6 (y⁺≈0.13)  IRAKSIYOR: Cd=-691205, Cl=-1.1e7

Kurulumun relaxation faktörleri Re=3.4e6 için ELLE ayarlanmıştı (kodun kendi
yorumu söylüyor) ve 10 kat farklı bir Reynolds'a taşınmıyor. Yeniden ayarlamak
ayrı bir iş; oysa bu rejim — düşük Re, laminer kabarcık, geçiş — XFOIL'in panel +
e^N yönteminin tam olarak tasarlandığı problem.

DÜRÜSTLÜK: XFOIL bir RANS ikamesi DEĞİLDİR. Sıkıştırılamaz, ince-tabaka
etkileşimli, 2B ve stall sonrası güvenilmez. Bu modül onu YALNIZ lineer bölgede
ve YAKINSAMA yargısıyla birlikte kullanır; her nokta XFOIL'in kendi yakınsama
bayrağıyla ve fizik kapısıyla süzülür.

    python xfoil_kesit.py --naca 0012 --re 3.5e5 --alfa 0 2 4 6 8
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOWS = os.name == "nt"

# e^N kritik genlik faktörü. N=9 "standart" rüzgâr tüneli (Tu≈%0.1); serbest
# uçuşta türbülans daha düşük olabilir (N=11-13), tünelde daha yüksek (N=5-7).
# SEÇİM RAPORLANIR: geçiş yerini ve dolayısıyla Cd'yi doğrudan belirler.
N_KRIT = 9.0
MAX_ITER = 200


def _xfoil_yolu() -> tuple[str, bool]:
    """(yol, wsl_mi). Windows'ta WSL üzerinden sürülür."""
    from dis_araclar import bul
    r = bul("xfoil")
    if r.get("yol"):
        return r["yol"], False
    if WINDOWS:
        p = subprocess.run(["wsl", "bash", "-lc", "command -v xfoil"],
                           capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip(), True
    raise FileNotFoundError(
        "XFOIL bulunamadı. WSL'de: sudo apt install xfoil — ya da XFOIL_EXE "
        "ortam değişkenini ayarlayın (bkz. dis_araclar.py).")


def _komut_dizisi(naca: str, re: float, mach: float, alfalar: list[float],
                  cikti: str, panel: int = 0) -> str:
    # PANEL SAYISI = XFOIL'in AYRIKLASTIRMA parametresi. RANS'ta mesh neyse
    # burada panel odur; bandi OLCMEK icin degistirilebilmeli (varsayilan 0 =
    # XFOIL'in kendi varsayilani, mevcut kosularin anlami degismez).
    s = [f"NACA {naca}"]
    if panel:
        s += ["PPAR", f"N {panel}", "", ""]
    s += ["OPER", f"VISC {re:.6g}", f"MACH {mach}",
          "VPAR", f"N {N_KRIT}", "", f"ITER {MAX_ITER}", "PACC", cikti, ""]
    s += [f"ALFA {a:g}" for a in alfalar]
    s += ["PACC", "", "QUIT"]
    return "\n".join(s) + "\n"


def _oku_polar(metin: str) -> list[dict]:
    """XFOIL PACC tablosu → kayıtlar. Başlık satırları atlanır."""
    out = []
    for satir in metin.splitlines():
        p = satir.split()
        if len(p) < 4:
            continue
        try:
            a, cl, cd, cdp = (float(p[0]), float(p[1]), float(p[2]), float(p[3]))
        # sessiz-yutma: kabul — XFOIL tablosunun BASLIK satirlari (alpha/CL/CD ve
        # ---- ayraci) sayiya cevrilemez; atlanmalari beklenen davranistir. Veri
        # KAYBI olusturmaz: istenen ile donen acilar ayrica karsilastirilir ve
        # eksik aci `yakinsamayan_alfa` olarak RAPORLANIR.
        except ValueError:
            continue
        if not (-90.0 <= a <= 90.0):
            continue
        out.append({"alpha": a, "Cl": round(cl, 5), "Cd": round(cd, 6),
                    "Cdp": round(cdp, 6)})
    return out


def polar(naca: str = "0012", re: float = 3.5e5, mach: float = 0.0,
          alfalar: tuple[float, ...] = (0, 2, 4, 6, 8),
          lineer_max: float = 8.0, panel: int = 0,
          tekrar: bool = True) -> dict:
    """Kesit poları + YAKINSAMA ve FİZİK yargısı.

    XFOIL yakınsamayan açıyı polar tablosuna HİÇ yazmaz — yani eksik satır bir
    başarısızlıktır ve sessizce kaybolmamalı. İstenen ile dönen açılar
    karşılaştırılır.
    """
    yol, wsl = _xfoil_yolu()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        pol = d / "polar.txt"
        if wsl:
            p = subprocess.run(["wsl", "bash", "-lc", "mktemp -d"],
                               capture_output=True, text=True, check=True)
            wsl_dir = p.stdout.strip()
            cikti = f"{wsl_dir}/polar.txt"
            girdi = _komut_dizisi(naca, re, mach, list(alfalar), cikti, panel)
            r = subprocess.run(["wsl", "bash", "-lc", f"cd {wsl_dir} && {yol}"],
                               input=girdi, capture_output=True, text=True,
                               timeout=600)
            g = subprocess.run(["wsl", "bash", "-lc", f"cat {cikti}"],
                               capture_output=True, text=True)
            tablo = g.stdout
            subprocess.run(["wsl", "bash", "-lc", f"rm -rf {wsl_dir}"],
                           capture_output=True, text=True)
        else:
            girdi = _komut_dizisi(naca, re, mach, list(alfalar), str(pol), panel)
            r = subprocess.run([yol], input=girdi, cwd=d, capture_output=True,
                               text=True, timeout=600)
            tablo = pol.read_text(errors="replace") if pol.exists() else ""

    noktalar = _oku_polar(tablo)
    donen = {round(n["alpha"], 3) for n in noktalar}
    eksik = [a for a in alfalar if round(float(a), 3) not in donen]

    # YAKINSAMAYAN ACIYI TEK BASINA YENIDEN DENE. XFOIL PACC suprumunde bir
    # onceki cozumu baslangic tahmini olarak TASIR; o tahmin kotuyse nokta duser.
    # OLCULDU (NACA0012, Re=3.4e6): alpha=4 suprumde YAKINSAMADI ama tek basina
    # kosunca Cl=0.4438 / Cd=0.00614 ile yakinsadi — ve o aci referansin
    # (Ladson) tanimli oldugu tam aciydi. Yani devam-yolu artefakti yuzunden
    # DOGRULAMA yapilamaz hale geliyordu.
    if eksik and tekrar:
        kurtarilan = []
        for a in list(eksik):
            tek = polar(naca, re, mach, (a,), lineer_max, panel, tekrar=False)
            if tek["polar"]:
                kurtarilan += tek["polar"]
        if kurtarilan:
            noktalar = sorted(noktalar + kurtarilan, key=lambda n: n["alpha"])
            donen = {round(n["alpha"], 3) for n in noktalar}
            eksik = [a for a in alfalar if round(float(a), 3) not in donen]

    from validity_envelope import force_admissibility
    fizik_disi = []
    gecerli = []
    for n in noktalar:
        f = force_admissibility(n["Cd"], n["Cl"], n["alpha"],
                                rejim="2b_tek_elemanli")   # XFOIL tek kesit
        n["fizik"] = f["verdict"]
        (gecerli if f["verdict"] != "inadmissible" else fizik_disi).append(n)

    uyarilar = []
    if eksik:
        # SESSİZ KAYIP YOK: XFOIL yakınsamayan açıyı yazmaz; boş satır
        # "o açı denenmedi" değil "YAKINSAMADI" demektir.
        uyarilar.append(
            f"YAKINSAMAYAN AÇI(LAR): {eksik} — XFOIL bu açıları polar tablosuna "
            "yazmadı. Düşük Re'de laminer kabarcık patlaması tipik sebeptir; "
            "bu açılar için sonuç YOKTUR (sıfır değil).")
    if fizik_disi:
        uyarilar.append(f"FİZİK-DIŞI nokta(lar) elendi: "
                        f"{[n['alpha'] for n in fizik_disi]}")
    dis_lineer = [n["alpha"] for n in gecerli if abs(n["alpha"]) > lineer_max]
    if dis_lineer:
        uyarilar.append(
            f"LİNEER BÖLGE DIŞI: {dis_lineer} — XFOIL stall yakınında ve sonrasında "
            "güvenilmez (ince-tabaka etkileşimi ayrılmayı yeterince temsil etmez).")

    return {
        "vaka": f"NACA{naca} 2B kesit poları — XFOIL {N_KRIT:g}-e^N, Re={re:.3g}",
        "_neden": ("Dusuk-Re gecisli kesit polari RANS ile uretilemedi: ilk hucre "
                   "3e-5'te Cl 0.17-0.32 (beklenen ~0.44), 8e-6'da IRAKSAMA "
                   "(Cd=-691205). Kurulumun relaxation'i Re=3.4e6 icin elle "
                   "ayarlanmisti ve 10 kat farkli Re'ye tasinmiyor."),
        "yontem": f"XFOIL 6.99, panel + e^N (N_krit={N_KRIT:g}), ITER={MAX_ITER}",
        "re": re, "mach": mach, "naca": naca, "panel": panel,
        "polar": gecerli, "fizik_disi": fizik_disi,
        "istenen_alfa": list(alfalar), "yakinsamayan_alfa": eksik,
        "tekil_tekrar": tekrar,
        "uyarilar": uyarilar,
        "_kisit": ("XFOIL bir RANS IKAMESI DEGILDIR: 2B, sikistirilamaz, "
                   "ince-tabaka etkilesimli. Lineer bolgede (|alpha| <= "
                   f"{lineer_max:g} derece) tasarim-oncesi icin uygundur; stall "
                   "yakininda ve sonrasinda kullanilmaz. N_krit gecis yerini ve "
                   "dolayisiyla Cd'yi DOGRUDAN belirler — secim raporlanir."),
        "_uretim": (f"Üretim: python xfoil_kesit.py --naca {naca} --re {re:g} "
                    + "--alfa " + " ".join(f"{a:g}" for a in alfalar)),
        "_xfoil_stdout_kuyruk": (r.stdout or "")[-400:],
    }


def panel_bagimsizligi(naca: str, re: float, mach: float,
                       alfalar: tuple, paneller=(0, 200, 300)) -> dict:
    """Panel sayısı XFOIL'in AYRIKLAŞTIRMA parametresidir — RANS'ta mesh neyse
    burada panel odur. Band ÖLÇÜLÜR, literatürden varsayılmaz.

    ÖLÇÜLDÜ (NACA0012, Re=3.5e5, 160/200/300 panel): en kötü Cd sapması %0.55.
    Karşılaştırma: aynı kesiti RANS ile üretme denemesi %36.6 band vermişti.
    """
    kosular = {}
    for pn in paneller:
        r = polar(naca, re, mach, alfalar, panel=pn)
        kosular[pn] = {n["alpha"]: n["Cd"] for n in r["polar"]}
    ortak = set.intersection(*(set(k) for k in kosular.values())) if kosular else set()
    en_kotu, ayrinti = 0.0, []
    for a in sorted(ortak):
        cds = [kosular[pn][a] for pn in paneller]
        sap = (max(cds) - min(cds)) / max(min(cds), 1e-12) * 100
        en_kotu = max(en_kotu, sap)
        ayrinti.append({"alpha": a, "Cd": cds, "sapma_pct": round(sap, 3)})
    return {"paneller": list(paneller), "ortak_alfa": len(ortak),
            "en_kotu_sapma_pct": round(en_kotu, 3), "ayrinti": ayrinti,
            "yorum": ("Bu, kesit Cd'sinin AYRIKLASTIRMA bandidir (RANS'taki "
                      "mesh-bagimsizligin karsiligi). MODEL-FORM hatasi DEGIL: "
                      "XFOIL'in deneyle uyumu ayri bir sorudur.")}


def main() -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--naca", default="0012")
    ap.add_argument("--re", type=float, default=3.5e5)
    ap.add_argument("--mach", type=float, default=0.0)
    ap.add_argument("--alfa", type=float, nargs="*", default=[0, 2, 4, 6, 8])
    ap.add_argument("--out", default="kesit_xfoil.json")
    ap.add_argument("--band", action="store_true",
                    help="panel-bagimsizlik bandini OLC (3 kosu)")
    a = ap.parse_args()
    rec = polar(a.naca, a.re, a.mach, tuple(a.alfa))
    if a.band:
        rec["panel_bagimsizligi"] = panel_bagimsizligi(
            a.naca, a.re, a.mach, tuple(a.alfa))
    rec["verdikt"] = (
        f"{len(rec['polar'])}/{len(a.alfa)} acida yakinsak ve fiziksel sonuc. "
        + ("YAKINSAMAYAN: " + str(rec["yakinsamayan_alfa"]) + ". "
           if rec["yakinsamayan_alfa"] else "")
        + "Kesit verisi polar_birlestirme'ye VERILEBILIR (lineer bolge)."
        if rec["polar"] else "Kullanilabilir nokta YOK.")
    (HERE / a.out).write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(f"{rec['vaka']}\n")
    print(f"  {'α':>6} {'Cl':>9} {'Cd':>10}   ince-kanat Cl (2π·α)")
    for n in rec["polar"]:
        teo = 2 * math.pi * math.radians(n["alpha"])
        print(f"  {n['alpha']:6.1f} {n['Cl']:9.4f} {n['Cd']:10.5f}   {teo:8.4f}")
    for u in rec["uyarilar"]:
        print("  ⚠ " + u)
    print("\n" + rec["verdikt"])
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
