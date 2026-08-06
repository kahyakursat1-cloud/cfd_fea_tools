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
            "band_yok_nedeni": d.get("band_yok_nedeni"),
            "belirsizlik": d.get("belirsizlik") or {},
            "yuzey_cozunurlugu": d.get("yuzey_cozunurlugu") or {},
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
        # ÖLÇÜLMEDİ, SIFIR DEMEK DEĞİL. Ilk surumde GCI yoksa gci_pct=0 olup
        # band_r=0 cikiyordu ve Delta ±%0.1 ile YAYINLANIYORDU — yani band
        # OLCULMEDIGI icin MUKEMMEL KESINLIK gibi gorunuyordu. Tam da bu depoda
        # avlanan kusur.
        band_olculdu = bool(gci_pct) and not r.get("band_yok_nedeni")
        band_r = cd_rans_kanat_tabani * (gci_pct / 100.0) if band_olculdu else None
        band_d = ((band_r ** 2 + band_b ** 2) ** 0.5
                  if band_r is not None else None)

        # BILESEN AYRIMI. "Band olculmedi" demek de FAZLA KABA: RANS kaydinda
        # OLCULMUS bir sayisal bilesen var (salinim genligi %1.42) ama o
        # AYRIKLASTIRMA bandi DEGIL. Iki ayri bilesen tek kelimeye sikistirilirsa
        # ya olculmus bir sey yok sayilir ya da olculmemis bir sey varmis gibi
        # gosterilir. Ikisi de yanlis; ayrildilar.
        alt_sinir = None
        if not band_olculdu:
            _u = r.get("belirsizlik") or {}
            _sal = _u.get("u_sayisal_pct")
            if _sal:
                _br = cd_rans_kanat_tabani * (float(_sal) / 100.0)
                _alt = (_br ** 2 + band_b ** 2) ** 0.5
                alt_sinir = {
                    "deger": round(_alt, 6),
                    "pct": round(_alt / abs(delta) * 100, 2) if delta else None,
                    "iceren_bilesenler": [
                        f"RANS {_u.get('u_sayisal_kaynak', 'sayisal')} %{_sal}",
                        f"birlestirme %{b['nokta'].get('Cd_band_pct', 0)}"],
                    "eksik_bilesenler": ["RANS ayriklastirma (mesh) belirsizligi"],
                    "_anlam": ("ALT SINIRDIR: yalnizca OLCULMUS bilesenleri "
                               "icerir. Ayriklastirma bileseni eklendiginde "
                               "gercek band BUYUR, kucullmez."),
                }
        kestirim = rec["islak_alan"]["Cd_parazit_kestirimi"]
        rec["delta"] = {
            "deger": round(delta, 6),
            "band": round(band_d, 6) if band_d is not None else None,
            "band_olculdu": band_olculdu,
            "band_pct": (round(band_d / abs(delta) * 100, 1)
                         if band_d is not None and delta else None),
            "band_paylari": {
                "rans": round(band_r, 6) if band_r is not None else "OLCULMEDI",
                "birlestirme": round(band_b, 6)},
            "kestirime_orani": round(delta / kestirim, 2) if kestirim else None,
            "alt_sinir_bandi": alt_sinir,
        }
        if not band_olculdu:
            engeller.append(
                "RANS BANDI OLCULMEDI: mesh-bagimsizlik calismasi yok"
                + (f" ({r['band_yok_nedeni']})" if r.get("band_yok_nedeni") else "")
                + ". Delta'nin TAM bandi HESAPLANAMAZ — bandsiz bir fark, kesin "
                  "bir fark DEGILDIR"
                + (f". Yalniz OLCULMUS bilesenlerden ALT SINIR: "
                   f"±{alt_sinir['deger']:.5f} (±%{alt_sinir['pct']:.1f})"
                   if alt_sinir else ""))

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
        _as = d.get("alt_sinir_bandi")
        _b = (f"± {d['band']:.5f} (±%{d['band_pct']:.0f}) — band degerin "
              f"{d['band'] / abs(d['deger']):.1f} KATI"
              if d.get("band") is not None else
              (f"TAM BAND YOK; olculmus bilesenlerden ALT SINIR "
               f"±{_as['deger']:.5f} (±%{_as['pct']:.1f}), AYRIKLASTIRMA "
               f"bileseni eksik — gercek band bundan BUYUK"
               if _as else
               "BANDSIZ — belirsizlik OLCULMEDI (sifir DEGIL)"))
        rec["verdikt"] = (
            f"⛔ Δ HESAPLANDI ama KULLANILAMAZ: {d['deger']:.5f} {_b}. "
            f"Duz-levha kestirimi {rec['islak_alan']['Cd_parazit_kestirimi']:.5f}, "
            f"olculen onun {d['kestirime_orani']:.1f} kati. Engeller: "
            + " | ".join(e.split(":")[0] for e in engeller))
    elif engeller:
        rec["verdikt"] = "⛔ Δ HESAPLANAMADI: " + " | ".join(
            e.split(":")[0] for e in engeller)
    else:
        d = rec["delta"]
        rec["verdikt"] = (f"✅ Δ = {d['deger']:.5f} ± {d['band']:.5f} "
                          f"(±%{d['band_pct']:.0f}), kanat alani tabaninda")

    # GEREKLI ADIMLAR OLCUMDEN URETILIR, SABIT YAZILMAZ. Ilk surumde metin
    # "en ince seviye 74 yuz veriyor" diye SABITTI; ref_bump duzeltmesinden
    # sonra yuzey 24.477 yuze cikti ve metin kendi verisiyle CELISTI.
    _yz = (r.get("yuzey_cozunurlugu") or {}).get("yuzey_yuz")
    _adim = []
    if _yz and not (r.get("yuzey_cozunurlugu") or {}).get("cozuldu"):
        _adim.append(f"(0) ARAC YUZEYI COZULMELI — olculen {_yz:,} yuz")
    elif _yz:
        _adim.append(f"(0) ✔ arac yuzeyi COZULDU ({_yz:,} yuz)")
    _adim.append("(1) mesh-bagimsizlik bandi YOK — " + (r.get("band_yok_nedeni") or
                 f"GCI %{gci_pct:.0f}"))
    if yplus_ort:
        _ok = 30.0 <= yplus_ort <= 300.0
        _adim.append(f"(2) {'✔ ' if _ok else ''}y+ ortalama {yplus_ort:.0f}"
                     + ("" if _ok else " — bant 30-300 disi"))
    if cl_b is not None and r["Cl"] is not None:
        _adim.append(f"(3) Cl uyusmuyor: RANS {r['Cl']:.4f} vs birlestirme "
                     f"{cl_b:.4f} (2B beklenti ~0.25)")
    rec["_gerekli"] = "SIRA ONEMLI. " + " | ".join(_adim)
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
