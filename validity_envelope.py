"""Geçerlilik-zarfı sınıflandırıcı — okula-güvenli TEK KAYNAK.

Her CFD/FEA çıktısını doğrulanmış-zarfa göre sınıflar (DOĞRULANMIŞ / EĞİLİM / ZARF-DIŞI)
ve raporun EN BAŞINA çocuk-okunur ezici bir banner üretir. Amaç: hiçbir sayı belirsizlik-
sınıfı olmadan gösterilmesin; zarf-dışı/eğilim sonuçlar "tasarım sayısı DEĞİL" kapısıyla
işaretlensin (öğrenci yarışma roketini/kanadını yanlış sayıyla tasarlamasın).

Dayanak (Annex I + 2026-06 doğrulamaları):
  - Lift: NACA0012 kOmegaSSTLM, |α|≤8° → %3.7/7.8 (Ladson). α=10/12 → %45/46 (erken stall).
  - Mutlak drag: bu O-grid ailesinde mesh-yakınsamadı (p≈0.2); 3-mesh GCI yoksa EĞİLİM.
  - Süpersonik: inviscid kayma-duvar taban-drag'ı ~%15 fazla → EĞİLİM.
  - FEA: 6 kanonik vaka %0.0–4.8; temsili gerilme tasarım-OK, tepe/tekillik EĞİLİM.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

VALIDATED = "VALIDATED"
TREND = "TREND"
OUT = "OUT"

ALPHA_VALID_DEG = 8.0   # |α|≤8° bağlı akış, doğrulanmış; üstü erken-stall (~%45 @10°)
MACH_INCOMP = 0.3
# Cd üst sınırı GEOMETRİ SINIFINA bağlıdır; tek eşik yanlış alarm üretir.
# Ölçülen referanslar (frontal alan): küp ≈1.05, akışa dik levha ≈1.98, paraşüt ≈1.4,
# Ahmed gövdesi ≈0.3, NACA0012 α=0° ≈0.008. Gerçek-çözücü regresyonu (küp Cd=1.079)
# 0.5'lik tek eşiğin künt cisimleri haksız yere reddettiğini gösterdi.
CD_MAX_PLAUSIBLE = 2.5      # EVRENSEL fizik sınırı — üstü hiçbir araç sınıfında makul değil
CD_MAX_STREAMLINED = 0.5    # profil/kanat/ince gövde bilindiğinde çağıran bunu geçirir
CL_MAX_PLAUSIBLE = 3.0      # 2D basit kesit CLmax ~1.6-2.0; üstü şüpheli

_TR = {VALIDATED: "DOĞRULANMIŞ", TREND: "YALNIZ-EĞİLİM", OUT: "ZARF-DIŞI"}
_ICON = {VALIDATED: "✅", TREND: "🟡", OUT: "🔴"}
_RANK = {VALIDATED: 0, TREND: 1, OUT: 2}


@dataclass
class Verdict:
    quantity: str
    klass: str
    design_safe: bool
    message: str


HAVA_NU = 1.5e-5          # m²/s, ~15 °C
OLCEK_BUYUK_M = 100.0     # üstü: mm/inç ölçek hatası şüphesi (10 m'lik model 1000× → 10 km)
OLCEK_KUCUK_M = 0.005     # altı: m yerine mm girilmiş küçük parça şüphesi


KESKIN_KENAR_ESIGI = 0.02   # altı: pürüzsüz gövde (küre/kapsül 0.00; küp 0.67, silindir 0.33)
EKSEN_ORAN_ESIGI = 1.5      # frontal/en-küçük izdüşüm; küp 1.0 (yanlış alarm vermez),
                            # Z-hizalı roket 12.1 (NX testinde ölçüldü)


def geometry_sanity(geo: dict, vehicle_type: str = "genel",
                    velocity: float | None = None, n_layers: int = 0) -> list[str]:
    """KURULUM kapısı — çözücü başlamadan ÖNCE, saatlik koşuyu boşa harcamamak için.

    Fizik kapısı sonucu denetler; bu kapı GİRDİYİ denetler. Yakalanan üç hata sınıfı,
    üçü de sessizce "geçerli görünen" ama tamamen yanlış bir sayı üretir:
      1. Ölçek — STL mm cinsinden ihraç edilmişse domain 1000× büyür, Reynolds ve
         dolayısıyla Cd tamamen kayar; hiçbir sonuç-kapısı bunu yakalayamaz.
      2. Eksen — akış ekseni yanlışsa cisim akışa yanlış yüzünü verir; sayı makul
         görünür ama başka bir problemin cevabıdır.
      3. Referans alan — araç tipi A_ref'i seçer (uçak: planform, diğerleri: frontal).
         Tip geometriyle uyuşmuyorsa Cd doğrudan alan oranı kadar yanlıştır.

    Döner: uyarı metinleri (boş liste = kurulum makul görünüyor).
    """
    u: list[str] = []
    L = geo.get("lmax_m") or 0.0
    on = geo.get("on_alan_m2") or 0.0
    yan = geo.get("yan_alan_m2") or 0.0
    plan = geo.get("planform_alan_m2") or 0.0

    if L > OLCEK_BUYUK_M:
        u.append(f"ÖLÇEK ŞÜPHESİ: model {L:.0f} m — mm cinsinden ihraç edilmiş olabilir "
                 f"(m karşılığı ~{L / 1000:.3f} m). Yanlış ölçek Reynolds'u ve Cd'yi "
                 "tamamen kaydırır; hiçbir sonuç kontrolü bunu yakalayamaz")
    elif 0 < L < OLCEK_KUCUK_M:
        u.append(f"ÖLÇEK ŞÜPHESİ: model {L * 1000:.2f} mm — birim m mi? "
                 "Çok küçük ölçekte Reynolds düşer, türbülans modeli geçersizleşir")
    if velocity and L > 0:
        re = velocity * L / HAVA_NU
        if re < 1e4:
            u.append(f"Re = {re:.1e} < 1e4 — türbülanslı RANS varsayımı zayıf "
                     "(laminer/geçiş rejimi); ölçek veya hız gözden geçirilmeli")

    # Eksen: akış-yönlü araçta frontal izdüşüm en KÜÇÜK olmalı.
    #
    # Bu kontrol ÖNCE yalnız tip ∈ {ucak, roket} için çalışıyordu — ama yanlış eksen
    # zaten TİPİ yanlış yapan şeydir. NX test setinde ölçüldü: Z ekseninde modellenmiş
    # bir roket (CAD'de en yaygın yönelim) sınıflandırıcıya 'genel' göründü ve kapı bu
    # yüzden sessiz kaldı; oysa A_ref 0.0113 yerine 0.1368 m² alınıyordu — Cd'de 12×
    # hata. Kapı, korumakla yükümlü olduğu değere bağımlı olamaz: artık tipten bağımsız.
    en_kucuk_diger = min(x for x in (yan, plan) if x > 0) if (yan > 0 or plan > 0) else 0.0
    if on > 0 and en_kucuk_diger > 0 and on > max(yan, plan) * 0.999:
        oran = on / en_kucuk_diger
        if oran >= EKSEN_ORAN_ESIGI:
            u.append(f"EKSEN ŞÜPHESİ: frontal izdüşüm ({on:.4g} m²) üç izdüşümün en "
                     f"büyüğü ve en küçüğünün {oran:.1f}× katı — yan {yan:.4g}, üstten "
                     f"{plan:.4g}. Akış-yönlü araçta frontal EN KÜÇÜK olmalıdır; model "
                     "büyük olasılıkla akış eksenine dik duruyor (CAD'de Z-uzun yönelim "
                     f"yaygındır). A_ref bu yüzden ~{oran:.0f}× büyük alınır ve Cd aynı "
                     "oranda yanlış çıkar; --burun/--ust eksenlerini kontrol edin")

    # Referans alan ↔ araç tipi tutarlılığı
    if vehicle_type == "ucak" and on > 0 and plan / on < 2.0:
        u.append(f"REFERANS ALAN ŞÜPHESİ: tip='ucak' planform alanını A_ref alır "
                 f"({plan:.4g} m²) ama planform/frontal = {plan / on:.1f} < 2 — "
                 "geometri kanat benzeri değil. Küt gövde için --tip genel kullan")
    if vehicle_type == "roket" and yan > 0 and on / yan > 0.5:
        u.append(f"GEOMETRİ ŞÜPHESİ: tip='roket' ama frontal/yan = {on / yan:.2f} > 0.5 — "
                 "narin gövde değil; Barrowman/slender varsayımları geçerli olmayabilir")

    # Ayrılma noktasını ne belirliyor? Bu hattın bilinen sistematik sınırı.
    kk = geo.get("keskin_kenar_orani")
    if kk is not None and kk < KESKIN_KENAR_ESIGI and n_layers == 0:
        u.append(f"PÜRÜZSÜZ GÖVDE (keskin-kenar oranı {kk:.3f} < {KESKIN_KENAR_ESIGI}): "
                 "ayrılma noktası geometriyle sabitlenmiyor, sınır-tabaka geçişine bağlı. "
                 "Duvar-fonksiyonlu tam-türbülanslı RANS bu sınıfta SİSTEMATİK şaşırır "
                 "(küre drag krizi vakası) — Cd yalnız EĞİLİM düzeyindedir. Prizma katmanı "
                 "(--katman) ile y⁺<1 çöz veya sonucu karşılaştırma amaçlı kullan")

    # Üçgen-sayısı uyarısı YALNIZ eğrilik varken anlamlı: küp tam 12 üçgendir, bu bir
    # yaklaşım değil kesin geometridir (ara açı oranı 0 → çok-yüzlü). Fasetli bir eğride
    # (küre/silindir) ara açılar dolar ve düşük üçgen sayısı gerçek bir çözünürlük sorunudur.
    n_ucgen = geo.get("ucgen_sayisi") or 0
    egrilik = geo.get("fasetli_egrilik_orani")
    if 0 < n_ucgen < 100 and (egrilik is None or egrilik > 0.0):
        u.append(f"GEOMETRİ ÇÖZÜNÜRLÜĞÜ: yalnız {n_ucgen} üçgen ve yüzeyde eğrilik var — "
                 "eğrilik fasetli, yüzey basıncı ve ayrılma noktası temsili olmayabilir")
    return u


def force_admissibility(Cd, Cl=None, alpha=None, cd_max=CD_MAX_PLAUSIBLE):
    """Kuvvet katsayıları FİZİKSEL olarak kabul edilebilir mi? (zarf sınıfından ÖNCE gelir)

    İterasyon yakınsaması ve mesh kalitesi SAYISAL ölçütlerdir; fiziksel imkânsızlığı
    yakalamazlar. Wake-kümelemesiz kaba grid negatif basınç sürüklemesi üretiyor ve drift
    küçük olduğu için "yakınsadı" görünüyordu — hüküm elle yazılan dipnotta kalıyordu.
    Bu kapı onu hesaplanabilir yapar; fizik-dışı sayı hiçbir zarf sınıfıyla kurtarılamaz.

    `cd_max`: varsayılan EVRENSEL sınır (2.5). Çağıran geometrinin akış-yönlü olduğunu
    biliyorsa `CD_MAX_STREAMLINED` geçirir; künt cisim (küp, araç, paraşüt) analizinde
    varsayılan kalmalıdır — aksi halde geçerli sonuç haksız yere reddedilir.

    Döner: {"verdict": "ok"|"suspect"|"inadmissible", "reasons": [...]}
    """
    reasons, verdict = [], "ok"
    # NaN ÖNCE: NaN ile yapılan HER karşılaştırma False döner, dolayısıyla aşağıdaki
    # `<= 0` ve `> cd_max` kontrolleri NaN'ı ıskalar ve kapı "ok" derdi (Inf yakalanıyordu
    # ama NaN geçiyordu). forceCoeffs başlığı değişince parser NaN üretebiliyor.
    for _ad, _v in (("sürükleme", Cd), ("taşıma", Cl)):
        if _v is not None and not math.isfinite(_v):
            reasons.append(f"{_ad} katsayısı sonlu değil ({_v}) — çözüm ıraksadı "
                           "veya kuvvet dosyası okunamadı")
            verdict = "inadmissible"
    if verdict == "inadmissible":
        return {"verdict": verdict, "reasons": reasons}
    if Cd is not None:
        if Cd <= 0:
            reasons.append(f"negatif/sıfır sürükleme (Cd={Cd:.5f}) — fiziksel olarak imkânsız")
            verdict = "inadmissible"
        elif abs(Cd) > cd_max:
            reasons.append(f"makul olmayan sürükleme mertebesi (Cd={Cd:.4f} > {cd_max})")
            verdict = "inadmissible"
    if Cl is not None:
        if abs(Cl) > CL_MAX_PLAUSIBLE:
            reasons.append(f"makul olmayan taşıma (|Cl|={abs(Cl):.2f} > {CL_MAX_PLAUSIBLE})")
            verdict = "inadmissible"
        elif alpha is not None and abs(alpha) > 2.0 and Cl * alpha < 0 and verdict != "inadmissible":
            reasons.append(f"taşıma işareti hücum açısıyla ters (α={alpha}°, Cl={Cl:.3f})")
            verdict = "suspect"
    return {"verdict": verdict, "reasons": reasons}


SF_MAKUL_UST = 100.0        # üstü: dikkat çekilir ama REDDEDİLMEZ (bkz. aşağıdaki not)
GERILME_TABAN_MPA = 1e-6    # bunun altı sayısal sıfır (çift-duyarlık gürültüsü)


def stress_admissibility(max_vm_mpa=None, yield_mpa=None, sf=None,
                         max_disp_mm=None, uygulanan_yuk_n=None) -> dict:
    """Yapısal sonucun FİZİKSEL kabul-edilebilirliği — `force_admissibility`'nin eşi.

    En tehlikeli yapısal başarısızlık "yüksek gerilme" değil, YÜKÜN HİÇ AKTARILMAMASIDIR:
    ccx sıfır dönüş kodu verir, .frd okunur, gerilme ~0 çıkar, SF astronomik olur ve
    rapor "çok güvenli" der; hiçbir şey test edilmemişken güvenli hükmü verilir.

    ÖLÇÜT SEÇİMİ (gerçek çözücü koşusuyla düzeltildi): "σ akmaya göre küçük" ölçütü
    YANLIŞTI — 20 m/s'de 0.4 m'lik bir plakada σ=0.12 MPa fiziksel olarak DOĞRUDUR
    (yapı sadece fazlasıyla güvenli). Hafif yüklü gerçek aero-yapısal vakaların
    neredeyse tamamı akmanın binde birinin altındadır. Doğru ölçüt gerilmenin akmaya
    oranı değil, UYGULANAN YÜKE karşı tepkinin olup olmadığıdır.

    Döner: {"verdict": "ok"|"suspect"|"inadmissible", "reasons": [...]}
    """
    reasons, verdict = [], "ok"
    yuklu = uygulanan_yuk_n is None or (math.isfinite(uygulanan_yuk_n)
                                        and abs(uygulanan_yuk_n) > 0)
    # Statik analizde yükün KENDİSİ sıfırsa sonuç anlamsızdır: kullanıcı yüklü analiz
    # istedi, basınç alanı boş geldi (CFD çözülmemiş / yanlış patch / birim hatası).
    # Sıfır gerilme burada "meşru" değildir — hiçbir şey sorulmamış demektir.
    if uygulanan_yuk_n is not None and math.isfinite(uygulanan_yuk_n) and uygulanan_yuk_n == 0:
        reasons.append("uygulanan toplam kuvvet SIFIR — basınç alanı boş "
                       "(CFD çözülmemiş, yanlış yüzey patch'i veya birim hatası); "
                       "statik sonuç anlamsız")
        verdict = "inadmissible"
    if max_vm_mpa is not None:
        if not math.isfinite(max_vm_mpa):
            reasons.append("gerilme alanı sonlu değil (NaN/Inf) — çözüm ıraksadı")
            verdict = "inadmissible"
        elif max_vm_mpa <= GERILME_TABAN_MPA and yuklu:
            reasons.append(
                f"gerilme sayısal sıfır (σ_max={max_vm_mpa:.3g} MPa)"
                + (f" oysa {abs(uygulanan_yuk_n):.3g} N yük uygulandı"
                   if uygulanan_yuk_n else "")
                + " — yük yapıya AKTARILMAMIŞ (yük seti/mesnet tanımı boş olabilir)")
            verdict = "inadmissible"
    if (max_disp_mm is not None and math.isfinite(max_disp_mm)
            and max_disp_mm == 0 and yuklu):
        reasons.append("hiçbir düğüm hareket etmemiş — model tümüyle ankastre veya yüksüz")
        verdict = "inadmissible"
    if sf is not None and math.isfinite(sf) and sf > SF_MAKUL_UST and verdict == "ok":
        # UYARI, ret DEĞİL: ön-tasarımda aşırı güvenli yapı meşrudur. Yine de yük
        # ölçeği/birim hatası da aynı imzayı verir; mühendis ayırt etsin.
        reasons.append(f"emniyet faktörü {sf:.0f} (> {SF_MAKUL_UST:.0f}) — yapı fazlasıyla "
                       "güvenli OLABİLİR ya da yük ölçeği/birimi hatalı; yük büyüklüğünü teyit edin")
        verdict = "suspect"
    return {"verdict": verdict, "reasons": reasons}


def apply_physics_gate(verdicts: list[Verdict], fizik: dict | None) -> list[Verdict]:
    """Fizik kapısı düştüyse zarf sınıflarını indir ve GEREKÇEYİ mesajlara yaz.

    Sınıfı indirip mesajı bırakmak mühendisi yanıltır ("ZARF-DIŞI" başlığın altında
    "tasarım kararı için kullanılabilir" açıklaması). Ladder:
      inadmissible -> hepsi OUT (fizik-dışı sayı hiçbir yorumla kurtarılamaz)
      suspect      -> DOĞRULANMIŞ olanlar EĞİLİM'e iner (şüphe doğrulamayı geçersizler)
    """
    v = (fizik or {}).get("verdict", "ok")
    if v == "ok":
        return verdicts
    gerekce = "; ".join((fizik or {}).get("reasons", [])) or "fiziksel kabul-edilebilirlik kapısı"
    if v == "inadmissible":
        return [Verdict(x.quantity, OUT, False, f"FİZİK KAPISI: {gerekce}") for x in verdicts]
    return [Verdict(x.quantity, TREND if x.klass == VALIDATED else x.klass, False,
                    f"FİZİK KAPISI (şüpheli): {gerekce}") for x in verdicts]


def sonuc_kapisi(fizik: dict | None, convergence: dict | None) -> dict:
    """Kullanıcı-yüzü tek hüküm (GUI rozeti / CLI özeti) — ÖNCELİK SIRALI.

    Sıra kritik: fiziksel kabul-edilebilirlik, sayısal yakınsamadan ÖNCE gelir. Yakınsamış
    ama fizik-dışı bir koşuya "✅ yakınsadı" demek mühendisi yanlış sayıya güvendirir.
    Döner: {"seviye": "engel"|"uyari"|"ok", "etiket": str, "gerekce": [...]}
    """
    v = (fizik or {}).get("verdict", "ok")
    if v == "inadmissible":
        return {"seviye": "engel", "etiket": "⛔ fizik-dışı",
                "gerekce": list((fizik or {}).get("reasons", []))}
    if v == "suspect":
        return {"seviye": "uyari", "etiket": "⚠️ fizik şüpheli",
                "gerekce": list((fizik or {}).get("reasons", []))}
    c = convergence or {}
    if c.get("drift_ok") and c.get("rezidual_ok"):
        return {"seviye": "ok", "etiket": "✅ yakınsadı", "gerekce": []}
    eksik = [ad for ad, anahtar in (("kuvvet drifti", "drift_ok"), ("rezidüel", "rezidual_ok"))
             if not c.get(anahtar)]
    return {"seviye": "uyari", "etiket": "⚠️ sınırda",
            "gerekce": [f"{', '.join(eksik)} hedefin dışında"] if eksik else []}


def classify_cfd(vehicle_type: str, alpha_deg: float, mach: float,
                 has_gci_band: bool = False, band_pct: float | None = None) -> list[Verdict]:
    """CFD aerodinamik çıktılarının zarf sınıfı. has_gci_band: 3-mesh asimptotik GCI var mı."""
    a = abs(alpha_deg or 0.0)
    compressible = (mach or 0.0) >= MACH_INCOMP
    v: list[Verdict] = []

    # ── TAŞIMA (C_L) ──
    if a > ALPHA_VALID_DEG:
        v.append(Verdict("C_L (taşıma)", OUT, False,
            f"α={alpha_deg:.0f}° > {ALPHA_VALID_DEG:.0f}°: 2D RANS taşımayı ~%45 DÜŞÜK tahmin "
            "eder (erken stall — α=10/12°'de ölçüldü). Tasarım sayısı DEĞİL; yalnız "
            "'bu açıda stall başlıyor' sezgisi için."))
    elif compressible:
        v.append(Verdict("C_L (taşıma)", TREND, False,
            f"Ma={mach:.2f}≥0.3 sıkışabilir rejim — taşıma yalnız eğilim düzeyinde."))
    else:
        v.append(Verdict("C_L (taşıma)", VALIDATED, True,
            f"Bağlı akış (|α|≤{ALPHA_VALID_DEG:.0f}°): NACA0012'de NASA Ladson'a karşı ≤%8 — "
            "tasarım kararı için kullanılabilir."))

    # ── SÜRÜKLEME (C_D, mutlak) ──
    if has_gci_band:
        v.append(Verdict("C_D (sürükleme)", VALIDATED, True,
            "3-mesh GCI asimptotik bandı — mutlak değer savunulabilir."))
    elif compressible:
        v.append(Verdict("C_D (sürükleme)", TREND, False,
            "Süpersonik inviscid kayma-duvar taban-drag'ı ~%15 fazla — mutlak Cd tasarım "
            "sayısı DEĞİL; Mach-eğilimi ve A/B karşılaştırması güvenilir."))
    else:
        extra = f" (2-mesh duyarlılık ±%{band_pct})" if band_pct is not None else ""
        v.append(Verdict("C_D (sürükleme)", TREND, False,
            "Mutlak sürükleme bu O-grid ailesinde mesh-yakınsamadı (gözlenen mertebe "
            f"p≈0.2){extra} — tasarım sayısı DEĞİL; yalnız A/B karşılaştırması ve eğilim."))

    # ── L/D ve sürükleme kuvveti: mutlak Cd'ye bağlı → en zayıfı miras alır ──
    v.append(Verdict("L/D, sürükleme kuvveti/gücü", TREND, False,
        "Mutlak sürüklemeden türetilir → tasarım sayısı değil; karşılaştırmalı kullanın."))
    return v


def classify_fea(has_singularity: bool = False,
                 buckling_margin: float | None = None) -> list[Verdict]:
    """FEA yapısal çıktılarının zarf sınıfı (tasarım-güvenli kısım).

    buckling_margin: λ_kritik / yük (verilirse stabilite verdikti eklenir). λ>1 stabil."""
    v = [Verdict("Gerilme (temsili, %99-persentil)", VALIDATED, True,
        "6 kanonik V&V %0.0–4.8 (kuvvet/basınç/gövde/termal/buckling) — temsili gerilme "
        "ve emniyet faktörü tasarım kararı için kullanılabilir.")]
    if has_singularity:
        v.append(Verdict("Tepe gerilme (tekillik noktası)", TREND, False,
            "Sivri-köşe tekilliği: tepe değer mesh inceldikçe büyür, fiziksel değil — "
            "temsili (%99-persentil) değeri kullanın."))
    if buckling_margin is not None:
        # Lineer-elastik özdeğer burkulması Euler'e %0.2 doğrulandı (fea_validation_buckling).
        # İdeal-geometri üst-sınırdır: gerçek kusur/eksantriklik kritik yükü DÜŞÜRÜR → marj
        # 1'e yakınsa güvenli değil; muhafazakâr tasarım marjı ≥1.5 beklenir.
        safe = buckling_margin >= 1.5
        v.append(Verdict("Burkulma marjı (lineer özdeğer)",
            VALIDATED if safe else TREND, safe,
            f"λ={buckling_margin:.2f}× — *BUCKLE yolu Euler'e %0.2 doğrulandı. "
            "İdeal-geometri ÜST-SINIRıdır; imalat kusuru/eksantriklik kritik yükü düşürür, "
            f"bu yüzden marj ≥1.5 beklenir ({'sağlandı' if safe else 'SAĞLANMADI — yalnız eğilim'})."))
    return v


def overall_class(verdicts: list[Verdict]) -> str:
    return max((x.klass for x in verdicts), key=lambda k: _RANK[k], default=VALIDATED)


# Bilinen airfoil deneysel CLmax referansları (yalnız VALİDE kaynaktan; CFD'den DEĞİL).
# NACA0012: Ladson NASA TM-4074 / TMR, Re=6×10⁶ — α=15° Cl=1.4938 (sourced).
CLMAX_REF = {
    "naca0012": (1.49, 15.0, "Ladson NACA0012, Re=6×10⁶ (NASA TMR)"),
}


@dataclass
class PolarEnvelope:
    alpha_envelope_max: float
    stall_onset_detected: bool
    stall_onset_alpha: float | None
    cfd_clmax_apparent: float | None    # CFD'nin GÖRÜNÜR tepesi — CLmax DEĞİL (düşük tahmin)
    clmax_reference: tuple | None       # (CLmax, α, kaynak) — DENEYSEL, CFD'den değil
    verdict: str


def analyze_polar_envelope(polar, alpha_valid: float = ALPHA_VALID_DEG,
                           clmax_ref: tuple | None = None) -> PolarEnvelope:
    """Polar eğrisinden ÇALIŞMA-ZARFI sınırını çıkarır — CLmax-bandı DEĞİL.
    Stall-onset yalnız 'zarf dışına çıkış sinyali' olarak işaretlenir; CLmax bu CFD'den
    TÜRETİLMEZ (steady-RANS stall'ı ~%45 düşük verir). Gerçek CLmax yalnız deneysel
    referanstan (clmax_ref) gelir. polar: [{'alpha','Cl', opsiyonel 'Cd'}, ...]."""
    pts = sorted(((float(p["alpha"]), float(p["Cl"]),
                   (float(p["Cd"]) if p.get("Cd") is not None else None))
                  for p in polar), key=lambda t: t[0])
    onset = None
    if len(pts) >= 3:
        slope0 = None
        for i in range(1, len(pts)):                 # ilk lineer eğim (referans)
            da = pts[i][0] - pts[0][0]
            if da > 0:
                slope0 = (pts[i][1] - pts[0][1]) / da
                break
        for i in range(1, len(pts)):
            (a0, cl0, cd0), (a1, cl1, cd1) = pts[i - 1], pts[i]
            da = a1 - a0
            if da <= 0:
                continue
            dcl = (cl1 - cl0) / da
            rollover = cl1 <= cl0                                  # taşıma düştü
            slope_break = slope0 is not None and dcl < 0.4 * slope0  # eğim sert kırıldı
            # Cd sıçraması yalnız POZİTİF Cd'de anlamlı (mutlak Cd güvenilmez/negatif olabilir
            # → oran spurious tetikler); asıl fiziksel sinyal Cl-rollover ve eğim-kırılması.
            cd_jump = (cd0 is not None and cd1 is not None and cd0 > 0 and cd1 > 1.8 * cd0)
            if a1 > alpha_valid * 0.5 and (rollover or slope_break or cd_jump):
                onset = a1
                break
    cfd_peak = max((c for _, c, _ in pts), default=None)
    if clmax_ref:
        ref = f"CLmax≈{clmax_ref[0]} @ α≈{clmax_ref[1]:.0f}° ({clmax_ref[2]})"
        verdict = (f"Bu RANS çözümü CLmax tahmini için GEÇERLİ DEĞİLDİR; α>{alpha_valid:.0f}° "
                   "sonuçları tasarım/validasyon girdisi yapılmamalıdır. Eğrideki kırılma "
                   "yalnız çalışma-zarfı sınır uyarısıdır — CLmax bu CFD'den TÜRETİLMEMİŞTİR. "
                   f"Deneysel referans: {ref}.")
    else:
        verdict = (f"Bu RANS çözümü CLmax tahmini için GEÇERLİ DEĞİLDİR; α>{alpha_valid:.0f}° "
                   "sonuçları tasarım/validasyon girdisi yapılmamalıdır. Bu geometri için "
                   "deneysel CLmax referansı tanımlı değil — CLmax CFD'den TAHMİN EDİLMEMELİDİR.")
    return PolarEnvelope(alpha_valid, onset is not None, onset, cfd_peak, clmax_ref, verdict)


def polar_envelope_md(env: PolarEnvelope) -> str:
    """Polar raporuna giren dürüst çalışma-zarfı bloğu (CLmax-bandı değil, sınır uyarısı)."""
    lines = ["> 🔴 **ÇALIŞMA ZARFI — TAŞIMA / STALL**", ">",
             f"> - Doğrulanmış üst sınır: **α ≤ {env.alpha_envelope_max:.0f}°** (bağlı akış, "
             "Ladson'a ≤%8).  "]
    if env.stall_onset_detected:
        ap = f"{env.cfd_clmax_apparent:.2f}" if env.cfd_clmax_apparent is not None else "?"
        lines.append(f"> - Eğride kırılma **α≈{env.stall_onset_alpha:.0f}°**'de saptandı — yalnız "
                     f"ZARF-SINIRI sinyali (CFD görünür tepe Cl≈{ap}; **bu CLmax DEĞİL**, "
                     "yöntem stall'da ~%45 düşük).  ")
    if env.clmax_reference:
        c = env.clmax_reference
        lines.append(f"> - Gerçek CLmax (yalnız deneysel referans): **≈{c[0]} @ α≈{c[1]:.0f}°** "
                     f"({c[2]}).  ")
    lines.append(">")
    lines.append(f"> {env.verdict}")
    lines.append("")
    return "\n".join(lines)


def banner_md(verdicts: list[Verdict]) -> str:
    """Raporun EN BAŞINA giren, belirsizlik-sınıfını DAYATTIRAN uyarı bloğu (çocuk-okunur)."""
    oc = overall_class(verdicts)
    head = {
        VALIDATED: "✅ **BU SONUÇLAR TASARIM İÇİN KULLANILABİLİR** (doğrulanmış zarf içinde).",
        TREND: "🟡 **DİKKAT — BAZI SONUÇLAR YALNIZ EĞİLİM.** Tasarım kararı vermeden önce oku.",
        OUT: "🔴 **UYARI — SONUÇ DOĞRULANMIŞ ZARFIN DIŞINDA.** Sayıları tasarımda KULLANMA.",
    }[oc]
    lines = [f"> {head}", ">",
             "> | Büyüklük | Sınıf | Tasarımda kullanılır mı? |",
             "> |---|---|---|"]
    for x in verdicts:
        lines.append(f"> | {x.quantity} | {_ICON[x.klass]} {_TR[x.klass]} | "
                     f"{'Evet' if x.design_safe else 'HAYIR — yalnız karşılaştırma/sezgi'} |")
    unsafe = [x for x in verdicts if not x.design_safe]
    if unsafe:
        lines.append(">")
        for x in unsafe:
            lines.append(f"> {_ICON[x.klass]} **{x.quantity}:** {x.message}")
    lines.append("")
    return "\n".join(lines)
