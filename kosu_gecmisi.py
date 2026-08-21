"""Koşu geçmişi — tüm analiz koşularını tek tablodan tara + iki koşuyu karşılaştır.

Mühendis iş-akışının ilk isteği: 'vehicle_runs doluyor, iki koşunun Cd'sini yan yana
görmek için JSON açıyorum'. Veri zaten sonuc.json'larda; bu modül yalnız görünüm katmanı.
Karşılaştırma A/B-dürüst: iki koşunun kalite/mesh ailesi farklıysa uyarır (farklı aile
karşılaştırması sistematik-hata kırpmaz).

CLI: python kosu_gecmisi.py listele [--tip roket]
     python kosu_gecmisi.py karsilastir <kosu_adi_A> <kosu_adi_B>
GUI: app_analyzer '📂 Koşular' → KosularDialog (bu modülü kullanır).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_ROOTS = ("vehicle_runs", "validation_anchors_runs", "_doe_runs")

_ALANLAR = [("ad", "Koşu"), ("tip", "Tip"), ("kalite", "Kalite"), ("hiz", "V (m/s)"),
            ("alpha", "α (°)"), ("cd", "Cd"), ("u_pct", "±U%"), ("cl", "Cl"),
            ("cells", "Hücre"), ("verdikt", "Mesh-bağımsızlık"), ("status", "Durum")]


def tara(roots=_ROOTS) -> list[dict]:
    """Tüm koşu dizinlerini tara → tablo-hazır kayıt listesi (yeni→eski, mtime)."""
    out = []
    for root in roots:
        base = HERE / root
        if not base.exists():
            continue
        for p in sorted(base.rglob("sonuc.json"), key=lambda x: -x.stat().st_mtime):
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                # Bozuk sonuc.json kosunun TABLODAN DUSMESI demektir: kullanici
                # "kosum listede yok" der ve nedenini ogrenemez. Satir atlanmaya
                # devam eder (tek bozuk kayit tum gecmisi dusurmemeli) ama
                # okunamayan kosu ADIYLA listeye girer.
                out.append({"ad": p.parent.name, "yol": str(p.parent),
                            "durum": "okunamadi",
                            "hata": f"{type(e).__name__}: {e}"})
                continue
            unc = s.get("belirsizlik") or {}
            md = s.get("mesh_duyarlilik") or {}
            out.append({
                "ad": p.parent.name, "yol": str(p.parent),
                "tip": s.get("vehicle_type", "?"), "kalite": s.get("kalite", ""),
                "hiz": s.get("velocity"), "alpha": s.get("alpha_deg"),
                "cd": s.get("cd"), "cl": s.get("cl"), "ld": s.get("ld"),
                "drag_N": s.get("drag_N"),
                "u_pct": unc.get("u_toplam_pct"),
                "u_sayisal_pct": unc.get("u_sayisal_pct"),
                "u_model_pct": unc.get("u_model_pct"),
                "u_kaynak": unc.get("u_sayisal_kaynak"),
                "model_kaynak": unc.get("model_kaynak"),
                "duvar_cozunur": unc.get("duvar_cozunur"),
                "cells": (s.get("mesh") or {}).get("cells"),
                "yplus": ((s.get("sinir_tabaka") or {}).get("yplus") or {}).get("ort"),
                "verdikt": (md.get("verdikt") or "")[:60],
                "status": s.get("status", "?"),
                "rapor": s.get("report", ""),
            })
    return out


def bul(ad: str, kayitlar: list[dict] | None = None) -> dict | None:
    for k in (kayitlar if kayitlar is not None else tara()):
        if k["ad"] == ad:
            return k
    return None


def karsilastir(a: str | dict, b: str | dict) -> dict:
    """İki koşunun metrik-yanyana karşılaştırması + Δ%. Uyarılar: farklı kalite/tip/hız
    (A/B karşılaştırmasının güvenilirlik önkoşulları)."""
    ka = a if isinstance(a, dict) else bul(a)
    kb = b if isinstance(b, dict) else bul(b)
    if not ka or not kb:
        raise ValueError(f"koşu bulunamadı: {a if not ka else b}")

    def d_pct(x, y):
        if x is None or y is None or not x:
            return None
        return round((y - x) / abs(x) * 100, 2)
    satirlar = []
    for key, etiket in (("cd", "Cd"), ("cl", "Cl"), ("ld", "L/D"),
                        ("drag_N", "Sürükleme (N)"), ("cells", "Hücre"),
                        ("yplus", "y⁺ (gövde)")):
        satirlar.append({"metrik": etiket, "A": ka.get(key), "B": kb.get(key),
                         "delta_pct": d_pct(ka.get(key), kb.get(key)),
                         "band_tasir": metrik_bandi(etiket)})
    uyarilar = []
    for key, mesaj in (("kalite", "mesh kalitesi farklı — Δ mesh-etkisi içerir"),
                       ("tip", "araç tipi/referans-alan modu farklı"),
                       ("hiz", "hız (Re) farklı — katsayılar aynı rejimde değil")):
        if ka.get(key) != kb.get(key):
            uyarilar.append(f"{key}: {ka.get(key)} ↔ {kb.get(key)} ({mesaj})")
    ayirt = _ayirt_edilebilirlik(ka, kb, uyarilar)
    return {"A": ka["ad"], "B": kb["ad"], "satirlar": satirlar,
            "uyarilar": uyarilar, "ayirt_edilebilirlik": ayirt}


def esles(ka: dict, kb: dict) -> tuple[bool, str]:
    """İki koşu AYNI model-form hücresinde mi? (rejim×duvar-işlemi)

    Eşleşiklerse model-form hatası ORTAKTIR ve farkta büyük ölçüde birbirini
    götürür — A/B bandı yalnız sayısal belirsizlikten gelmelidir.
    """
    if ka.get("tip") != kb.get("tip"):
        return False, "araç tipi (rejim) farklı"
    da, db = ka.get("duvar_cozunur"), kb.get("duvar_cozunur")
    if da is None or db is None:
        return False, "duvar işlemi koşuların en az birinde kayıtlı değil"
    if da != db:
        return False, "duvar işlemi farklı (biri duvar-çözünür, diğeri duvar-fonksiyonu)"
    return True, "aynı rejim + aynı duvar işlemi"


def _ayirt_edilebilirlik(ka: dict, kb: dict, uyarilar: list[str]) -> dict | None:
    """A/B farkı için EŞLEŞİK band + hüküm.

    Eski sürüm her iki koşunun `u_toplam` (sayısal ⊕ model) bandını RSS'liyordu.
    Bu, eşleşik karşılaştırmada YANLIŞ ve pratikte felç edici: iki mesh kalitesi
    kıyaslanırken %12'lik ORTAK model-form hatası iki kez sayılıp %17'lik bir
    banda dönüşüyor ve hiçbir tasarım farkı ayırt edilemiyordu. Ortak sistematik
    hata farkta götürülür (ASME V&V 20, eşleşik/paired karşılaştırma); yalnız
    hücre DEĞİŞİYORSA model-form banda girer.
    """
    ca, cb = ka.get("cd"), kb.get("cd")
    if None in (ca, cb) or not ca:
        return None
    esit, neden = esles(ka, kb)
    if esit:
        ua, ub = ka.get("u_sayisal_pct"), kb.get("u_sayisal_pct")
        band_tipi = "eşleşik (sayısal)"
        gerekce = f"{neden} → ortak model-form hatası farkta götürüldü"
    else:
        ua, ub = ka.get("u_pct"), kb.get("u_pct")
        band_tipi = "eşleşmemiş (sayısal ⊕ model)"
        gerekce = f"{neden} → model-form hatası götürülmez, banda dahil"
    if None in (ua, ub):
        return {"dCd_pct": round(abs(cb - ca) / abs(ca) * 100, 2),
                "band_rss_pct": None, "band_tipi": band_tipi, "gerekce": gerekce,
                "hukum": "HÜKÜM VERİLEMEZ — bu band tipi için belirsizlik kayıtlı değil"}
    dcd = abs(cb - ca) / abs(ca) * 100
    band = (ua ** 2 + ub ** 2) ** 0.5
    _rho = _rho_bilgisi(ka, kb) if esit else None
    if dcd > band:
        # UYARI VARSA "TASARIM FARKI" DENEMEZ. Kalite/hiz farkliysa olculen fark
        # mesh ya da Re etkisini de tasir; hangi payin tasarimdan geldigi bu
        # kiyastan cikmaz. Eski surum bu durumda da "gercek tasarim farki"
        # yaziyordu — okuyan yanlis nedene atfediyordu.
        hukum = ("Fark bandın DIŞINDA — ancak KAYNAĞI karışık: " + "; ".join(uyarilar)
                 if uyarilar else "Fark bandın DIŞINDA — gerçek tasarım farkı")
    else:
        hukum = "Fark bandın İÇİNDE — A/B ayırt edilemez"
    out = {"dCd_pct": round(dcd, 2), "band_rss_pct": round(band, 2),
           "band_tipi": band_tipi, "gerekce": gerekce, "hukum": hukum}
    # VARSAYIM YUK TASIYORSA GORUNSUN. Eslesik dal model-form hatasini TAMAMEN
    # goturur (rho=1). Olculdu (eslesik_korelasyon.json): bluff.wall_function
    # hucresindeki uc capa da AYNI yone sapiyor (+3,4 / +1,8 / +9,3), yani
    # ortak bias GERCEK ve eslestirme dayanakli. Ama vakaya ozgu sacilma
    # (sigma=3,2%) capalarin kendi sayisal bandindan (~5%) KUCUK, yani
    # sifirdan AYIRT EDILEMIYOR. Band bu yuzden genisletilmiyor --- ayirt
    # edilemeyen bir sayiyla bandi sismek olcume dayanmaz.
    #
    # Genisletilmediginde tek risk su: fark bandin hemen disindaysa, hukum
    # rho=1 varsayimina YASLANIR. O durum burada ADIYLA isaretlenir.
    if _rho and _rho.get("artik_pct"):
        genis = (band ** 2 + _rho["artik_pct"] ** 2) ** 0.5
        if band < dcd <= genis:
            out["varsayim_yuk_tasiyor"] = True
            out["hukum"] += (
                f" — ANCAK bu hüküm ρ=1 varsayımına yaslanıyor: ortak model-form "
                f"hatasının farkta TAMAMEN götürüldüğü kabul ediliyor. Ölçülen "
                f"korelasyon ρ={_rho['rho']:.2f} ile götürülemeyen artık "
                f"%{_rho['artik_pct']:.1f} olurdu ve fark o bandın (%{genis:.1f}) "
                f"İÇİNDE kalırdı")
            out["artik_model_bandi_pct"] = round(_rho["artik_pct"], 2)
            out["genisletilmis_band_pct"] = round(genis, 2)
    return out


def _rho_bilgisi(ka: dict, kb: dict) -> dict | None:
    """Koşuların hücresi için ÖLÇÜLEN model-form korelasyonu.

    Ölçüm yoksa None döner ve hiçbir şey iddia edilmez; hücre eşleşmiyorsa da
    öyle. Bir hücrede ölçülen ρ'yu başka hücreye taşımak, tam olarak bu
    dosyanın başka yerde reddettiği türden bir genellemedir.
    """
    p = HERE / "eslesik_korelasyon.json"
    if not p.exists():
        return None
    try:
        kayit = json.loads(p.read_text(encoding="utf-8"))
    # sessiz-yutma: kabul — kanit dosyasi bozuksa korelasyon NOTU dusmeli,
    # A/B kiyasi degil; sebep asagida hukme girmiyor cunku iddia da girmiyor
    except (json.JSONDecodeError, OSError):
        return None
    return _hucre_esle(kayit, ka.get("u_model_pct"), kb.get("u_model_pct"))


def _hucre_esle(kayit: dict, um_a: float | None, um_b: float | None) -> dict | None:
    """Koşuların model-form HÜCRESİ — `u_model_pct` değeri üzerinden DOĞRULANIR.

    Hücre adını araç tipinden yeniden türetmek cazip ama yanlış olurdu: koşu
    kaydı rejim adını TAŞIMIYOR ve `vehicle_type` → rejim eşlemesi bu dosyada
    ikinci bir kaynak olurdu. Koşunun taşıdığı `u_model_pct` ise hücrenin ta
    kendisinden geliyor; birebir tutması bağı doğrular.

    İki koşunun u_model'i farklıysa hücreleri de farklıdır --- o zaman zaten
    eşleşik dal çalışmamalıydı ve burada hiçbir şey iddia edilmez. Tek bir
    hücrede ölçülen ρ, başka hücreye TAŞINMAZ.
    """
    if um_a is None or um_b is None or abs(um_a - um_b) > 1e-6:
        return None
    aday = [{"rho": h["rho"], "artik_pct": h["artik_model_bandi_pct"], "hucre": ad}
            for ad, h in (kayit.get("hucreler") or {}).items()
            if h.get("artik_model_bandi_pct") is not None
            and h.get("u_model_pct") is not None
            and abs(float(h["u_model_pct"]) - um_a) <= 1e-6]
    return aday[0] if len(aday) == 1 else None


def metrik_bandi(metrik: str) -> str | None:
    """Hangi metrikler Cd'nin ölçülen bandını taşır, hangileri taşımaz.

    Cd bandı ölçülür (mesh duyarlılığı Cd üzerinden koşulur). Sürükleme kuvveti
    aynı hız/alanda Cd ile orantılıdır → aynı bağıl bandı taşır. Cl ve L/D
    TAŞIMAZ: taşımanın ağ duyarlılığı sürüklemeninkinden farklıdır (α=8°
    çapasında Cd yakınsarken Cl serisi ıraksıyordu). Onlara Cd'nin bandını
    uygulamak ölçülmemiş bir sayıyı ölçülmüş göstermek olur.
    """
    return {"Cd": "ölçülen", "Sürükleme (N)": "Cd ile orantılı — aynı bağıl band",
            }.get(metrik)


def tablo_metni(kayitlar: list[dict], tip: str = "") -> str:
    rows = [k for k in kayitlar if not tip or k["tip"] == tip]
    if not rows:
        return "(koşu yok)"
    basliklar = [b for _, b in _ALANLAR]
    hucre = [[("" if k.get(a) is None else str(k.get(a))) for a, _ in _ALANLAR] for k in rows]
    gen = [max(len(basliklar[i]), *(len(h[i]) for h in hucre)) for i in range(len(basliklar))]
    cizgi = "  ".join("-" * g for g in gen)
    out = ["  ".join(b.ljust(g) for b, g in zip(basliklar, gen)), cizgi]
    out += ["  ".join(c.ljust(g) for c, g in zip(h, gen)) for h in hucre]
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cli = argparse.ArgumentParser()
    cli.add_argument("komut", choices=["listele", "karsilastir"])
    cli.add_argument("a", nargs="?")
    cli.add_argument("b", nargs="?")
    cli.add_argument("--tip", default="")
    args = cli.parse_args()
    if args.komut == "listele":
        print(tablo_metni(tara(), tip=args.tip))
    else:
        if not (args.a and args.b):
            sys.exit("karsilastir için iki koşu adı gerekli")
        print(json.dumps(karsilastir(args.a, args.b), indent=2, ensure_ascii=False))
