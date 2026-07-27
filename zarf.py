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
    # utf-8-sig: PowerShell ile üretilen kanıt dosyaları BOM taşır (mesh_quality.json,
    # overnight_summary.json ölçüldü). Düz "utf-8" bunlarda JSONDecodeError verir;
    # -sig hem BOM'lu hem BOM'suz dosyayı okur (üst küme).
    return json.loads((ROOT / ad).read_text(encoding="utf-8-sig"))


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
    lsr = d.get("lsr") or {}
    yakinsadi = g["gci_fine_pct"] < 5 and g["p_in_range"] and g["monotonic"]
    # LSR tüm seviyelere bakar; Richardson yalnız en ince üçe. Ayrıştıklarında
    # ÇELİŞKİ gizlenmez — bant, çelişkiyi taşıyan tarafın hükmüyle sunulur.
    lsr_itiraz = lsr and not lsr.get("guvenilir", True)
    guv = ("⚠️ Bantlı" if (not yakinsadi or lsr_itiraz) else "✅ Yüksek")
    s = (f"Küp (Hoerner {ref}): Cd={d['Cd_ince']:.3f} → sapma %{d['literatur_sapma_pct']}, "
         f"Richardson GCI %{g['gci_fine_pct']:.1f} (p={g['p']}, "
         f"{'asimptotik' if yakinsadi else 'asimptotik DIŞI'})")
    if lsr_itiraz:
        s += f"; ancak {lsr['n']}-seviye LSR U=%{lsr['u_pct']:.0f} (asimptotik-altı)"
    return guv, s


def _tasima_a8() -> tuple[str, str]:
    """Taşıma (Cl) α=8° — zarfın 'bağlı akış α≤8° ✅' iddiasının doğrudan kanıtı.

    Bilerek HAM VERİDEN hesaplanır: dosyadaki düzyazı `sonuc` alanı Richardson
    ekstrapolasyonunun TMR'ye uyumunu öne çıkarıyor, oysa seri ıraksadığı için o
    ekstrapolasyon anlamsız. Savunulabilir sayı EN İNCE gridin değeridir.
    """
    d = _json("tmr_gci_verdict_a8.json")
    ince = max(d["seviyeler"], key=lambda x: x["cells"])
    ref = d["TMR_referans"]["Cl"]
    sapma = abs(ince["Cl"] - ref) / ref * 100
    p = d["gci"]["p"]
    yakinsak = d["gci"]["p_in_range"]
    guv = "✅ Yüksek" if (sapma < 5 and yakinsak) else "⚠️ Bantlı"
    return guv, (f"NASA TMR NACA0012 α=8°: en ince grid ({ince['cells']:,} hücre) "
                 f"Cl={ince['Cl']:.4f} vs TMR {ref} → sapma %{sapma:.1f}; "
                 f"ancak 3-grid serisi ıraksıyor (p={p}) → sayısal belirsizlik "
                 "Richardson ile ölçülemedi")


def _minihawk_gci() -> tuple[str, str]:
    """MiniHawk (ince kanat) — İKİ kampanya, iki AYRI darboğaz. İkisi de raporlanır:
    ilerleme gizlenmez, ama yakınsamadığı da yumuşatılmaz."""
    a = _json("gci_minihawk_arac.json")          # standart
    b = _json("gci_minihawk_hassas_nl.json")     # hassas_nl
    gb = b["gci"]
    ince = max(b["seviyeler"], key=lambda x: x["cells"])
    yp = (b.get("yplus") or {}).get("ort")
    c = _json("gci_minihawk_hassas.json")          # katmanlı deneme
    return "❌ Geçersiz geometri", (
        "⚠ Bu üç kampanya kanadı DÜZ KUTU olan bir STL üzerinde koşuldu (shapely "
        "kurulu olmadığı için NACA ekstrüzyonu sessizce kutuya düşüyordu; 2026-07-27'de "
        "düzeltildi) — aerodinamik sayılar NACA2412'yi TEMSİL ETMEZ, yeniden koşulmalı. "
        "Mesh-yakınsama dersleri geçerli: "
        f"(%{a['gci']['gci_fine_pct']:.0f} → %{gb['gci_fine_pct']:.0f}). "
        "GERÇEK ölçümle (rtree kurulduktan sonra) kanat hiçbir seviyede çözülmedi: "
        "yığın kalınlık/hücre standart 1.32×, hassas 3.39× — hedef ≥6. "
        "En ince özellik (firar kenarı ~2 mm) yüzey hücresinin 0.20 katı → 12 prizma "
        f"katmanı ÖRÜLEMEDİ (mesh katmansızla birebir aynı, y⁺={yp:.0f}). "
        f"Cd={c['Cd_ince']:.4f} yalnız basınç bileşeni; bu geometride snappy ile "
        "duvar-çözünür yol KAPALI")


