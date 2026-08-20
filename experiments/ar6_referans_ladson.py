"""AR6 kanat çapası — referansı YARI-ANALİTİKTEN ÖLÇÜLMÜŞE taşı.

MEVCUT DURUM. `naca0012_wing_ar6` referansı tümüyle analitik: düz-plaka Cf +
form faktörü ile profil sürüklemesi, üstüne lifting-line indüklenen sürükleme,
ilan edilen belirsizlik ±%15. u_D bu kadar büyük olunca ağ ne kadar
inceltilirse inceltilsin u_val %15'in altına inemez ve model hatası AYRILAMAZ.

BU BETİĞİN YAPTIĞI. Referansı İKİ TERİME ayırır ve baskın olanı ölçüme bağlar:
    Cd = cd_profil(cl)          ← LADSON (ölçülmüş, 2B kesit)
       + CDi = CL²/(π·e·AR)     ← lifting-line (modellenmiş)

Ladson noktaları depoda ZATEN kayıtlı (naca0012_re_eslesme.json): Re=6e6'da
α=0 → cd 0,0082 · α=4 → cl 0,452, cd 0,0092 · α=8 → cl 0,862, cd 0,0132.
O dosya ayrıca referans KOŞULUNU da ölçmüş ve "Re6e6" demiş — yani hangi
Reynolds'a ait olduğu varsayım değil, ölçüm.

SONLU KANAT DÜZELTMESİ ZORUNLU. Ladson 2B kesittir; AR=6 kanat aynı geometrik
α'da daha AZ taşır (downwash). Kesit taşıma eğimi Ladson'ın kendi iki
noktasından türetilir, literatürden varsayılmaz.

u_D NEREDEN GELİYOR. İki bileşen ayrı ayrı:
  · profil terimi — iki ölçülmüş nokta arasında interpolasyon; Ladson'ın kendi
    deneysel belirsizliği BU DEPODA DOĞRULANMADI, o yüzden profil tarafına
    belirsizlik YAZILMAZ ve bu AÇIKÇA söylenir (alt sınır).
  · indüklenen terim — açıklık verimi e'nin makul aralığı üzerinden ÖLÇÜLÜR:
    dikdörtgen AR=6 kanatta e ≈ 0,90–0,95 (δ≈0,05 → e=1/(1+δ)).

    python experiments/ar6_referans_ladson.py
Çıktı: ar6_referans_ladson.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent

AR = 6.0
ALPHA_DEG = 4.0
E_ALT, E_UST = 0.90, 0.952        # dikdörtgen AR=6 açıklık verimi bandı
E_NOM = 0.5 * (E_ALT + E_UST)


def _ladson_noktalari() -> list[dict]:
    """Depoda kayıtlı Ladson referans noktaları (Re=6e6 hücrelerinden)."""
    p = KOK / "naca0012_re_eslesme.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    return [{"alpha": h["alpha"], "cl": h["Cl_ref"], "cd": h["Cd_ref"]}
            for h in d.get("hucreler", [])
            if h.get("re") == "Re6e6" and h.get("Cd_ref")]


def _cd_profil(cl: float, nok: list[dict]) -> float:
    """cl'de profil sürüklemesi — ölçülmüş noktalar arasında interpolasyon."""
    s = sorted(nok, key=lambda x: x["cl"])
    for a, b in zip(s, s[1:]):
        if a["cl"] <= cl <= b["cl"]:
            f = (cl - a["cl"]) / (b["cl"] - a["cl"])
            return a["cd"] + f * (b["cd"] - a["cd"])
    return s[-1]["cd"] if cl > s[-1]["cl"] else s[0]["cd"]


def _cd_toplam(e: float, nok: list[dict]) -> dict:
    # KESIT TASIMA EGIMI LADSON'IN KENDI NOKTALARINDAN. Literaturden 2*pi
    # varsaymak, olculmus bir kaynak elde varken gereksiz bir model katmani
    # eklerdi.
    a4 = next(x for x in nok if x["alpha"] == 4)
    a0_rad = a4["cl"] / math.radians(4.0)
    # Prandtl sonlu-kanat duzeltmesi
    a = a0_rad / (1.0 + a0_rad / (math.pi * e * AR))
    cl_wing = a * math.radians(ALPHA_DEG)
    cdi = cl_wing ** 2 / (math.pi * e * AR)
    cdp = _cd_profil(cl_wing, nok)
    return {"e": e, "a0_rad": a0_rad, "a_rad": a, "CL": cl_wing,
            "CDi": cdi, "cd_profil": cdp, "Cd": cdp + cdi}


