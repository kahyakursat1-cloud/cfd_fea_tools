"""Δ_entegrasyon — 3B RANS ile kanat-birleştirmesi arasındaki fark.

NE ÖLÇÜLÜYOR: birleştirici Cd'yi KANAT için kuruyor (2B kesit profil sürüklemesi
+ kuramsal indüklenen direnç). 3B RANS ise TÜM aracı çözüyor. Fark, adı sık sık
"girişim sürüklemesi" konan terim — ama BURADA ÖYLE DEĞİL:

    Δ = Cd_RANS(tüm araç) − Cd_birleştirme(yalnız kanat)
      = GÖVDE parazit + KUYRUK parazit + girişim

RANS geometrisi ölçüldü (vehicle_runs/minihawk.stl): iki bileşen — gövde+kanat
birleşik gövde (0.56×1.50×0.08 m) ve yatay kuyruk (açıklık 0.667 m). Yani fark
girişimden ibaret değil; ismini böyle koymak, modellenmemiş iki bileşeni
girişim diye yutmak olurdu.

İKİ REFERANS ALANI FARKLI: RANS 0.775 m² (planform), birleştirme 0.45 m² (kanat
alanı). Ortak tabana çevrilmeden çıkarılan fark ANLAMSIZDIR — daha önce tam bu
1.72 katlık uyumsuzluk yüzünden Δ çıkarılamamıştı.

BAĞIMSIZ BÜYÜKLÜK KESTİRİMİ: düz-levha türbülanslı sürtünmesi ıslak alan
üzerinden Δ'nın mertebesini verir. Ölçülen değer bu mertebeden çok saparsa
sayıya değil ölçüme bakılır.

    python experiments/delta_entegrasyon.py
Çıktı: delta_entegrasyon.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

HIZ = 15.0
NU = 1.5e-5
# Islak alan kestirimi icin sekil (form) faktoru — ince govde/kuyruk icin
# tipik 1.2-1.4 araligi; ORTA deger alinir ve KESTIRIM oldugu yazilir.
FORM_FAKTORU = 1.3


def _rans() -> dict:
    d = json.loads((KOK / "gci_minihawk_arac.json").read_text(encoding="utf-8"))
    return {"Cd": d["Cd"], "Cl": d["Cl"], "aref": d["aref_m2"],
            "aref_mode": d.get("aref_mode"), "gci": d.get("gci") or {},
            "yplus": d.get("yplus") or {}, "verdikt": d.get("verdikt", "")}


def _birlestirme() -> dict:
    import polar_birlestirme as pb
    d = pb._depo_verisi()
    o = pb.birlesik_polar(
        d["vlm_polar"], d["kesit"], re_kanat=d["re_kanat"], re_kesit=d["re_kesit"],
        kesit_cd_mesh_bagimsiz=d["kesit_cd_mesh_bagimsiz"],
        kesit_cd_band_pct=d.get("kesit_cd_band_pct"),
        vlm_band_pct=d.get("vlm_band_pct"),
        vlm_band_kaynagi=d.get("vlm_band_kaynagi"),
        kesit_profili=d.get("kesit_profili"), arac_profili=d.get("arac_profili"),
        vlm_ar=d.get("vlm_ar"), vlm_taper=d.get("vlm_taper"),
        vlm_ok_acisi=d.get("vlm_ok_acisi"), band_ailesi=d.get("band_ailesi"),
        band_kaynak_dosyasi=d.get("band_kaynak_dosyasi"),
        taper_kaniti=d.get("taper_kaniti"),
        **{k: d[k] for k in ("kesit_simetrik", "vlm_simetrik")
           if d.get(k) is not None})
    from aircraft_geometry import AircraftLibrary
    ac = AircraftLibrary().get_template("mini_hawk")()
    n0 = next((n for n in o["noktalar"] if abs(n["alpha"]) < 1e-9), None)
    return {"nokta": n0, "engeller": o["engeller"], "sref": ac.wing.area,
            "arac": ac}


def _islak_alan_kestirimi(ac) -> dict:
    """Govde + yatay kuyruk islak alani ve duz-levha parazit Cd kestirimi."""
    fus, emp = ac.fuselage, ac.empennage
    s_govde = math.pi * fus.diameter * fus.length          # silindir yaklasimi
    s_kuyruk = 2.0 * (emp.h_area + emp.v_area) if emp else 0.0
    s_islak = s_govde + s_kuyruk
    re_l = HIZ * fus.length / NU
    cf = 0.074 / re_l ** 0.2                                # turbulanslı duz levha
    return {"s_govde_m2": round(s_govde, 5), "s_kuyruk_m2": round(s_kuyruk, 5),
            "s_islak_m2": round(s_islak, 5), "Re_L": round(re_l, 1),
            "Cf": round(cf, 6), "form_faktoru": FORM_FAKTORU,
            "Cd_parazit_kestirimi": round(cf * s_islak / ac.wing.area
                                          * FORM_FAKTORU, 6)}


def calistir() -> dict:
    r = _rans()
    b = _birlestirme()
    ac = b["arac"]
    sref = b["sref"]

    engeller: list[str] = []
    if b["engeller"]:
        engeller.append("BIRLESTIRME MUTLAK Cd VERMIYOR: "
                        + " | ".join(e.split(":")[0] for e in b["engeller"]))
    if not b["nokta"] or "Cd_toplam" not in (b["nokta"] or {}):
        engeller.append("alpha=0 noktasinda birlestirme Cd'si YOK")

    # REFERANS ALANI ORTAK TABANA CEVRILIR. Cd*S bir kuvvet katsayisidir;
    # tabani degistirmek carpim SABIT kalacak sekilde yapilir.
    olcek = r["aref"] / sref
    cd_rans_kanat_tabani = r["Cd"] * olcek

    gci_pct = float(r["gci"].get("gci_fine_pct") or 0.0)
    monoton = bool(r["gci"].get("monotonic"))
    yplus_ort = float(r["yplus"].get("ort") or 0.0)

    rec = {
        "vaka": ("Δ_entegrasyon — 3B RANS (tum arac) eksi kanat birlestirmesi, "
                 f"V={HIZ:g} m/s, alpha=0"),
        "_ne_olculuyor": ("Fark GIRISIM DEGIL: RANS geometrisi govde+kanat ve "
                          "yatay kuyruk iceriyor, birlestirme ise YALNIZ kanat. "
                          "Delta = govde parazit + kuyruk parazit + girisim."),
        "referans_alani": {"rans_m2": r["aref"], "rans_mode": r["aref_mode"],
                           "birlestirme_m2": sref, "olcek": round(olcek, 5),
                           "_neden": ("Ortak tabana cevrilmeden cikarilan fark "
                                      "anlamsizdir; 1.72 katlik bu uyumsuzluk "
                                      "daha once Delta'nin cikarilmasini "
                                      "engellemisti.")},
        "rans": {"Cd_kendi_tabani": r["Cd"], "Cd_kanat_tabani":
                 round(cd_rans_kanat_tabani, 6), "Cl": r["Cl"],
                 "gci_fine_pct": gci_pct, "monoton": monoton,
                 "yplus_ort": yplus_ort},
        "birlestirme": b["nokta"],
        "islak_alan": _islak_alan_kestirimi(ac),
    }

    if not engeller:
        cd_b = b["nokta"]["Cd_toplam"]
        delta = cd_rans_kanat_tabani - cd_b
        band_b = cd_b * (b["nokta"].get("Cd_band_pct", 0.0) / 100.0)
        band_r = cd_rans_kanat_tabani * (gci_pct / 100.0)
        band_d = (band_r ** 2 + band_b ** 2) ** 0.5
        kestirim = rec["islak_alan"]["Cd_parazit_kestirimi"]
        rec["delta"] = {
            "deger": round(delta, 6), "band": round(band_d, 6),
            "band_pct": round(band_d / abs(delta) * 100, 1) if delta else None,
            "band_paylari": {"rans": round(band_r, 6),
                             "birlestirme": round(band_b, 6)},
            "kestirime_orani": round(delta / kestirim, 2) if kestirim else None,
        }

    # KAPILAR — Delta'nin KULLANILABILIR olmasi icin RANS'in savunulabilir
    # olmasi gerekir; RANS'in kendi verdikti bunu zaten reddediyor.
    # KOK NEDEN VARSA ONCE O SOYLENIR. "GCI yuksek" bir BELIRTI; teshis dosyasi
    # varsa arac yuzeyinin mesh'te olup olmadigini soyler ve o daha temeldir.
    _t = KOK / "minihawk_mesh_teshisi.json"
    if _t.exists():
        t = json.loads(_t.read_text(encoding="utf-8"))
        rec["mesh_teshisi"] = {
            "yuzey_yuzleri": [(k["ad"], k.get("yuzey_yuz")) for k in
                              t.get("seviyeler", [])],
            "esik": t.get("yuzey_yuz_esigi"),
            "monoton": t.get("yuzey_yuz_monoton"),
        }
        if t.get("esik_altinda_seviyeler"):
            engeller.append(
                "ARAC YUZEYI MESH'TE YOK: "
                + ", ".join(f"{ad}={y}" for ad, y in
                            rec["mesh_teshisi"]["yuzey_yuzleri"])
                + f" yuz (esik {t.get('yuzey_yuz_esigi')}). Cd/Cl bu "
                  "kademelerden SAYI DEGIL; asagidaki GCI ve y+ engelleri bunun "
                  "SONUCUDUR. Ayrinti: minihawk_mesh_teshisi.json")

    if gci_pct > 15.0:
        engeller.append(
            f"RANS MESH-BAGIMSIZ DEGIL: GCI %{gci_pct:.0f}"
            + ("" if monoton else ", seri MONOTON DEGIL")
            + ". Delta bu bandi AYNEN devralir")
    if yplus_ort and not (30.0 <= yplus_ort <= 300.0):
        engeller.append(
            f"y+ BANT DISI: ortalama {yplus_ort:.0f} (hedef 30-300). Ilk hucre "
            "sinir tabakayi yutuyor, CILT SURTUNMESI COZULMUYOR — Delta'nin "
            "baskin terimi tam da o")
    # Iki kaynak AYNI AERODINAMIK DURUMDA mi: tasima uyusmuyorsa surukleme
    # karsilastirmasi ayni noktada yapilmiyor demektir.
    cl_b = (b["nokta"] or {}).get("Cl")
    if (cl_b is not None and r["Cl"] is not None
            and abs(r["Cl"] - cl_b) > 0.05):
        engeller.append(
            f"AYNI DURUMDA DEGILLER: RANS Cl={r['Cl']:.4f}, birlestirme "
            f"Cl={cl_b:.4f}. RANS kamburlugu cozemiyor (mesh), yani iki sayi "
            "ayni aerodinamik noktaya ait degil")

    rec["engeller"] = engeller
    if engeller and "delta" in rec:
        d = rec["delta"]
        rec["verdikt"] = (
            f"⛔ Δ HESAPLANDI ama KULLANILAMAZ: {d['deger']:.5f} ± {d['band']:.5f} "
            f"(±%{d['band_pct']:.0f}) — band degerin "
            f"{d['band']/abs(d['deger']):.1f} KATI. Duz-levha kestirimi "
            f"{rec['islak_alan']['Cd_parazit_kestirimi']:.5f}, olculen onun "
            f"{d['kestirime_orani']:.1f} kati. Engeller: "
            + " | ".join(e.split(":")[0] for e in engeller))
    elif engeller:
        rec["verdikt"] = "⛔ Δ HESAPLANAMADI: " + " | ".join(
            e.split(":")[0] for e in engeller)
    else:
        d = rec["delta"]
        rec["verdikt"] = (f"✅ Δ = {d['deger']:.5f} ± {d['band']:.5f} "
                          f"(±%{d['band_pct']:.0f}), kanat alani tabaninda")
    rec["_gerekli"] = (
        "SIRA ONEMLI. (0) ONCE ARAC YUZEYI COZULMELI: en ince seviye 74 yuz "
        "veriyor, esik 500. Kok neden dagitim — alan 1.5 m ucak icin 38x22.5x21 m "
        "ve arka plan mesh'i oraya DUZGUN seriliyor (0.166 m hucre), butce "
        "yuzeye ulasmadan tukeniyor. `CFDCase.refinement_regions` zaten var ama "
        "arac yolu kullanmiyor; govde cevresine hedefli kutu ayni butceyle "
        "yuzeyi cozer. (1) sonra mesh-bagimsizligi (GCI<%15, monoton), "
        "(2) y+ 30-300 (prizma katmani), (3) Cl kamburlugu cozmeli (su an "
        "alpha=0'da 0.0143, 2B beklenti ~0.25). 1-3 ancak 0 saglaninca "
        "anlamlidir; geometri artik dogru.")
    rec["_uretim"] = "Üretim: python experiments/delta_entegrasyon.py"
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "delta_entegrasyon.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    ra = rec["referans_alani"]
    print(f"referans alani: RANS {ra['rans_m2']} m² ({ra['rans_mode']}) -> "
          f"kanat {ra['birlestirme_m2']} m², olcek {ra['olcek']}")
    print(f"RANS  Cd = {rec['rans']['Cd_kendi_tabani']} "
          f"-> {rec['rans']['Cd_kanat_tabani']} (kanat tabani), "
          f"Cl = {rec['rans']['Cl']}")
    n = rec["birlestirme"] or {}
    print(f"BIRL. Cd = {n.get('Cd_toplam')} ±%{n.get('Cd_band_pct')}, "
          f"Cl = {n.get('Cl')}")
    ia = rec["islak_alan"]
    print(f"islak alan {ia['s_islak_m2']} m², Cf={ia['Cf']} -> "
          f"parazit kestirimi Cd={ia['Cd_parazit_kestirimi']}")
    if "delta" in rec:
        d = rec["delta"]
        print(f"\nΔ = {d['deger']} ± {d['band']} (±%{d['band_pct']}); "
              f"band paylari {d['band_paylari']}")
    print("\n" + rec["verdikt"])
    print("\nGEREKLI: " + rec["_gerekli"])
    print("-> delta_entegrasyon.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
