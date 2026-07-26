"""Çalışma zarfı (geçerlilik sınırları) tablosu — KANITTAN üretilir, elle yazılmaz.

README'nin "Çalışma Zarfı" bölümü kök dizindeki yapılandırılmış V&V kanıt dosyalarından
türetilir. Elle yazılan tablo, kanıt yenilenince sessizce eskiyordu: README "Mesh
yakınsama ✅ GCI %0.09" derken aynı vaka için VV_report "p=4.14 asimptotik dışı —
GÖSTERİLEMEDİ" diyordu. Verdiktler burada kanonik fonksiyonlarla (report_generator:
compute_gci / gci_verdict) yeniden hesaplanır; kanıt dosyası yoksa satır sessizce
düşmez, "kanıt yok — beyan" olarak işaretlenir.

    python zarf.py           # tabloyu bas (README'ye dokunmaz)
    python zarf.py --yaz     # README.md'yi işaretçiler arasından güncelle
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from report_generator import compute_gci, gci_verdict

ROOT = Path(__file__).resolve().parent
BASLANGIC = "<!-- ZARF:BASLANGIC — `python zarf.py --yaz` uretir, elle duzenleme -->"
BITIS = "<!-- ZARF:SON -->"

BEYAN = "beyan — kanıt dosyası yok"


def _json(ad: str) -> dict:
    return json.loads((ROOT / ad).read_text(encoding="utf-8"))


def _airfoil_cd() -> tuple[str, str]:
    d = _json("tmr_gci_verdict.json")
    g = d["gci"]
    ref = d["TMR_referans_SST_alpha0"]
    sapma = abs(d["Cd_richardson"] - ref) / ref * 100
    guv = "✅ Yüksek" if d["strict_gci_verdict"].startswith("✅") else "⚠️ Şartlı"
    return guv, (f"NASA TMR NACA0012 α=0°: GCI %{g['gci_fine_pct']:.1f} "
                 f"(p={g['p']}), TMR sapması %{sapma:.1f}")


def _arac_mesh() -> tuple[str, str]:
    lv = _json("mesh_independence.json")["levels"]
    h = [x["h"] for x in lv]
    cd = [x["Cd"] for x in lv]
    g = compute_gci(h[0], h[1], h[2], cd[0], cd[1], cd[2])
    if g is None:
        return "⚠️ Belirsiz", "GCI hesaplanamadı (seviyeler ayırt edilemiyor)"
    v = gci_verdict(g)
    guv = "✅" if v.startswith("✅") else "⚠️ Gösterilemedi"
    return guv, (f"MiniHawk 3D snappyHexMesh: GCI %{g['gci_fine_pct']:.2f}, "
                 f"p={g['p']} ({'asimptotik' if g['p_in_range'] else 'asimptotik aralık DIŞI'})")


def _kup_arac_gci() -> tuple[str, str]:
    d = _json("gci_kup_arac.json")
    g, ref = d["gci"], d["referans"]["Cd"]
    asimptotik = g["p_in_range"] and g["monotonic"]
    guv = "✅ Yüksek" if g["gci_fine_pct"] < 5 else "⚠️ Bantlı"
    return guv, (f"Küp (Hoerner {ref}): Cd={d['Cd_ince']:.3f} → sapma %{d['literatur_sapma_pct']}, "
                 f"GCI %{g['gci_fine_pct']:.1f} (p={g['p']}, "
                 f"{'asimptotik' if asimptotik else 'asimptotik DIŞI'})")


def _arac_bandi() -> tuple[str, str]:
    b = _json("validation_band.json")
    p = [f"{vaka} %{max(m.values()):.1f}" for vaka, m in b.items() if isinstance(m, dict) and m]
    return ("⚠️ Bantlı", "Ölçülen validasyon bandı — " + ", ".join(p)) if p else \
           ("⚠️ Bantlı", "validation_band.json boş")


def _kiris() -> tuple[str, str]:
    d = _json("fea_validation.json")
    return "✅ Çok yüksek", (f"Ankastre kiriş ↔ Euler-Bernoulli: sehim %{d['sehim']['hata_pct']}, "
                            f"gerilme %{d['gerilme']['hata_pct']}")


def _kt() -> tuple[str, str]:
    d = _json("fea_validation_hole.json")
    return "✅ Yüksek", (f"Delikli plaka Kt ↔ Heywood: tepe gerilme %{d['fem']['hata_pct']} "
                        f"(C3D10, {d['fem']['eleman_C3D10']} eleman)")


SATIRLAR = [
    ("Bağlı akış, 2D airfoil mutlak $C_d$ (M<0.3)", _airfoil_cd),
    ("3D araç mesh yakınsama (snappyHexMesh)", _arac_mesh),
    ("3D künt cisim — araç hattı GCI + literatür", _kup_arac_gci),
    ("3D araç $C_d$ — V&V/UQ bandı", _arac_bandi),
    ("Yapısal — lineer statik (kiriş)", _kiris),
    ("Yapısal — gerilme konsantrasyonu ($K_t$)", _kt),
    ("Stall / $C_{L,max}$", None),
    ("y⁺<1 transition / ayrılmış akış", None),
]

BEYANLAR = {
    "Stall / $C_{L,max}$": ("⚠️ ±2-3°, ±%15 (RANS)", BEYAN),
    "y⁺<1 transition / ayrılmış akış": ("❌ Kapsam dışı", f"{BEYAN}; C-grid / DES gerekir"),
}


def zarf_tablosu() -> str:
    sat = ["| Koşul | Güvenilirlik | Kanıt |", "|-------|--------------|-------|"]
    for kosul, fn in SATIRLAR:
        if fn is None:
            guv, kanit = BEYANLAR[kosul]
        else:
            try:
                guv, kanit = fn()
            except FileNotFoundError as e:
                guv, kanit = "❓ Kanıt yok", f"`{Path(str(e.filename)).name}` bulunamadı"
            except (KeyError, ValueError, TypeError) as e:
                guv, kanit = "❓ Okunamadı", f"kanıt dosyası şema dışı ({type(e).__name__})"
        sat.append(f"| {kosul} | {guv} | {kanit} |")
    return "\n".join(sat)


def readme_guncelle() -> bool:
    p = ROOT / "README.md"
    metin = p.read_text(encoding="utf-8")
    if BASLANGIC not in metin or BITIS not in metin:
        print(f"HATA: README.md içinde işaretçiler yok:\n  {BASLANGIC}\n  {BITIS}")
        return False
    bas = metin.index(BASLANGIC) + len(BASLANGIC)
    son = metin.index(BITIS)
    yeni = metin[:bas] + "\n" + zarf_tablosu() + "\n" + metin[son:]
    if yeni == metin:
        print("README.md güncel — değişiklik yok.")
        return True
    p.write_text(yeni, encoding="utf-8")
    print("README.md çalışma zarfı tablosu güncellendi.")
    return True


if __name__ == "__main__":
    if "--yaz" in sys.argv:
        sys.exit(0 if readme_guncelle() else 1)
    print(zarf_tablosu())
