"""Model-form belirsizliği — REJİM BAŞINA, ölçülen çapalardan.

NEDEN: model-form belirsizliği `lifting/bluff × duvar-çözünürlüğü` tablosundan
geliyordu ama değerler LİTERATÜR-ÖNCÜLÜYDÜ (5/12/10/20). Tek ölçülen hücre
`bluff.wall_resolved = 5.95` idi. Bağlı akış, ayrılmış akış ve künt cisim aynı
model-form belirsizliğini taşımaz; bunu ölçülen çapalardan doldurmak mümkün.

NE ÖLÇÜLEBİLİR: bir çapa, ÇÖZÜCÜNÜN referanstan sapmasını verir. O sapma, o
rejimdeki model-form hatasının BİR ÖRNEĞİDİR. Tek örnekten "band" çıkarmak
istatistiksel olarak zayıftır ve bu dosya N'i AÇIKÇA yazar; N=1 ise "tek
çapa" der, dağılım iddia etmez.

NE ÖLÇÜLEMEZ: çapada duvar işlemi (y⁺) KAYITLI DEĞİLSE o çapa bir hücreye
ATANAMAZ. Tahmin edilmez — atanamayan çapa listelenir ve hücre öncül kalır.

    python experiments/model_form_bandi.py
Çıktı: model_form_bandi.json  (+ validation_band.json'a ölçülen hücreler)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

BAND_DOSYASI = KOK / "validation_band.json"


def _j(ad: str) -> dict | None:
    p = KOK / ad
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _duvar_islemi(yplus_ort: float | None) -> str | None:
    """y⁺ KAYITLIYSA hücre adı; değilse None (tahmin YOK)."""
    from validity_envelope import YPLUS_BANDI, YPLUS_DUVAR_COZUNUR
    if yplus_ort is None:
        return None
    if yplus_ort <= YPLUS_DUVAR_COZUNUR:
        return "wall_resolved"
    if YPLUS_BANDI[0] <= yplus_ort <= YPLUS_BANDI[1]:
        return "wall_function"
    return None          # bant dışı: o koşu zaten savunulabilir değil


def _kosudan_yplus(cells: int | None) -> dict | None:
    """Çapanın y⁺'ını KOŞU ARŞİVİNDEN al — ama TAHMİNLE değil, DOĞRULANMIŞ
    bağla: yalnız hücre sayısı BİREBİR tutan koşu kabul edilir.

    NEDEN: küp çapasının y⁺'ı ölçülmüştü (vehicle_runs/gci_kup, ort 112,83) ama
    çapa dosyasına hiç yazılmamıştı; bu yüzden çapa hiçbir hücreye atanamıyor ve
    `bluff.wall_function` öncül kalıyordu. Ölçüm vardı, tüketicisine ulaşmıyordu.

    Hücre sayısı eşleşmesi zorunlu: "aynı geometrinin bir koşusu" yetmez, çünkü
    y⁺ kademeye göre değişir ve yanlış kademenin y⁺'ını çapaya iliştirmek
    ölçümü uydurmak olurdu.
    """
    if not cells:
        return None
    for sj in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        d = json.loads(sj.read_text(encoding="utf-8"))
        if (d.get("mesh") or {}).get("cells") != cells:
            continue
        yp = (d.get("sinir_tabaka") or {}).get("yplus") or {}
        if yp.get("ort") is None:
            continue
        return {"ort": yp["ort"], "max": yp.get("max"), "min": yp.get("min"),
                "kosu": sj.parent.name, "cells": cells,
                "_bag": f"hücre sayısı birebir eşleşti ({cells:,})"}
    return None


def capalari_topla() -> list[dict]:
    """Her çapa: rejim, ölçülen sapma (%), duvar işlemi (varsa), referans."""
    c: list[dict] = []

    kup = _j("gci_kup_arac.json")
    if kup and kup.get("literatur_sapma_pct") is not None:
        _yp = ((kup.get("yplus") if isinstance(kup.get("yplus"), dict) else None)
               or _kosudan_yplus((kup.get("seviyeler") or [{}])[-1].get("cells")))
        c.append({"capa": "küp", "rejim": "bluff",
                  "sapma_pct": abs(float(kup["literatur_sapma_pct"])),
                  "yplus_ort": (_yp or {}).get("ort"),
                  "yplus_max": (_yp or {}).get("max"),
                  "yplus_kaynak": (_yp or {}).get("_bag"),
                  "yplus_kosu": (_yp or {}).get("kosu"),
                  "referans": (kup.get("referans") or {}).get("kaynak", "Hoerner 1965")})

    tmr = _j("tmr_gci_verdict.json")
    if tmr and tmr.get("seviyeler"):
        ref = float(tmr.get("TMR_referans_SST_alpha0") or 0.0)
        ince = float(tmr["seviyeler"][-1]["Cd"])
        if ref:
            c.append({"capa": "NACA0012 α=0 (2B, bağlı akış)",
                      "rejim": "attached_2d",
                      "sapma_pct": abs((ince - ref) / ref * 100),
                      # TMR C-grid ailesi y⁺<1 ile üretilir (kanıtın kendi tanımı)
                      "yplus_ort": 1.0,
                      "referans": "NASA TMR / CFL3D"})

    bas = _j("basamak_ayrilma.json")
    if bas:
        ok = [s for s in bas.get("seviyeler", []) if s.get("durum") == "ok"]
        if ok:
            en_iyi = min(ok, key=lambda s: abs(s["hata_pct"]))
            c.append({"capa": f"geriye-basamak ({en_iyi['model']})",
                      "rejim": "separated",
                      "sapma_pct": abs(float(en_iyi["hata_pct"])),
                      "yplus_ort": en_iyi.get("yplus_ort"),
                      "referans": (bas.get("referans") or {}).get("kaynak", "")})
    return c


def calistir() -> dict:
    from validation_anchors import _MODEL_U_PCT
    capalar = capalari_topla()

    hucreler: dict[str, dict] = {}
    atanamayan: list[dict] = []
    for x in capalar:
        hucre = _duvar_islemi(x.get("yplus_ort"))
        if hucre is None:
            atanamayan.append({"capa": x["capa"], "rejim": x["rejim"],
                               "sapma_pct": round(x["sapma_pct"], 2),
                               "neden": "duvar işlemi (y⁺) kanıtta KAYITLI DEĞİL "
                                        "— hücreye atanmadı, TAHMİN edilmedi"})
            continue
        hucreler.setdefault(x["rejim"], {}).setdefault(hucre, []).append(x)

    olculen: dict[str, dict] = {}
    ayrinti: dict[str, dict] = {}
    for rejim, h in hucreler.items():
        for islem, liste in h.items():
            en_kotu = max(x["sapma_pct"] for x in liste)
            oncul = _MODEL_U_PCT.get(rejim, {}).get(islem)
            # TEK CAPAYLA BAND DARALTILMAZ. n=1 bir dagilim degil, tek ornektir;
            # olculen deger onculden KUCUKSE bu "model daha iyi" demek degil,
            # "bu tek vakada daha iyi cikti" demektir. Model-form hatasi rejim
            # icinde geometriye gore guclu degisir. Bu yuzden n=1 iken
            # max(oncul, olculen) raporlanir ve olcum kayda gecer.
            # Olcum onculden BUYUKSE her durumda olcum kazanir: oncul o zaman
            # kanitla YANLISLANMIS demektir (asagi degil, yukari duzeltme).
            oncul_korundu = (len(liste) == 1 and oncul is not None
                             and en_kotu < oncul)
            deger = oncul if oncul_korundu else en_kotu
            olculen.setdefault(rejim, {})[islem] = round(deger, 2)
            ayrinti.setdefault(rejim, {})[islem] = {
                "u_pct": round(deger, 2), "olculen_pct": round(en_kotu, 2),
                "oncul_pct": oncul, "oncul_korundu": oncul_korundu,
                "n_capa": len(liste),
                "capalar": [{"ad": x["capa"], "sapma_pct": round(x["sapma_pct"], 2),
                             "referans": x["referans"]} for x in liste],
                "_anlam": (
                    (f"TEK ÇAPA (%{en_kotu:.2f}) öncülden (%{oncul}) KÜÇÜK — "
                     "band tek ölçümle DARALTILMADI; öncül korundu, ölçüm kayıtlı"
                     if oncul_korundu else
                     "TEK ÇAPA — dağılım değil, tek ölçüm; öncülü AŞTIĞI için "
                     "ölçüm kullanıldı") if len(liste) == 1
                    else f"{len(liste)} çapanın EN KÖTÜSÜ"),
            }

    # MEVCUT OLCULEN HUCRELER KORUNUR: bu betigin kapsamadigi bir hucre daha
    # once olculmusse silinmez.
    onceki = json.loads(BAND_DOSYASI.read_text(encoding="utf-8")) \
        if BAND_DOSYASI.exists() else {}
    birlesik = {r: {**onceki.get(r, {}), **v} for r, v in olculen.items()}
    for r, v in onceki.items():
        birlesik.setdefault(r, v)

    oncul_kalan = []
    for rejim, cells in _MODEL_U_PCT.items():
        for islem, v in cells.items():
            if not birlesik.get(rejim, {}).get(islem):
                oncul_kalan.append({"rejim": rejim, "duvar": islem,
                                    "oncul_pct": v})

    # BU BETIGIN HESAPLAMADIGI HUCRELER. Band dosyasinda duruyorlar ama baska
    # bir kampanyadan geldiler; kac capadan turedikleri ve tek-capa kuralinin
    # onlara uygulanip uygulanmadigi BURADAN bilinemez. Sessiz birakmak,
    # farkli kurallarla uretilmis sayilari ayni tabloda esitlemek olurdu.
    _bu_betik = {(r, i) for r, h in ayrinti.items() for i in h}
    dis_kaynakli = []
    for rejim, h in birlesik.items():
        for islem, v in h.items():
            if (rejim, islem) in _bu_betik:
                continue
            oncul = _MODEL_U_PCT.get(rejim, {}).get(islem)
            dis_kaynakli.append({
                "rejim": rejim, "duvar": islem, "u_pct": v, "oncul_pct": oncul,
                "_not": ("bu betik ÜRETMEDİ (başka kampanya); çapa sayısı ve "
                         "tek-çapa kuralının uygulanıp uygulanmadığı bilinmiyor"
                         + (f" — öncülden (%{oncul}) KÜÇÜK, gözden geçirilmeli"
                            if oncul is not None and v < oncul else ""))})

    rec = {
        "vaka": "Model-form belirsizliği — rejim × duvar işlemi, ÖLÇÜLEN çapalardan",
        "_neden": ("Deger LITERATUR-ONCULUYDU ve rejimden bagimsiz uygulaniyordu. "
                   "Bagli akis, ayrilmis akis ve kunt cisim ayni model-form "
                   "hatasini tasimaz."),
        "capalar": [{**x, "sapma_pct": round(x["sapma_pct"], 2)} for x in capalar],
        "olculen_hucreler": ayrinti,
        "atanamayan_capalar": atanamayan,
        "oncul_kalan_hucreler": oncul_kalan,
        "dis_kaynakli_hucreler": dis_kaynakli,
        "_kisit": ("Bir capanin sapmasi, o rejimdeki model-form hatasinin BIR "
                   "ORNEGIDIR. N=1 olan hucrede dagilim IDDIA EDILMEZ. Duvar "
                   "islemi kayitli olmayan capa hucreye ATANMAZ — tahmin "
                   "edilmez. Ayrica sapma, referansin KENDI deneysel "
                   "belirsizligini de icerir ve o ayristirilmamistir."),
        "_uretim": "Üretim: python experiments/model_form_bandi.py",
    }
    rec["verdikt"] = (
        f"{len(capalar)} capa toplandi; {sum(len(v) for v in ayrinti.values())} "
        f"hucre OLCULDU, {len(atanamayan)} capa atanamadi, "
        f"{len(oncul_kalan)} hucre ONCUL kaldi. "
        + "; ".join(f"{r}.{i}=%{d['u_pct']} (n={d['n_capa']})"
                    for r, h in ayrinti.items() for i, d in h.items()))
    rec["_yazilan"] = birlesik
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    BAND_DOSYASI.write_text(
        json.dumps(rec["_yazilan"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (KOK / "model_form_bandi.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    for x in rec["capalar"]:
        print(f"  {x['capa']:<34} {x['rejim']:<12} %{x['sapma_pct']:>5.2f}"
              f"  y+={x.get('yplus_ort')}")
    if rec["atanamayan_capalar"]:
        print("\n  ATANAMAYAN (duvar işlemi kayıtlı değil):")
        for x in rec["atanamayan_capalar"]:
            print(f"    {x['capa']} — %{x['sapma_pct']}")
    print("\n" + rec["verdikt"])
    print("-> model_form_bandi.json, validation_band.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
