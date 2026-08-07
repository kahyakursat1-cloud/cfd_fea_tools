"""URANS eskalasyonu — "kesin çözüm URANS'tır" cümlesini REÇETEYE çevirir.

Kararlı-RANS koşusu limit çevrimine girdiğinde hüküm bugün doğru olanı
söylüyor: akış zaman-bağımlıdır, kesin çözüm URANS'tır. Ama orada duruyor.
Kullanıcının elinde ne zaman adımı var, ne kaç adım koşacağı, ne de bunun
kaç saat süreceği. Öneri uygulanabilir değilse hüküm yarım kalır --- aynı
kusur `propeller_params`'ta da vardı: "sınırı aştın" demek yetmiyordu, o
hız ve çapta ne kadar mümkün olduğu da yazılmalıydı.

BU BİR TAHMİNDİR, ÖLÇÜM DEĞİL. Kararlı çözücüde iterasyon zaman değildir;
salınımın iterasyon-periyodu fiziksel periyoda çevrilemez. Fiziksel frekans
Strouhal öncülünden gelir ve öncül rejime bağlıdır. Reçete bunu her çıktısında
söyler; sayılar bir başlangıç noktasıdır, doğrulanmış bir kurulum değil.

    from urans_kapisi import urans_recetesi
"""
from __future__ import annotations

# Strouhal ONCULU — rejime gore. Kaynak: Roshko (1961) silindir; Okajima (1982)
# kare kesit; Ahmed govdesi icin Sims-Williams (2001) mertebe. Bunlar OLCUM
# DEGIL literatur mertebesidir ve +-%50 sasabilir; recete de o kadar sasar.
ST_ONCUL = {
    "bluff": (0.20, "Roshko 1961 — silindir/küt cisim mertebesi"),
    "separated": (0.20, "ayrılmış kayma tabakası — küt cisim mertebesiyle aynı"),
    "lifting": (0.15, "stall sonrası kanat; bağlı akışta salınım beklenmez"),
    "attached_2d": (0.15, "bağlı 2B akış — salınım varsa kurulum şüphelidir"),
}
ST_VARSAYILAN = (0.20, "rejim bilinmiyor — küt cisim öncülü")

ADIM_PER_PERIYOT = 100      # bir periyotta zaman adimi (2. mertebe sema icin yeterli)
GECIS_PERIYODU = 5          # baslangic gecicisi atilir
ISTATISTIK_PERIYODU = 15    # ortalama/genlik istatistigi
IC_ITERASYON = 3            # PIMPLE dis dongusu — adim basina cozucu maliyeti carpani


def urans_recetesi(salinim: dict | None, lref_m: float | None,
                   velocity: float | None, rejim: str | None = None,
                   rans_sure_s: float | None = None,
                   rans_iterasyon: int | None = None) -> dict:
    """Salınan bir kararlı-RANS koşusundan URANS kurulum önerisi.

    `salinim`: `vehicle_pipeline.salinim_analizi` çıktısı (osilasyon, genlik_pct).
    `rans_sure_s` / `rans_iterasyon`: maliyet tahmini için; yoksa süre verilmez.
    """
    if not (salinim or {}).get("osilasyon"):
        return {"gerekli": False, "gerekce": "kararlı-RANS salınmıyor — eskalasyon gereksiz"}
    if not lref_m or not velocity or lref_m <= 0 or velocity <= 0:
        return {"gerekli": True, "hesaplanabilir": False,
                "gerekce": ("salınım var ama karakteristik uzunluk ya da hız "
                            "bilinmiyor — zaman adımı hesaplanamaz")}
    st, st_kaynak = ST_ONCUL.get(rejim or "", ST_VARSAYILAN)
    f = st * velocity / lref_m
    periyot_s = 1.0 / f
    dt = periyot_s / ADIM_PER_PERIYOT
    toplam_periyot = GECIS_PERIYODU + ISTATISTIK_PERIYODU
    adim = int(toplam_periyot * ADIM_PER_PERIYOT)

    out = {
        "gerekli": True, "hesaplanabilir": True,
        "strouhal_oncul": st, "strouhal_kaynak": st_kaynak,
        "frekans_hz": round(f, 4), "periyot_s": round(periyot_s, 6),
        "zaman_adimi_s": float(f"{dt:.3g}"),
        "adim_sayisi": adim,
        "toplam_fiziksel_s": round(toplam_periyot * periyot_s, 5),
        "gecis_periyodu": GECIS_PERIYODU,
        "istatistik_periyodu": ISTATISTIK_PERIYODU,
        "genlik_pct": (salinim or {}).get("genlik_pct"),
        "_oncul_uyarisi": (
            "Zaman adımı STROUHAL ÖNCÜLÜNDEN türetildi, ölçümden değil. Kararlı "
            "çözücüde iterasyon zaman değildir; salınımın iterasyon-periyodu "
            "fiziksel periyoda çevrilemez. Öncül ±%50 şaşarsa reçete de o kadar "
            "şaşar — ilk URANS koşusunda ölçülen frekansla Δt yeniden ayarlanmalı."),
        "_courant_uyarisi": (
            "Δt burada YALNIZ periyot çözünürlüğünden gelir. Courant kısıtı ayrıca "
            "kontrol edilmelidir: en küçük hücrede Co = U·Δt/Δx ≤ 1 (PIMPLE'da daha "
            "gevşek olabilir). İkisinden KÜÇÜK olanı seçilir."),
    }
    if rans_sure_s and rans_iterasyon and rans_iterasyon > 0:
        it_maliyet = rans_sure_s / rans_iterasyon
        tahmin_s = adim * IC_ITERASYON * it_maliyet
        out["tahmini_sure_s"] = round(tahmin_s, 1)
        out["tahmini_sure_metin"] = _sure_metni(tahmin_s)
        out["_maliyet_temeli"] = (
            f"kararlı koşu {rans_sure_s:.0f} s / {rans_iterasyon} iterasyon = "
            f"{it_maliyet:.2f} s/iterasyon; URANS adım başına ~{IC_ITERASYON} dış "
            "döngü. Aynı ağda, aynı makinede.")
    return out


def _sure_metni(s: float) -> str:
    if s < 3600:
        return f"~{s / 60:.0f} dakika"
    if s < 86400:
        return f"~{s / 3600:.1f} saat"
    return f"~{s / 86400:.1f} gün"


def recete_metni(r: dict) -> list[str]:
    """Hüküm gerekçesine eklenecek satırlar — kullanıcı-yüzü."""
    if not r.get("gerekli") or not r.get("hesaplanabilir"):
        return [r["gerekce"]] if r.get("gerekce") and r.get("gerekli") else []
    sure = r.get("tahmini_sure_metin")
    return [
        (f"URANS reçetesi: Δt={r['zaman_adimi_s']:g} s, {r['adim_sayisi']} adım "
         f"({r['gecis_periyodu']}+{r['istatistik_periyodu']} periyot, "
         f"f≈{r['frekans_hz']:g} Hz, St={r['strouhal_oncul']} öncülü)"
         + (f" — bu ağda tahmini {sure}" if sure else "")),
        r["_oncul_uyarisi"],
        r["_courant_uyarisi"],
    ]
