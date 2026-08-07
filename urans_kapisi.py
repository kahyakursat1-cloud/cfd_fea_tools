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


# ── KOŞUM SONRASI: ÖNCÜLÜ ÖLÇÜMLE DEĞİŞTİR ────────────────────────────────

def salinim_olc(zaman: list[float], deger: list[float],
                gecis_orani: float = 0.25) -> dict:
    """Zaman serisinden frekans, genlik ve ortalama — geçiş atıldıktan sonra.

    Reçetenin Strouhal öncülü BİR TAHMİNDİR ve bunu kendi çıktısında söyler.
    Koşu bitince tahmin edilecek bir şey kalmaz: frekans ÖLÇÜLÜR. Bu fonksiyon
    o ölçümü yapar ve reçete `recete_guncelle` ile öncülden çıkıp ölçüme
    dayanır.

    YÖNTEM: ortalamadan YUKARI geçişlerin zamanı, doğrusal enterpolasyonla
    bulunup ardışık farkların MEDYANI alınır.

    İlk sürüm işaret değişimlerini SAYIYORDU (f = geçiş/2T) ve sentetik 8 Hz
    sinyalde %11 şaştı: pencere tam periyot sayısına oturmadığında baştaki ve
    sondaki kısmi periyotlar sayımı bozuyor. Enterpolasyonlu medyan aynı
    sinyalde %0,0001 veriyor. Fark önemli, çünkü ölçülen frekans doğrudan
    Δt'ye giriyor — %11 hata reçeteyi o kadar kaydırırdı.

    Medyan (ortalama değil) seçildi: tek bir bozuk periyot (başlangıç geçicisi
    ya da ikincil mod) sonucu sürüklemesin. FFT yerine bu yöntem, düzensiz
    örneklenmiş seride (adjustableTimeStep) yeniden-örnekleme gerektirmez;
    bedeli çok-frekanslı sinyalde baskın modu ayıramamaktır ve bu SÖYLENİR.
    """
    if len(zaman) < 8 or len(zaman) != len(deger):
        return {"olculdu": False, "neden": f"yetersiz örnek ({len(deger)})"}
    n0 = int(len(zaman) * gecis_orani)
    t, y = zaman[n0:], deger[n0:]
    if len(t) < 8 or (t[-1] - t[0]) <= 0:
        return {"olculdu": False, "neden": "geçiş atıldıktan sonra pencere boş"}
    ort = sum(y) / len(y)
    sapma = [v - ort for v in y]
    sure = t[-1] - t[0]
    genlik = (max(y) - min(y)) / 2.0
    # Yukari gecis zamanlari (dogrusal enterpolasyon): sapma <=0 iken >0 olur.
    yukari = [t[i] + (t[i + 1] - t[i]) * (-sapma[i]) / (sapma[i + 1] - sapma[i])
              for i in range(len(sapma) - 1)
              if sapma[i] <= 0 < sapma[i + 1] and sapma[i + 1] != sapma[i]]
    if len(yukari) < 3:
        return {"olculdu": False,
                "neden": (f"pencerede {len(yukari)} tam salınım geçişi — salınım "
                          "görünmüyor (çözüm oturmuş olabilir)"),
                "ortalama": ort, "genlik": genlik, "pencere_s": sure}
    periyotlar = sorted(b - a for a, b in zip(yukari, yukari[1:]))
    per = periyotlar[len(periyotlar) // 2]
    if per <= 0:
        return {"olculdu": False, "neden": "medyan periyot sıfır/negatif",
                "ortalama": ort, "genlik": genlik, "pencere_s": sure}
    f = 1.0 / per
    sacilma = (periyotlar[-1] - periyotlar[0]) / per * 100
    return {"olculdu": True, "frekans_hz": round(f, 6),
            "periyot_s": round(per, 8),
            "ortalama": ort, "genlik": genlik,
            "genlik_pct": round(abs(genlik / ort) * 100, 3) if ort else None,
            "periyot_sayisi": len(periyotlar), "pencere_s": round(sure, 6),
            "periyot_sacilmasi_pct": round(sacilma, 2),
            "_yontem": ("yukarı-geçiş zamanlarının MEDYAN farkı (doğrusal "
                        "enterpolasyonlu); düzensiz örneklemede yeniden-örnekleme "
                        "gerektirmez ama çok-frekanslı sinyalde baskın modu AYIRAMAZ"),
            "_uyari": ("; ".join(x for x in (
                (f"pencerede yalnız {len(periyotlar)} periyot var — istatistik "
                 "zayıf, en az 10 önerilir") if len(periyotlar) < 10 else None,
                (f"periyot saçılması %{sacilma:.0f} — tek frekanslı değil, "
                 "medyan baskın modu temsil etmeyebilir") if sacilma > 30 else None,
            ) if x) or None)}


def recete_guncelle(recete: dict, olcum: dict) -> dict:
    """Öncüle dayalı reçeteyi ÖLÇÜLEN frekansla yeniden hesapla.

    Bir URANS koşusundan sonra Strouhal öncülünü kullanmaya devam etmek,
    elde ölçüm varken tahmine sarılmaktır. Ölçülen frekans öncülden ne kadar
    saptı — o da yazılır, çünkü öncülün ne kadar güvenilir olduğu bir sonraki
    vaka için bilgidir.
    """
    if not olcum.get("olculdu"):
        return {**recete, "_olcum_notu": "frekans ölçülemedi — öncül korundu: "
                                         + str(olcum.get("neden"))}
    f = float(olcum["frekans_hz"])
    periyot = 1.0 / f
    dt = periyot / ADIM_PER_PERIYOT
    toplam = GECIS_PERIYODU + ISTATISTIK_PERIYODU
    onculf = recete.get("frekans_hz")
    sapma = (abs(f - onculf) / onculf * 100) if onculf else None
    return {**recete, "frekans_hz": round(f, 6), "periyot_s": round(periyot, 8),
            "zaman_adimi_s": float(f"{dt:.3g}"),
            "adim_sayisi": int(toplam * ADIM_PER_PERIYOT),
            "toplam_fiziksel_s": round(toplam * periyot, 6),
            "kaynak": "ÖLÇÜM (ilk URANS koşusundan)",
            "oncul_frekans_hz": onculf,
            "oncul_sapmasi_pct": round(sapma, 1) if sapma is not None else None,
            "_oncul_uyarisi": (
                f"Frekans artık ÖLÇÜLDÜ; Strouhal öncülü {sapma:.0f}% şaşmıştı"
                if sapma is not None else "Frekans ölçüldü."),
            "_olcum": olcum}
