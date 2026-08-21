"""Eşleşik karşılaştırmada model-form KORELASYONU — ρ ölçülüyor.

NEDEN: `kosu_gecmisi._ayirt_edilebilirlik` ikili bir varsayım kullanıyor.
Aynı hücredeki iki koşuda model-form hatası ORTAK sayılıp farkta TAMAMEN
götürülüyor (ρ=1); hücre farklıysa hiç götürülmüyor (ρ=0). İkisi de aynı
formülün uç noktalarıdır:

    u_fark² = u_nA² + u_nB² + u_mA² + u_mB² − 2·ρ·u_mA·u_mB

ρ=1 ve u_mA=u_mB iken model terimi tam olarak sıfırlanır --- bugünkü eşleşik
dal. ρ=0 iken tam RSS --- eşleşmemiş dal. Arada bir yer yok ve hangisinin
doğru olduğu ÖLÇÜLMEMİŞTİ.

NE ÖLÇÜLEBİLİR: aynı hücredeki çapaların İŞARETLİ sapmaları. Model hatası
e_i = μ + ε_i biçimindeyse (μ hücreye ortak sistematik bias, ε_i vakaya özgü
saçılma), iki farklı vakanın hatası arasındaki korelasyon

    ρ = μ² / (μ² + σ²)

olur. μ ve σ, çapa sapmalarından doğrudan kestirilir. Eşleştirme ORTAK olanı
götürür; götüremediği ε'dur ve bugün o da sıfır sayılıyor.

NE ÖLÇÜLEMEZ: n=3'lük tek bir hücreden ρ'nun kendisi güvenle kestirilemez ve
bu dosya bunu AÇIKÇA yazar. Dahası saçılma, çapaların KENDİ sayısal bandıyla
aynı mertebedeyse model saçılması sayısal gürültüden AYRILAMAZ --- o durumda
ölçülen σ bir ÜST SINIRDIR, kestirim değil.

    python experiments/eslesik_korelasyon.py
Çıktı: eslesik_korelasyon.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "eslesik_korelasyon.json"


def rho_kestir(isaretli_sapmalar: list[float]) -> dict:
    """Ortak bias / saçılma ayrışımından ρ.

    İŞARET ŞART: mutlak değerler kullanılırsa zıt yöne sapan iki çapa aynı
    yöne sapıyormuş gibi görünür ve ρ sistematik olarak ŞİŞER. Eşleştirmenin
    tüm dayanağı sapmaların AYNI yönde olmasıdır.
    """
    n = len(isaretli_sapmalar)
    if n < 2:
        return {"n": n, "rho": None,
                "gerekce": "tek çapadan saçılma ölçülemez — ρ KESTİRİLMEDİ"}
    mu = sum(isaretli_sapmalar) / n
    var = sum((e - mu) ** 2 for e in isaretli_sapmalar) / n
    sigma = math.sqrt(var)
    rms = math.sqrt(sum(e * e for e in isaretli_sapmalar) / n)
    rho = mu * mu / (mu * mu + var) if (mu or var) else None
    return {
        "n": n, "isaretli_sapmalar_pct": [round(e, 2) for e in isaretli_sapmalar],
        "ortak_bias_pct": round(mu, 2), "sacilma_pct": round(sigma, 2),
        "rms_pct": round(rms, 2), "rho": round(rho, 3) if rho is not None else None,
        "ayni_yonde_mi": all(e > 0 for e in isaretli_sapmalar)
                         or all(e < 0 for e in isaretli_sapmalar),
    }


def artik_model_bandi(u_model_pct: float, rho: float | None) -> float | None:
    """Eşleşik farkta GÖTÜRÜLEMEYEN model belirsizliği [%].

    u_mA = u_mB = u_m alınır (aynı hücre): u_artik = u_m·√(2(1−ρ)).
    ρ=1 → 0 (bugünkü varsayım). ρ=0 → u_m·√2 (tam RSS).
    """
    if rho is None or u_model_pct is None:
        return None
    return u_model_pct * math.sqrt(max(0.0, 2.0 * (1.0 - rho)))


def _hucre_capalari() -> dict:
    """Ölçülen hücrelerden İŞARETLİ sapmalar. İşaret kanıt dosyasında YOK
    (mutlak yazılıyor); koşu Cd'si ile referans Cd'sinden geri hesaplanır."""
    from validation_anchors import ANCHORS
    band = json.loads((KOK / "model_form_bandi.json").read_text(encoding="utf-8"))
    ad_kosu = {"disk": "disk", "küp (çapa koşusu)": "cube", "Ahmed 25°": "ahmed_25",
               "küre": "sphere", "NACA0012 kanat AR6": "naca0012_wing_ar6"}
    out = {}
    for rejim, ic in (band.get("olculen_hucreler") or {}).items():
        for duvar, v in ic.items():
            sapmalar, u_say, atlanan = [], [], []
            for c in v.get("capalar") or []:
                anahtar = ad_kosu.get(c["ad"])
                sj = (KOK / "validation_anchors_runs" / f"_anchor_{anahtar}"
                      / "sonuc.json") if anahtar else None
                spec = ANCHORS.get(anahtar) if anahtar else None
                if not (sj and sj.exists() and spec and spec.get("Cd")):
                    # ISARET GERI HESAPLANAMIYOR: capa kanit-JSON kaynakli ve
                    # koşu arşivi yok. Sapmanin MUTLAK degeri elde ama isareti
                    # yok; isaretsiz deger rho'yu SISIRIR, o yuzden alinmiyor.
                    atlanan.append(c["ad"])
                    continue
                cd = json.loads(sj.read_text(encoding="utf-8")).get("cd")
                if cd is None:
                    atlanan.append(c["ad"])
                    continue
                sapmalar.append((cd - spec["Cd"]) / spec["Cd"] * 100)
                if c.get("u_sayisal_pct") is not None:
                    u_say.append(float(c["u_sayisal_pct"]))
            if sapmalar:
                out[f"{rejim}.{duvar}"] = {
                    "sapmalar": sapmalar, "u_sayisal": u_say,
                    "isareti_okunamayan": atlanan,
                    "u_model_pct": v.get("u_pct"),
                }
    return out


def olc() -> dict:
    hucreler, kayit = _hucre_capalari(), {}
    for ad, h in hucreler.items():
        r = rho_kestir(h["sapmalar"])
        u_say_ort = (sum(h["u_sayisal"]) / len(h["u_sayisal"])) if h["u_sayisal"] else None
        # SACILMA SAYISAL GURULTUDEN AYRILABILIYOR MU. Capalarin kendi
        # ayriklastirma bandi olculen sacilmayla ayni mertebedeyse, sacilmanin
        # ne kadari MODEL ne kadari AG bu veriden cikmaz.
        ayrilabilir = (r.get("sacilma_pct") is not None and u_say_ort is not None
                       and r["sacilma_pct"] > u_say_ort)
        kayit[ad] = {
            **r,
            "u_model_pct": h["u_model_pct"],
            "u_sayisal_ort_pct": round(u_say_ort, 2) if u_say_ort else None,
            "sacilma_sayisaldan_ayrilabilir_mi": ayrilabilir if u_say_ort else None,
            "artik_model_bandi_pct": (
                round(artik_model_bandi(h["u_model_pct"], r.get("rho")), 2)
                if r.get("rho") is not None and h["u_model_pct"] else None),
            "isareti_okunamayan_capalar": h["isareti_okunamayan"],
            "_yorum": (
                "σ, çapaların kendi sayısal bandından KÜÇÜK — vakaya özgü model "
                "saçılması sayısal gürültüden AYRILAMAZ; ölçülen σ bir ÜST "
                "SINIRDIR." if u_say_ort and not ayrilabilir else
                "σ sayısal bandın üstünde — vakaya özgü saçılma GÖRÜLEBİLİR."
                if u_say_ort else
                "çapaların sayısal bandı kayıtlı değil — ayrılabilirlik "
                "DEĞERLENDİRİLMEDİ"),
        }
    coklu = {k: v for k, v in kayit.items() if (v.get("n") or 0) >= 2}
    ayrilabilen = [k for k, v in coklu.items()
                   if v.get("sacilma_sayisaldan_ayrilabilir_mi")]
    yon = [k for k, v in coklu.items() if v.get("ayni_yonde_mi")]
    return {
        "vaka": "Eşleşik karşılaştırmada model-form korelasyonu (ρ)",
        # HUKUM KANITTAN YAZILIR: iki ayri olgu, iki ayri cumle.
        "verdikt": (
            (f"EŞLEŞTİRME DAYANAKLI ({len(yon)}/{len(coklu)} çok-çapalı hücrede "
             f"tüm sapmalar AYNI yönde — ortak bias gerçek), ANCAK ρ=1 "
             f"GÖSTERİLEMEDİ: saçılma "
             + ("hiçbir hücrede " if not ayrilabilen else
                f"{len(coklu) - len(ayrilabilen)}/{len(coklu)} hücrede ")
             + "sayısal gürültüden ayrılamıyor, ölçülen σ bir ÜST SINIRDIR. "
               "Band GENİŞLETİLMEDİ; varsayımın hükmü çevirdiği aralık "
               "işaretleniyor (kosu_gecmisi._ayirt_edilebilirlik).")
            if coklu else
            "ÖLÇÜLEMEDİ — hiçbir hücrede birden çok çapa yok; ρ KESTİRİLMEDİ"),
        "_neden": ("kosu_gecmisi eslesik dalda rho=1 varsayiyor (model-form "
                   "farkta TAMAMEN goturuluyor). Varsayim OLCULMEMISTI."),
        "hucreler": kayit,
        "olculebilen_hucre": sorted(coklu),
        "_kisit": (
            "rho yalnizca COK CAPALI hucrede kestirilebilir; bugun bu kosulu "
            f"saglayan hucre: {', '.join(sorted(coklu)) or 'YOK'}. n=3 ile "
            "kestirim zayiftir ve tek hucreden TUM tabloya genellenmez. Ayrica "
            "sapmalar farkli GEOMETRILER arasindadir (disk / kup / Ahmed); "
            "kullanicinin tipik A/B kiyasi AYNI aracin iki varyantidir ve orada "
            "ortak olan daha COKTUR. Bu yuzden olculen sacilma, ayni-arac A/B "
            "icin bir UST SINIRDIR."),
        "_uretim": "Üretim: python experiments/eslesik_korelasyon.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    print("Eşleşik karşılaştırma — model-form korelasyonu\n")
    for ad, v in r["hucreler"].items():
        if v.get("rho") is None:
            print(f"  {ad:<28} n={v['n']}  {v.get('gerekce', '')}")
            continue
        print(f"→ {ad:<28} n={v['n']}  sapmalar {v['isaretli_sapmalar_pct']}")
        print(f"   ortak bias {v['ortak_bias_pct']:+.2f}%  ·  saçılma "
              f"{v['sacilma_pct']:.2f}%  ·  ρ = {v['rho']:.3f}"
              f"  ({'aynı yönde' if v['ayni_yonde_mi'] else 'YÖN KARIŞIK'})")
        print(f"   u_model {v['u_model_pct']}%  →  eşleşik farkta GÖTÜRÜLEMEYEN "
              f"artık: {v['artik_model_bandi_pct']}%")
        print(f"   {v['_yorum']}")
        if v["isareti_okunamayan_capalar"]:
            print(f"   işareti okunamayan (ρ'ya GİRMEDİ): "
                  f"{', '.join(v['isareti_okunamayan_capalar'])}")
    print(f"\n{r['_kisit']}")
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