def main() -> int:
    nok = _ladson_noktalari()
    if len(nok) < 2:
        print("Ladson noktaları okunamadı (naca0012_re_eslesme.json)")
        return 1

    nom = _cd_toplam(E_NOM, nok)
    alt = _cd_toplam(E_UST, nok)      # yuksek e -> DUSUK CDi
    ust = _cd_toplam(E_ALT, nok)      # dusuk e  -> YUKSEK CDi
    yayilim_pct = 100.0 * (ust["Cd"] - alt["Cd"]) / nom["Cd"]

    eski_cd, eski_u = 0.020, 15.0
    rec = {
        "vaka": "AR6 kanat çapası — referans YARI-ANALİTİKTEN ÖLÇÜLMÜŞE taşındı",
        "_tarih": "2026-08-19",
        "kaynak": ("Ladson, C. L., NASA TM-4074 (1988) — Langley Düşük-Türbülanslı "
                   "Basınçlı Tünel, NACA 0012, tripped, Re=6e6. NASA TMR bu seti "
                   "'fully turbulent CFD kuvvetleriyle kıyas için en uygun' diyor."),
        "_kosul_olculdu": ("Referansın hangi Reynolds'a ait olduğu VARSAYIM DEĞİL: "
                           "naca0012_re_eslesme.json iki adayı (3e6/6e6) ölçüp "
                           "'Re6e6' demiş."),
        "ladson_noktalari": nok,
        "yontem": {
            "kesit_tasima_egimi": ("Ladson'ın KENDİ α=4 noktasından: "
                                   f"a0 = {nom['a0_rad']:.4f} /rad "
                                   f"({nom['a0_rad'] * math.pi / 180:.5f} /derece)"),
            "sonlu_kanat": ("Prandtl: a = a0/(1 + a0/(π·e·AR)) — Ladson 2B kesittir, "
                            "AR=6 kanat aynı geometrik α'da downwash yüzünden daha "
                            "AZ taşır. Bu düzeltme ZORUNLU."),
            "profil_terimi": "ölçülmüş iki nokta arasında interpolasyon",
            "induklenen_terim": "CDi = CL²/(π·e·AR) — MODELLENMİŞ",
        },
        "nominal": {k: (round(v, 6) if isinstance(v, float) else v)
                    for k, v in nom.items()},
        "e_duyarliligi": {
            "band": [E_ALT, E_UST],
            "_neden": ("Dikdörtgen AR=6 kanatta açıklık verimi; δ≈0,05 → "
                       "e=1/(1+δ)≈0,952 üst uç, 0,90 muhafazakâr alt uç."),
            "Cd_e_dusuk": round(ust["Cd"], 6), "Cd_e_yuksek": round(alt["Cd"], 6),
            "yayilim_pct": round(yayilim_pct, 2),
        },
        "u_D": {
            "deger_pct": round(yayilim_pct, 2),
            "sinif": ("ALT SINIR — YALNIZ indüklenen terimin model belirsizliğini "
                      "(e bandı) kapsar. Ladson'ın DENEYSEL belirsizliği bu depoda "
                      "doğrulanmadı, o yüzden profil tarafına belirsizlik "
                      "YAZILMADI. Gerçek u_D bundan BÜYÜKTÜR."),
        },
        "kiyas": {
            "eski_Cd": eski_cd, "eski_u_D_pct": eski_u,
            "yeni_Cd": round(nom["Cd"], 6), "yeni_u_D_pct": round(yayilim_pct, 2),
            "Cd_degisimi_pct": round(100 * (nom["Cd"] - eski_cd) / eski_cd, 1),
        },
        "verdikt": (
            f"Referans {eski_cd} (±%{eski_u:.0f}, tümüyle analitik) → "
            f"{nom['Cd']:.5f} (±%{yayilim_pct:.1f}, profil terimi ÖLÇÜLMÜŞ). "
            f"Baskın terim artık Ladson'dan geliyor; kalan belirsizlik yalnız "
            f"indüklenen terimin e bandından. u_D %{eski_u:.0f} → "
            f"%{yayilim_pct:.1f}, yani ağ inceltmesi ARTIK ANLAMLI: u_val'in "
            f"tabanı %{eski_u:.0f} değil %{yayilim_pct:.1f}."),
    }
    (KOK / "ar6_referans_ladson.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    print("Ladson (Re=6e6) noktaları:")
    for x in nok:
        print(f"  α={x['alpha']:>2}°  cl={x['cl']:.3f}  cd={x['cd']:.4f}")
    print(f"\nkesit taşıma eğimi a0 = {nom['a0_rad']:.4f} /rad")
    print(f"AR=6 (e={E_NOM:.3f}) → a = {nom['a_rad']:.4f} /rad,  "
          f"CL(α=4°) = {nom['CL']:.4f}")
    print(f"  profil cd(cl={nom['CL']:.3f}) = {nom['cd_profil']:.5f}  [ÖLÇÜLMÜŞ]")
    print(f"  CDi                        = {nom['CDi']:.5f}  [modellenmiş]")
    print(f"  toplam Cd                  = {nom['Cd']:.5f}")
    print(f"\ne bandı {E_ALT}-{E_UST} → Cd {alt['Cd']:.5f}..{ust['Cd']:.5f} "
          f"(yayılım %{yayilim_pct:.2f})")
    print(f"\n{rec['verdikt']}")
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
