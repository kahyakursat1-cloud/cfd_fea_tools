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


def capalari_topla() -> list[dict]:
    """Her çapa: rejim, ölçülen sapma (%), duvar işlemi (varsa), referans."""
    c: list[dict] = []

    kup = _j("gci_kup_arac.json")
    if kup and kup.get("literatur_sapma_pct") is not None:
        c.append({"capa": "küp", "rejim": "bluff",
                  "sapma_pct": abs(float(kup["literatur_sapma_pct"])),
                  "yplus_ort": (kup.get("yplus") or {}).get("ort")
                  if isinstance(kup.get("yplus"), dict) else None,
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
            # N=1: "band" degil TEK ORNEK. Deger yine kullanilir (oncul'den
            # daha iyidir) ama N yazilir ve dagilim IDDIA EDILMEZ.
            en_kotu = max(x["sapma_pct"] for x in liste)
            olculen.setdefault(rejim, {})[islem] = round(en_kotu, 2)
            ayrinti.setdefault(rejim, {})[islem] = {
                "u_pct": round(en_kotu, 2), "n_capa": len(liste),
                "capalar": [{"ad": x["capa"], "sapma_pct": round(x["sapma_pct"], 2),
                             "referans": x["referans"]} for x in liste],
                "_anlam": ("TEK ÇAPA — dağılım değil, tek ölçüm" if len(liste) == 1
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

    rec = {
        "vaka": "Model-form belirsizliği — rejim × duvar işlemi, ÖLÇÜLEN çapalardan",
        "_neden": ("Deger LITERATUR-ONCULUYDU ve rejimden bagimsiz uygulaniyordu. "
                   "Bagli akis, ayrilmis akis ve kunt cisim ayni model-form "
                   "hatasini tasimaz."),
        "capalar": [{**x, "sapma_pct": round(x["sapma_pct"], 2)} for x in capalar],
        "olculen_hucreler": ayrinti,
        "atanamayan_capalar": atanamayan,
        "oncul_kalan_hucreler": oncul_kalan,
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