def _minihawk_v2() -> tuple[str, str]:
    """İlk DOĞRU-GEOMETRİ koşusu (gerçek NACA2412 kanat)."""
    d = _json("gci_minihawk_v2_profil.json")
    kk = d["kutu_kanat_kiyasi"]
    yp = (d.get("yplus") or {}).get("ort")
    return "⚠️ Yalnız eğilim", (
        f"MiniHawk gerçek NACA2412 kanatla (ilk kez): Cd={d['Cd']:.4f} ± %{d['fark_pct']:.0f} "
        f"(2 seviye vekil bant; 'orta' seviye mesh kapısında reddedildi). "
        f"Kutu-kanat hatası Cd'yi %{abs(kk['fark_pct']):.0f} yüksek, y⁺'yi 8× büyük "
        f"gösteriyordu (y⁺ {kk['yplus_kutu']:.0f}→{yp:.0f}). "
        f"Cl={d['Cl']:.4f} oysa NACA2412 α=0'da ~0.25 — kamburluk ÇÖZÜLMÜYOR: en ince "
        "boyut yüzey hücresinin 0.6 katı (hedef ≥6)")


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


def _duz_levha() -> tuple[str, str]:
    """Cilt-sürtünmesinin y⁺'ye duyarlılığı — MiniHawk'ın NİTEL uyarısının NİCEL karşılığı."""
    d = _json("duz_levha_cf.json")
    ok = [s for s in d["seviyeler"] if s["durum"] == "ok"]
    bant = [s for s in ok if s["ilk_hucre_delta99"] <= 1.0]
    asiri = [s for s in ok if s["ilk_hucre_delta99"] > 1.0]
    en_kotu_bant = max(abs(s["hata_pct"]) for s in bant)
    ek = ""
    if asiri:
        k = max(asiri, key=lambda s: abs(s["hata_pct"]))
        ek = (f"; ilk hücre {k['ilk_hucre_delta99']:.1f}·δ99 olunca (y⁺≈"
              f"{s_yp(k):.0f}) hata %{k['hata_pct']:+.0f}")
    return "✅ Yüksek", (f"Düz levha $C_f$ ↔ Schlichting 1/7-kuvvet: ilk hücre ≤δ99 iken "
                        f"hata ≤%{en_kotu_bant:.0f} ({len(bant)} seviye){ek}")


def s_yp(s: dict) -> float:
    return s.get("yplus_olculen") or s["yplus_hedef"]


SATIRLAR = [
    ("Bağlı akış, 2D airfoil mutlak $C_d$ (M<0.3)", _airfoil_cd),
    ("Bağlı akış, 2D airfoil taşıma $C_l$ (α=8°)", _tasima_a8),
    ("3D araç mesh yakınsama (snappyHexMesh)", _arac_mesh),
    ("3D ince-kanatlı İHA — araç hattı GCI", _minihawk_gci),
    ("3D İHA, gerçek NACA kanat (ilk doğru geometri)", _minihawk_v2),
    ("3D künt cisim — araç hattı GCI + literatür", _kup_arac_gci),
    ("3D araç $C_d$ — V&V/UQ bandı", _arac_bandi),
    ("Cilt sürtünmesi $C_f$ — y⁺ duyarlılığı (2D düz levha)", _duz_levha),
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
