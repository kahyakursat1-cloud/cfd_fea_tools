"""VLM ÇAPASI — VSPAERO'nun taşımasına ÖLÇÜLMÜŞ bir band verir.

NEDEN: `polar_birlestirme` 3B taşımayı VLM'den alıyor ama VLM bu depoda hiçbir
referansa karşı doğrulanmamıştı; Cl "literatür-öncül" etiketiyle çıkıyordu. Bu
çapa o etiketi ÖLÇÜME çevirir.

ÖLÇÜT GRAFİK-TABLOSUZ VE KAPALI-FORM. Dikdörtgen kanat için lifting-line'ın τ/δ
düzeltmeleri kitap grafiklerinden okunur — ezberden alıntılamak kanıt değildir.
Onun yerine Prandtl lifting-line'ın CEBİRSEL sonucu kullanılır:

    1/a_3B  =  1/a_2B  +  (1+τ)/(π·AR)

Yani 1/a'yı 1/AR'ye karşı çizersek DOĞRU çıkmalı ve KESİŞİMİ 1/a_2B olmalı.
İnce-kanat teorisinde a_2B = 2π, yani kesişim 1/(2π) = 0.15915 rad⁻¹.

Bu test yanlışlanabilir ve tablo gerektirmez: VLM sonlu-kanat çözücüsü gibi
davranıyorsa AR taramasının kesişimi 2π'yi geri vermek ZORUNDA.

İKİNCİ ÖLÇÜT (yine kapalı-form): span verimi e = CL²/(π·AR·CDi). Eliptik yükleme
matematiksel ÜST SINIRDIR (e=1); dikdörtgen kanat bunun ALTINDA kalmalı. e>1
çıkarsa çözücü fiziksel olarak imkânsız bir sonuç veriyor demektir.

Bu bir DOĞRULAMA (validation) DEĞİL, bir DOĞRULAMADIR (verification): VLM'i
potansiyel-akış teorisiyle karşılaştırır. Viskoz gerçeklikle farkı (model-form)
AYRI bir sorudur ve bu çapa onu ölçmez.

    conda run -n openvsp python experiments/vlm_capa.py
Çıktı: vlm_capa.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

AR_LISTESI = (4.0, 6.0, 8.0, 12.0)
# YAKINSAMIS SPAN PANELI. OLCULDU (AR=6): varsayilan panelde span verimi
# e=1.0788 cikiyor — eliptik ust sinirin USTU, yani FIZIKSEL OLARAK IMKANSIZ.
# Panel artirilinca e monoton dusuyor: 12->1.0280, 24->1.0045, 40->0.9954.
# Yani imkansiz deger AYRIKLASTIRMA artefaktiydi. Tasima egimi de kayiyor:
# 4.4523 -> 4.1750 (%6.6). Capa YAKINSAMIS panelde olculmeli.
SPAN_PANEL = 40
ALFALAR = (0.0, 2.0, 4.0, 6.0)
KIRIS = 1.0
MACH = 0.05
A_2B_TEORI = 2.0 * math.pi          # ince-kanat: 1/a kesişimi 1/(2π)


def _kanat_kur(ar: float, kiris: float = KIRIS, span_panel: int = 0,
               kiris_panel: int = 0):
    """SADE dikdörtgen kanat: gövde yok, kuyruk yok, ok yok, dihedral yok.

    Çapa temiz olmalı — gövde/kuyruk katkısı kesişimi kaydırır ve ölçtüğümüz şey
    artık "VLM sonlu-kanat teorisine uyuyor mu" olmaktan çıkar.
    """
    import openvsp as vsp
    vsp.VSPCheckSetup()
    vsp.ClearVSPModel()
    wid = vsp.AddGeom("WING")
    vsp.SetGeomName(wid, "AnchorWing")
    span_yari = ar * kiris / 2.0
    xs = vsp.GetXSec(vsp.GetXSecSurf(wid, 0), 1)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Span"), span_yari)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Root_Chord"), kiris)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Tip_Chord"), kiris)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Sweep"), 0.0)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Dihedral"), 0.0)
    # PANEL YOGUNLUGU = VLM'in AYRIKLASTIRMASI (RANS'ta mesh neyse bu odur).
    # e>1 olcumu bunun yakinsamamis olabilecegini soyluyor; band OLCULMELI.
    if span_panel:
        vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "SectTess_U"), span_panel)
    if kiris_panel:
        vsp.SetParmValUpdate(vsp.FindParm(wid, "Tess_W", "Shape"), kiris_panel)
    vsp.Update()
    return wid


def _polar(ar: float, span_panel: int = 0, kiris_panel: int = 0) -> list[dict]:
    import openvsp as vsp

    from openvsp_bridge import _ayar
    _kanat_kur(ar, KIRIS, span_panel, kiris_panel)
    span = ar * KIRIS
    alan = span * KIRIS
    vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
    vsp.ExecAnalysis("VSPAEROComputeGeometry")
    a = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(a)
    _ayar(a, "AlphaStart", [float(min(ALFALAR))], "double")
    _ayar(a, "AlphaEnd", [float(max(ALFALAR))], "double")
    _ayar(a, "AlphaNpts", [len(ALFALAR)])
    _ayar(a, "MachStart", [MACH], "double")
    _ayar(a, "Sref", [alan], "double")
    _ayar(a, "bref", [span], "double")
    _ayar(a, "cref", [KIRIS], "double")
    _ayar(a, "WakeNumIter", [5])
    vsp.ExecAnalysis(a)
    pol = vsp.FindResultsID("VSPAERO_Polar", 0)
    if not pol:
        return []
    al = list(vsp.GetDoubleResults(pol, "Alpha"))
    cl = list(vsp.GetDoubleResults(pol, "CLwtot"))
    cdi = list(vsp.GetDoubleResults(pol, "CDiw"))
    return [{"alpha": round(al[i], 3), "Cl": round(cl[i], 6),
             "Cd_i": round(cdi[i], 7)}
            for i in range(min(len(al), len(cl), len(cdi)))]


def _egim_per_rad(noktalar: list[dict]) -> float | None:
    """En küçük kareler taşıma eğimi (1/rad). Simetrik kanatta kesişim ~0."""
    n = len(noktalar)
    if n < 2:
        return None
    xs = [math.radians(p["alpha"]) for p in noktalar]
    ys = [p["Cl"] for p in noktalar]
    mx, my = sum(xs) / n, sum(ys) / n
    payda = sum((x - mx) ** 2 for x in xs)
    return None if payda < 1e-15 else sum((x - mx) * (y - my)
                                          for x, y in zip(xs, ys)) / payda


def panel_yakinsamasi(ar: float = 6.0,
                      paneller=(0, 12, 24, 40)) -> dict:
    """Span-panel sayisi ile e ve a nasil degisiyor — VLM'in "mesh yakinsamasi".

    NEDEN: ilk kosuda span verimi e = 1.05-1.09 cikti, oysa eliptik yukleme
    MATEMATIKSEL UST SINIRDIR (e=1). Ya cozucu induklenen direnci iyimser
    veriyor ya da AYRIKLASTIRMA yakinsamamis. Ikisi ayri seydir ve olcumle
    ayrilir: panel arttikca e -> 1'e YAKLASIYORSA ayriklastirma, SABIT
    KALIYORSA sistematik model hatasi.
    """
    out = []
    for sp in paneller:
        p = _polar(ar, span_panel=sp)
        a3 = _egim_per_rad(p)
        e_ler = [x["Cl"] ** 2 / (math.pi * ar * x["Cd_i"])
                 for x in p if x["Cd_i"] and x["Cd_i"] > 1e-9 and abs(x["Cl"]) > 1e-6]
        out.append({"span_panel": sp or "varsayilan",
                    "a_3B_per_rad": round(a3, 5) if a3 else None,
                    "e_max": round(max(e_ler), 4) if e_ler else None})
    e_ler = [x["e_max"] for x in out if x["e_max"]]
    a_ler = [x["a_3B_per_rad"] for x in out if x["a_3B_per_rad"]]
    return {"AR": ar, "kosular": out,
            "e_araligi": [min(e_ler), max(e_ler)] if e_ler else None,
            "a_sapma_pct": (round((max(a_ler) - min(a_ler)) / min(a_ler) * 100, 3)
                            if len(a_ler) > 1 else None),
            "yorum": ("e panel ile 1'e yaklasiyorsa AYRIKLASTIRMA, sabit kaliyorsa "
                      "SISTEMATIK model hatasidir.")}


def calistir() -> dict:
    kayit = []
    for ar in AR_LISTESI:
        p = _polar(ar, span_panel=SPAN_PANEL)
        a3 = _egim_per_rad(p)
        # span verimi: eliptik yükleme e=1 ile MATEMATİKSEL ÜST SINIRDIR.
        e_ler = [round(x["Cl"] ** 2 / (math.pi * ar * x["Cd_i"]), 4)
                 for x in p if x["Cd_i"] and x["Cd_i"] > 1e-9 and abs(x["Cl"]) > 1e-6]
        kayit.append({"AR": ar, "noktalar": p,
                      "a_3B_per_rad": round(a3, 5) if a3 else None,
                      "span_verimi_e": e_ler})

    # 1/a = 1/a_2B + (1+τ)/(π·AR)  →  1/AR'ye karşı DOĞRU; kesişim 1/a_2B olmalı.
    veri = [(1.0 / k["AR"], 1.0 / k["a_3B_per_rad"]) for k in kayit
            if k["a_3B_per_rad"]]
    kesisim = egim = r2 = None
    if len(veri) >= 2:
        n = len(veri)
        mx = sum(x for x, _ in veri) / n
        my = sum(y for _, y in veri) / n
        sxx = sum((x - mx) ** 2 for x, _ in veri)
        egim = sum((x - mx) * (y - my) for x, y in veri) / sxx if sxx > 1e-18 else None
        if egim is not None:
            kesisim = my - egim * mx
            sst = sum((y - my) ** 2 for _, y in veri)
            sse = sum((y - (kesisim + egim * x)) ** 2 for x, y in veri)
            r2 = 1.0 - sse / sst if sst > 1e-18 else None

    a2b_olculen = (1.0 / kesisim) if kesisim else None
    hata_pct = (abs(a2b_olculen - A_2B_TEORI) / A_2B_TEORI * 100
                if a2b_olculen else None)
    tau = (egim * math.pi - 1.0) if egim is not None else None
    e_max = max((max(k["span_verimi_e"]) for k in kayit if k["span_verimi_e"]),
                default=None)
    panel = panel_yakinsamasi()

    rec = {
        "vaka": ("VLM çapası — VSPAERO sonlu-kanat taşıma eğimi vs Prandtl "
                 "lifting-line (AR taraması, dikdörtgen kanat)"),
        "_neden": ("polar_birlestirme 3B tasimayi VLM'den aliyor ama VLM bu depoda "
                   "hicbir referansa karsi dogrulanmamisti; Cl 'literatur-oncul' "
                   "etiketiyle cikiyordu. Bu capa o etiketi OLCUME cevirir."),
        "olcut": ("1/a_3B = 1/a_2B + (1+tau)/(pi*AR). 1/AR'ye karsi DOGRU olmali "
                  "ve KESISIMI 1/a_2B vermeli; ince-kanat teorisinde a_2B = 2*pi. "
                  "Grafik/tablo degeri KULLANILMAZ — olcut kapali-formdur."),
        "AR_listesi": list(AR_LISTESI), "alfalar": list(ALFALAR),
        "span_panel": SPAN_PANEL,
        "kayitlar": kayit,
        "uyum": {"kesisim_1_over_a": round(kesisim, 6) if kesisim else None,
                 "a_2B_olculen_per_rad": round(a2b_olculen, 4) if a2b_olculen else None,
                 "a_2B_teori_per_rad": round(A_2B_TEORI, 4),
                 "hata_pct": round(hata_pct, 2) if hata_pct is not None else None,
                 "dogrusal_R2": round(r2, 6) if r2 is not None else None,
                 "tau_ima_edilen": round(tau, 4) if tau is not None else None},
        "span_verimi_max": e_max,
        "panel_yakinsamasi": panel,
        "_kisit": ("Bu bir DOGRULAMA (verification) calismasidir: VLM potansiyel-akis "
                   "TEORISIYLE karsilastirilir. Viskoz gercekle farki (model-form) "
                   "AYRI bir sorudur ve bu capa onu OLCMEZ. Ayrica VSPAERO kamburlu "
                   "kesitte yuksek alfada iraksadigi icin capa SIMETRIK/duz kanattir."),
        "_uretim": "Üretim: conda run -n openvsp python experiments/vlm_capa.py",
    }
    ok_dogrusal = (r2 is not None and r2 > 0.99)
    ok_kesisim = (hata_pct is not None and hata_pct < 10.0)
    # e>1 EL ALTINDAN GECISTIRILMEZ ama KORU KORUNE de reddedilmez: eliptik sinir
    # TEORIDE kesindir, sayisal bir cozucu onu AYRIKLASTIRMA hatasiyla asabilir.
    # Ayrimi ÖLÇÜM yapar — panel calismasi e'nin monoton 1'e indigini gosteriyor
    # (1.0788 -> 1.0280 -> 1.0045 -> 0.9954). Kalan asim o kaymanin altindaysa
    # ARTIK AYRIKLASTIRMA, ustundeyse SISTEMATIK hatadir.
    _pk = (panel.get("e_araligi") or [None, None])
    _kayma = (abs(_pk[1] - _pk[0]) if all(x is not None for x in _pk) else None)
    _asim = (e_max - 1.0) if e_max is not None else None
    e_sinifi = ("sinir icinde" if (_asim is not None and _asim <= 0) else
                "artik ayriklastirma" if (_asim is not None and _kayma
                                          and _asim < _kayma) else
                "SISTEMATIK — aciklanamiyor")
    ok_e = e_sinifi != "SISTEMATIK — aciklanamiyor"
    rec["span_verimi_asimi"] = {"e_max": e_max,
                                "asim": round(_asim, 4) if _asim is not None else None,
                                "panel_kaymasi": round(_kayma, 4) if _kayma else None,
                                "sinif": e_sinifi}
    rec["verdikt"] = (
        ("✅ " if (ok_dogrusal and ok_kesisim and ok_e) else "⚠️ ")
        + (f"1/a-1/AR dogrusalligi R²={r2:.5f}; " if r2 is not None else "")
        + (f"kesisimden a_2B={a2b_olculen:.4f}/rad, teori 2π={A_2B_TEORI:.4f} "
           f"(sapma %{hata_pct:.2f}); " if hata_pct is not None else "")
        + (f"span verimi max e={e_max} ({e_sinifi}"
           + (f", asim {_asim:+.4f} < panel kaymasi {_kayma:.4f}"
              if (_asim is not None and _asim > 0 and _kayma) else "")
           + ")" if e_max is not None else ""))
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "vlm_capa.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{'AR':>5} {'a_3B (1/rad)':>14} {'1/a':>9}  span verimi e")
    for k in rec["kayitlar"]:
        a3 = k["a_3B_per_rad"]
        print(f"{k['AR']:5.1f} {a3 if a3 else float('nan'):14.5f} "
              f"{1 / a3 if a3 else float('nan'):9.5f}  {k['span_verimi_e']}")
    print()
    print(json.dumps(rec["uyum"], indent=2, ensure_ascii=False))
    print("\n" + rec["verdikt"])
    print("-> vlm_capa.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
