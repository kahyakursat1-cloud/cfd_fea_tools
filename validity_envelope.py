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
from dataclasses import dataclass, field

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
# TAŞIMA SINIRI TEK SAYI OLAMAZ. 3.0'lık evrensel eşik iki yönde de yanlıştı:
# çok-elemanlı yüksek-taşıma kesitini (slat+flap, CLmax 3.5-4.5) HAKSIZ reddediyor,
# AR=6 düz bir kanadın fiziksel tavanı ~1.5 iken 2× yanlış bir sayıyı SESSİZCE
# geçiriyordu. Sınır rejime bağlıdır ve her biri kaynaklıdır.
CL_MAX_REJIM = {
    # tek-elemanlı 2B kesit: NACA 4/5-haneli CLmax 1.5-1.8 (Abbott & von Doenhoff,
    # Theory of Wing Sections); modern laminer kesitlerde ~2.0'a çıkar
    "2b_tek_elemanli": 2.2,
    # çok-elemanlı yüksek-taşıma: slat+çift flap CLmax 3.5-4.5 (A.M.O. Smith 1975,
    # "High-Lift Aerodynamics"); üst sınır olarak 4.5
    "2b_cok_elemanli": 4.5,
    # sonlu düz kanat: 3B kayıp nedeniyle CLmax_3B ≈ 0.9·CLmax_2B, artı indüklenmiş
    # açı kaybı — AR 5-10 için 1.4-1.6 (Anderson, Aircraft Performance and Design)
    "3b_duz_kanat": 1.8,
    # delta / kırlangıç: girdap taşıması ile doğrusal-ötesi kazanç (Polhamus 1966)
    "3b_delta": 1.6,
    # künt cisim: taşıma tasarım amacı değil; ölçülen yan/taşıma kuvveti küçüktür
    "kunt": 0.8,
}
# REJİM BEYAN EDİLMEZSE en gevşek sınır uygulanır — çünkü daha sıkı bir sınır
# uygulamak, hangi rejimde olduğunu bilmediğimiz geçerli bir sonucu reddetmek olur.
# Bunun bedeli kapının zayıflamasıdır ve bu SÖYLENİR (bkz. force_admissibility).
CL_MAX_PLAUSIBLE = max(CL_MAX_REJIM.values())

_TR = {VALIDATED: "DOĞRULANMIŞ", TREND: "YALNIZ-EĞİLİM", OUT: "ZARF-DIŞI"}
_ICON = {VALIDATED: "✅", TREND: "🟡", OUT: "🔴"}
_RANK = {VALIDATED: 0, TREND: 1, OUT: 2}


@dataclass
class Verdict:
    quantity: str
    klass: str
    design_safe: bool
    message: str
    # KARARLI MAKİNE KODU. `message` sunumdur ve dile göre değişir; `kod`
    # sözleşmenin parçasıdır ve değişmez. Türkçe okumayan bir tüketici
    # (Erasmus+ ortağı) hükmü kod üzerinden ayırt edebilsin diye eklendi.
    # Varsayılan boş: kodu olmayan bir hüküm hâlâ geçerlidir, yalnız
    # makine düzeyinde ayırt edilemez ve bir test bunu sayar.
    kod: str = ""
    parametreler: dict = field(default_factory=dict)


def _mesaj(kod: str, **p) -> str:
    """Hüküm gerekçesinin TÜRKÇE metni --- katalogdan, elle değil.

    Metin burada değil `mesajlar.py`de durur, çünkü aynı cümlenin ikinci bir
    dilde de yaşaması gerekiyor ve iki dilin iki ayrı yerde tutulması bu
    deponun tekrar tekrar ölçtüğü ayrışmayı üretir. Türkçe şablonlar mevcut
    metnin BİREBİR aynısıdır; bu bir yeniden yazım değil, tek-kaynağa toplamadır.
    """
    from mesajlar import VARSAYILAN_DIL, gerekce_metni
    return gerekce_metni(kod, VARSAYILAN_DIL, **p)


HAVA_NU = 1.5e-5          # m²/s, ~15 °C
OLCEK_BUYUK_M = 100.0     # üstü: mm/inç ölçek hatası şüphesi (10 m'lik model 1000× → 10 km)
OLCEK_KUCUK_M = 0.005     # altı: m yerine mm girilmiş küçük parça şüphesi


# PARÇALANMIŞ GEOMETRİ EŞİĞİ. Tek parça bir araç 1-3 gövdeden oluşur (gövde+kanat
# ayrı ihraç edilmiş olabilir). Onlarca kopuk kabuk, CAD ihracının yüzeyi
# birleştirmediğini gösterir ve snappyHexMesh'in yakalayacağı kapalı bir yüzey yoktur.
GOVDE_SAYISI_ESIGI = 10
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

    # PARÇALANMIŞ GEOMETRİ — ÇÖZÜCÜDEN ÖNCE, çünkü snappyHexMesh bunu ZAMAN
    # AŞIMIYLA öğretiyor. ÖLÇÜLDÜ (su57): 1398 ayrı gövde, su geçirmez DEĞİL,
    # 354.710 üçgen. snappy 1398 kopuk kabuğu yakalamaya çalışıp snap aşamasında
    # 310.719 bozuk yüz üretti ve 30 dk sınırını doldurdu — DÖRT koşu boyunca.
    # Ölçek onarımı çalışmıştı (mm→m) ama gövdeleri BİRLEŞTİRMEZ.
    #
    # Bu, hücre bütçesiyle ilgili DEĞİL: kaç hücre verilirse verilsin parçalanmış
    # bir yüzeyde güvenilir mesh çıkmaz. `govde_sayisi` prepare_geometry'de ZATEN
    # ölçülüyordu ve hiçbir kapı onu tüketmiyordu.
    nb = (geo.get("hazirlik") or {}).get("govde_sayisi")
    if nb and nb >= GOVDE_SAYISI_ESIGI:
        u.append(f"PARÇALANMIŞ GEOMETRİ: model {nb} AYRI gövdeden oluşuyor "
                 f"(eşik {GOVDE_SAYISI_ESIGI})"
                 + ("" if geo.get("su_gecirmez") else " ve su geçirmez DEĞİL")
                 + ". snappyHexMesh yakalayacağı KAPALI bir yüzey bulamaz; snap "
                 "aşaması bozuk yüz üretir ve mesh adımı zaman aşımına düşer "
                 "(ölçüldü: 1398 gövdeli bir modelde 310.719 bozuk yüz, 30 dk aşım). "
                 "Bu bir hücre bütçesi sorunu DEĞİLDİR — önce geometri onarımı "
                 "(kabukları birleştir / su geçirmez hale getir) gerekir")

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


_ARAC_REJIMI = {"ucak": "3b_duz_kanat", "roket": "kunt", "multikopter": "kunt",
                "araba": "kunt", "genel": "kunt"}


def rejim_arac_tipinden(vehicle_type: str | None) -> str | None:
    """Araç tipi → taşıma-sınırı rejimi. Bilinmeyen tip için None (kapı gevşer,
    ve gevşediği SÖYLENİR) — tahminle bir rejime atamak, hangi sınırın
    uygulandığını gizler."""
    return _ARAC_REJIMI.get(vehicle_type or "")


def cl_siniri(rejim: str | None) -> tuple[float, str]:
    """(|Cl| üst sınırı, kaynak metni). Rejim bilinmiyorsa EN GEVŞEK sınır."""
    if rejim in CL_MAX_REJIM:
        return CL_MAX_REJIM[rejim], f"rejim='{rejim}'"
    return CL_MAX_PLAUSIBLE, (
        f"REJİM BEYAN EDİLMEDİ ({rejim!r}) — en gevşek sınır ({CL_MAX_PLAUSIBLE}) "
        "uygulandı; bu kapı zayıftır ve 3B düz kanat için ~2.5× fazla toleranslıdır")


def force_admissibility(Cd, Cl=None, alpha=None, cd_max=CD_MAX_PLAUSIBLE,
                        rejim: str | None = None):
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
    cl_max, cl_kaynak = cl_siniri(rejim)
    if Cl is not None:
        if abs(Cl) > cl_max:
            reasons.append(f"makul olmayan taşıma (|Cl|={abs(Cl):.2f} > {cl_max}; "
                           f"{cl_kaynak})")
            verdict = "inadmissible"
        elif alpha is not None and abs(alpha) > 2.0 and Cl * alpha < 0 and verdict != "inadmissible":
            reasons.append(f"taşıma işareti hücum açısıyla ters (α={alpha}°, Cl={Cl:.3f})")
            verdict = "suspect"
    out = {"verdict": verdict, "reasons": reasons}
    if Cl is not None:
        # KAPININ NE KADAR SIKI OLDUĞU da bir çıktıdır: rejim beyan edilmediyse
        # "fizik kapısı geçti" cümlesi çok daha az şey söylüyor demektir.
        out["cl_kapisi"] = {"sinir": cl_max, "rejim": rejim, "kaynak": cl_kaynak,
                            "beyan_edildi": rejim in CL_MAX_REJIM}
    return out


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
        return [Verdict(x.quantity, OUT, False, _mesaj("FIZIK_KAPISI", gerekce=gerekce),
                        "FIZIK_KAPISI", {"gerekce": gerekce}) for x in verdicts]
    return [Verdict(x.quantity, TREND if x.klass == VALIDATED else x.klass, False,
                    _mesaj("FIZIK_KAPISI_SUPHELI", gerekce=gerekce),
                    "FIZIK_KAPISI_SUPHELI", {"gerekce": gerekce}) for x in verdicts]


# SIRKULASYONA BAGLI BUYUKLUKLER — firar kenari cozulmezse bunlar KURULMAZ.
# Taşıma ve moment Kutta kosulundan dogar; keskin firar kenari agda temsil
# edilmiyorsa sirkulasyon fiziksel olarak belirlenmemistir. Direnc farklidir:
# basinc direncinin ana bileseni govdeden gelir ve yakalanir, yalniz ozelligin
# kendi katkisi eksik kalir. Bu yuzden hukum BUYUKLUGE GORE ayrilir.
_SIRKULASYON_QOI = ("C_L", "C_M", "L/D", "CL", "CM", "L_D")


def _sirkulasyona_bagli(quantity: str) -> bool:
    q = (quantity or "").upper().replace(" ", "")
    return any(q.startswith(k.upper()) or k.upper() in q for k in _SIRKULASYON_QOI)


# SUBKRITIK Re BANDI — bu aralikta kunt cisimde BAGLI sinir tabaka LAMINERDIR.
# Ust ucta (~3e5) surukleme krizi baslar ve tabaka kendiliginden turbulanslasir;
# orada tam-turbulansli kapanis savunulabilir hale gelir.
SUBKRITIK_RE = (1.0e4, 2.0e5)

# TAM-TURBULANSLI kapanislar: bagli tabakayi bastan turbulansli sayarlar.
# `kOmegaSSTLM` (Langtry-Menter) gecis modelidir ve bu listede DEGILDIR.
_TAM_TURBULANSLI = ("komegasst", "kepsilon", "komegassstdes", "komegasstdes",
                    "spalartallmaras", "kkl", "realizablke")

# OLCULEN SAPMALAR — silindir capalari, Re=1,4e5, ayni kurulum ailesi.
# Kaynak: silindir_urans_3b.json, silindir_des_3b.json
SUBKRITIK_OLCUM = {
    "3B URANS (kOmegaSST)": {"Cd_pct": -26.88, "St_pct": 29.74},
    "3B DES (kOmegaSSTDES)": {"Cd_pct": -39.16, "St_pct": 38.16},
}


# GECIS MODELI BIR COZUM DEGIL, BIR IMKANDIR — VE KOSULLUDUR.
# Bu metin ONERI olarak yazilmisti ("gecis modeli ya da LES gerekir").
# 2026-08-23'te SINANDI ve oneri o haliyle EKSIK cikti: kOmegaSSTLM ayni agda
# kosuldu, sapma degismedi (Cd %-27,55) AMA sebep modelin yetersizligi degildi
# --- gammaInt her yerde ~1 kaldi (min 0,9869, laminer hucre %0,0), yani model
# hic devreye girmedi ve tam-turbulansli kOmegaSST'ye DEJENERE oldu. Sebep
# serbest-akis turbulans siddeti: TI=%1 gecisi hemen tetikliyor, oysa subkritik
# silindir deneyleri ~%0,1'de yapilir. Bir oneriyi sinamadan yazmak, onu
# olculmus gibi gostermektir; kayit duzeltildi.
GECIS_MODELI_KAYDI = (
    "Geçiş modeli (kOmegaSSTLM) ya da duvar-çözümlü LES gerekir; ikincisi bu "
    "donanımda sığmaz (84,7 M hücre / 62,9 GB). BİRİNCİSİ AĞ İSTER, KAPANIŞ "
    "DEĞİL: modeli seçmek onu ÇALIŞTIRMAZ. DÖRT KOŞU ölçüldü — Tu %1 ve %0,1 "
    "(gammaInt min 0,9869 / 0,9867), sonra nut duvar işlemi düzeltilerek "
    "(0,9872) — model hiçbirinde devreye girmedi. Sebep ağdı: ölçülen y⁺ 24,9, "
    "oysa LM y⁺≲1 ister; duvar-fonksiyonu ağına düşük-Re alanı koymak ilk "
    "hücreyi tampon tabakada bırakır ve Cd %−26,88'den %−62,63'e düşer. "
    "Duvar-çözünür silindir ağı ELDE VAR (silindir_des_3b: y⁺=0,78, 2,43 M "
    "hücre) ama URANS ağının ~6 katıdır. Aralıklılık (gammaInt<0,5 hücre "
    "oranı) DENETLENMEDEN geçiş modeli koşusu delil sayılmaz.")


def subkritik_kapanis_hukmu(rejim: str | None, Re: float | None,
                            turbulence_model: str | None) -> dict:
    """Subkritik Re'de künt cisim + TAM-TÜRBÜLANSLI kapanış = ölçülmüş büyük hata.

    NEDEN: model-form tablosu bu koşuya `bluff`/`separated` diyor ve
    %9,31--25 band veriyor. Ama TAM BU konfigürasyonun ölçülen hatası
    Cd %--27 (3B URANS) ve %--39 (3B DES) --- band hatayı 1,6--4 kat EKSİK
    gösteriyor.

    Sapmanın kaynağı ölçüldü, çıkarsanmadı: aynı ağ önce duvar-fonksiyonuyla
    (y⁺=0,009, geçersiz) sonra düşük-Re ile (y⁺=0,78, geçerli) koşuldu ve
    cevap %1'den az değişti. Yani sorun çözünürlük ya da duvar işlemi DEĞİL,
    KAPANIŞ. Subkritik Re'de bağlı sınır tabaka LAMİNERDİR; tam-türbülanslı
    kapanış onu türbülans sayar, ayrılmayı geciktirir, izi daraltır.

    Fiziksel doğru kurulum duvar-çözümlü LES'tir ve bu makinede sığmaz
    (84,7 M hücre / 62,9 GB --- silindir_les_fizibilite.json).

    Bu bir BAND GENİŞLETME değil UYARIDIR: %39'luk bir hatayı banda gömmek,
    ölçülmüş bir kusuru belirsizlik gibi göstermek olurdu.
    """
    if not rejim or Re is None or not turbulence_model:
        return {"tetiklendi": False,
                "neden": "rejim, Re ya da türbülans modeli bilinmiyor — "
                         "DEĞERLENDİRİLMEDİ (yokluk 'sorun yok' sayılmaz)"}
    kunt = rejim in ("bluff", "separated")
    lo, hi = SUBKRITIK_RE
    bandda = lo <= float(Re) <= hi
    tam_turb = turbulence_model.lower().replace("_", "") in _TAM_TURBULANSLI
    if not (kunt and bandda and tam_turb):
        return {"tetiklendi": False,
                "neden": (f"rejim={rejim}, Re={float(Re):.3g}, "
                          f"model={turbulence_model} — üç koşul birlikte "
                          f"sağlanmıyor")}
    en_kotu = min(v["Cd_pct"] for v in SUBKRITIK_OLCUM.values())
    return {
        "tetiklendi": True,
        "Re": float(Re), "rejim": rejim, "model": turbulence_model,
        "olculen_sapmalar": SUBKRITIK_OLCUM,
        "en_kotu_Cd_pct": en_kotu,
        "hukum": (
            f"SUBKRİTİK Re'DE TAM-TÜRBÜLANSLI KAPANIŞ (Re={float(Re):.2g}, "
            f"{turbulence_model}): bağlı sınır tabaka bu rejimde LAMİNERDİR ve "
            f"kapanış onu türbülans sayar — ayrılma gecikir, iz daralır, Cd "
            f"düşük çıkar. Silindir çapalarında ÖLÇÜLDÜ: Cd %{-en_kotu:.0f}'a "
            f"kadar düşük (3B DES), St %38 yüksek. Model-form bandı (%9-25) bu "
            f"hatayı KAPSAMAZ. {GECIS_MODELI_KAYDI}"),
    }




def _gecis_kapisi(verdicts: list, r) -> list:
    """Geçiş kapısını KOŞU KAYDINDAN besle — tek yerde, iki kanal için.

    `_subkritik_uyari` ile aynı desen: kapının bir kanalda görünüp öbüründe
    susması bu deponun tekrar tekrar ürettiği kusurdur.
    """
    return apply_gecis_gate(verdicts, getattr(r, "gecis_aralikligi", None),
                            getattr(r, "turbulence_model", None))


def _subkritik_uyari(r) -> dict:
    """Subkritik-kapanış kapısını KOŞU KAYDINDAN besle — tek yerde.

    İki sunum kanalı da (hizmet, app_analyzer) aynı yardımcıyı çağırır;
    kapının bir kanalda görünüp öbüründe susması bu deponun tekrar tekrar
    ürettiği kusurdur.
    """
    from validity_envelope import rejim_arac_tipinden, subkritik_kapanis_hukmu
    geo = getattr(r, "geometry", None) or {}
    L = geo.get("lmax_m")
    V = getattr(r, "velocity", None)
    Re = (V * L / 1.5e-5) if (V and L) else None
    # `rejim_arac_tipinden` TASIMA-siniri rejimini verir ("kunt"/"3b_duz_kanat");
    # model-form rejimine cevrilir.
    _r = rejim_arac_tipinden(getattr(r, "vehicle_type", None))
    rejim = "bluff" if _r == "kunt" else ("lifting" if _r else None)
    return subkritik_kapanis_hukmu(rejim, Re,
                                   getattr(r, "turbulence_model", None))


def apply_ince_ozellik_gate(verdicts: list[Verdict],
                            geometri_goreli: dict | None) -> list[Verdict]:
    """İnce özellik çözülmediyse sınıfı BÜYÜKLÜĞE GÖRE ayrı indir.

    Bu kapı, dış incelemenin (2026-08-21) en yerinde bulgusuydu: ölçüm zaten
    yapılıyordu (`openfoam_runner` `ozellik_cozuldu` alanını hesaplıyor) ama
    yalnız KAYIT olarak duruyordu --- tek tüketicisi bir deney betiğiydi,
    geçerlilik sınıfına hiç girmiyordu. Bu deponun baskın kusuru: ölçülür,
    kaydedilir, karara ulaşmaz.

    Bir koşuya TEK ``geçerli'' etiketi vermek yanlıştır, çünkü geometri
    çözünürlüğünün etkisi her çıktı için aynı değildir:
      * C_L, C_M, L/D --> ZARF-DIŞI. Sirkülasyon Kutta koşulundan doğar;
        firar kenarı yoksa taşıma ``belirsiz'' değil KURULMAMIŞTIR.
      * C_D --> DOĞRULANMIŞ ise EĞİLİM'e iner. Basınç direncinin ana bileşeni
        gövdeden gelir ve yakalanır; eksik olan özelliğin kendi katkısıdır ve
        bu bandda YOKTUR. Reddetmek orantısız, ``doğrulanmış'' demek yanlış
        olurdu.
    Ölçüldü: MiniHawk 0,17 hücre/özellik, A320 gövdesi 0,94 --- arşivdeki 12
    koşunun 3'ünde özellik yüzey hücresinden küçük.
    """
    g = geometri_goreli or {}
    if g.get("ozellik_cozuldu") is not False:
        return verdicts            # ölçülmedi ya da çözüldü -> dokunma
    # ANAHTAR URETICININ SEMASINDAN: `openfoam_runner` bunu
    # `ozellik_basina_hucre` olarak yazar. Kendi adimi uydurmak, alani hic
    # okuyamayan sessiz bir kapi uretirdi.
    hucre = g.get("ozellik_basina_hucre")
    esik = OZELLIK_BASINA_HUCRE_ESIK
    if hucre is None:
        return verdicts            # sayı yoksa gerekçe yazılamaz; sessiz inme YOK
    p = {"hucre": float(hucre), "esik": esik}
    out = []
    for x in verdicts:
        if _sirkulasyona_bagli(x.quantity):
            out.append(Verdict(x.quantity, OUT, False,
                               _mesaj("INCE_OZELLIK_SIRKULASYON", **p),
                               "INCE_OZELLIK_SIRKULASYON", dict(p)))
        elif x.klass == VALIDATED:
            out.append(Verdict(x.quantity, TREND, False,
                               _mesaj("INCE_OZELLIK_DIRENC", **p),
                               "INCE_OZELLIK_DIRENC", dict(p)))
        else:
            out.append(x)
    return out


OZELLIK_BASINA_HUCRE_ESIK = 4


def apply_gecis_gate(verdicts: list[Verdict], gecis_aralikligi: dict | None,
                     turbulence_model: str | None) -> list[Verdict]:
    """Geçiş modeli devreye GİRMEDİYSE, sonuç o modelin sonucu değildir.

    Kullanıcı `kOmegaSSTLM` seçer, koşu tamamlanır, bir Cd çıkar --- ve
    aralıklılık her yerde 1 kalmışsa o Cd tam-türbülanslı kOmegaSST'nin
    Cd'sidir. Sayı yanlış değil, ETİKETİ yanlıştır; ve kullanıcı geçiş
    modelinin laminer bölgeyi çözdüğünü VARSAYARAK karar verir.

    ÖLÇÜLDÜ (2026-08-23): aynı serbest-akış şiddetinde (TI=%1) silindir
    devreye girmedi (gammaInt min 0,9869, laminer hücre %0,0), küre girdi
    (min 0,0206, %1,05). Yani bu ayrım girdi ayarından okunamaz, yalnız
    koşunun kendi alanından okunur --- bu yüzden kapı koşudan SONRA çalışır.

    İNDİRME SEVİYESİ: sınıf ZARF-DIŞI'na değil EĞİLİM'e iner. Sonuç geçersiz
    değil, YANLIŞ ADLA gelmiştir; tam-türbülanslı kapanışın kendi geçerlilik
    alanı ayrıca değerlendirilir (subkritik künt cisimde `_subkritik_uyari`
    zaten devreye girer). Reddetmek, ölçülmemiş bir kusuru varsaymak olurdu.
    """
    # MODEL LISTESI TEK KAYNAKTAN. Burada ikinci bir demet yazmak, listeyi
    # genisleten kisinin bu kapiyi sessizce atlamasina yol acardi.
    from analysis.openfoam_runner import GECIS_MODELLERI
    if turbulence_model not in GECIS_MODELLERI:
        return verdicts
    a = gecis_aralikligi or {}
    if a.get("devrede") is not False:
        return verdicts        # devrede ya da ÖLÇÜLEMEDİ -> sessiz inme YOK
    p = {"model": turbulence_model, "min": a.get("min"),
         "laminer_pct": a.get("laminer_hucre_orani_pct")}
    mesaj = (f"{turbulence_model} SEÇİLDİ AMA DEVREYE GİRMEDİ: aralıklılık "
             f"(gammaInt) minimumu {p['min']}, laminer hücre oranı "
             f"%{p['laminer_pct']} — laminer bölge hiç oluşmadı ve çözüm "
             f"tam-türbülanslı kOmegaSST'ye dejenere oldu. Bu sayı geçiş "
             f"modeli sonucu DEĞİLDİR.")
    return [x if x.klass != VALIDATED
            else Verdict(x.quantity, TREND, False, mesaj, "GECIS_DEVREDE_DEGIL",
                         dict(p))
            for x in verdicts]


# QoI-duraganlik esigi: DRIFT_LIMIT_PCT (2.0) 'kabul edilebilir', bu ise 'oturmus'
# demek icin DAHA SIKI. Olculen uc vaka %0.21-%0.80 araliginda kaldi.
QOI_DURAGAN_DRIFT_PCT = 1.0


# SALINIM KABUL EŞİĞİ — limit çevrimini "yakınsadı" saymak DEĞİL, genliği ÖLÇÜLMÜŞ
# ve BANDA KATILMIŞ bir belirsizlik bileşeni olarak kabul etmektir.
# Ölçüldü (12 geometri): salınım genlikleri %0.68-2.5; aynı koşularda MODEL-form
# belirsizliği %12. Yani salınım, zaten raporlanan bandın beşte biri kadar. Böyle bir
# sonucu tümden reddetmek orantısız; ama genliğin bandda GERÇEKTEN olması şart.
SALINIM_KABUL_PCT = 3.0
SALINIM_MODEL_ORANI = 3.0     # genlik, model belirsizliğinin en fazla 1/3'ü olmalı


def sonuc_kapisi(fizik: dict | None, convergence: dict | None,
                 belirsizlik: dict | None = None,
                 kosu: dict | None = None) -> dict:
    """Kullanıcı-yüzü tek hüküm (GUI rozeti / CLI özeti) — ÖNCELİK SIRALI.

    `kosu`: {lref_m, velocity, rejim, sure_s, iterasyon} — verilirse salınan
    koşuya URANS eskalasyon REÇETESİ eklenir. "Kesin çözüm URANS'tır" cümlesi
    tek başına uygulanabilir değildir: zaman adımı, adım sayısı ve maliyet
    olmadan kullanıcı o cümleyle hiçbir şey yapamaz.

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
    # SALINIM: rezidüel ve drift ölçütlerinin İKİSİ de sağlanırken çözüm yine de sabit
    # noktaya oturmamış olabilir — limit çevrimi. Drift, son nokta ile %20-önceki noktayı
    # kıyaslar; salınımın periyodu o pencereye denk gelirse ölçülen drift SIFIRA yakın
    # çıkar. Ölçüldü: Cd ±%4 salınırken drift %1.25 (limit %2) → kapı "✅ yakınsadı"
    # diyordu. Dedektör (salinim_analizi) zaten vardı ve hükme HİÇ girmiyordu.
    # Fiziksel gerekçe: keskin-kenarlı küt cisim ve ayrılmış akış (geriye-basamaklı
    # akış çapasında p rezidüeli 20000 iterasyon boyunca 8e-5'te platoya oturdu).
    sal = c.get("salinim") or {}
    salinimda = bool(sal.get("osilasyon"))
    if c.get("drift_ok") and c.get("rezidual_ok") and not salinimda:
        return {"seviye": "ok", "etiket": "✅ yakınsadı", "gerekce": []}
    # QoI-DURAĞANLIK: "residualControl tetiklenmedi" ile "Cd hâlâ hareket ediyor"
    # AYNI ŞEY DEĞİLDİR. ASME V&V pratiğinde hüküm İLGİLENİLEN BÜYÜKLÜĞÜN
    # yakınsamasına dayanır; rezidüel seviyesi onun VEKİLİDİR. Aynı ayrım 2B NACA2412
    # çapasında kurulmuş ve commit edilmişti (87751f9); araç yolunda uygulanmamıştı.
    #
    # ÖLÇÜLDÜ (güvenilirlik taraması, hassas_nl + ref_bump 2): üç geometri YALNIZ
    # rezidüel yüzünden düştü — Cd sürüklenmesi %0.21 / %0.61 / %0.80, salınım YOK,
    # ~400-500 iterasyon. Bağımsız doğrulama: genel_kup800 Cd=1.0375, literatür
    # (Hoerner, küp) 1.05 → %-1.2. Yani bu koşularda sayı OTURMUŞ.
    #
    # KAPI GEVŞETİLMİYOR: salınan koşu HÂLÂ düşer (limit çevriminde Cd nerede
    # durulduğuna bağlıdır) ve rezidüel durumu etikette AÇIKÇA yazılır — birini
    # yazıp diğerini gizlemek ya bulguyu bastırır ya güveni şişirir.
    drift = c.get("cd_drift_son20pct")
    if (not salinimda and c.get("drift_ok") and drift is not None
            and drift <= QOI_DURAGAN_DRIFT_PCT):
        return {"seviye": "ok",
                "etiket": f"✅ QoI durağan (Cd drifti %{drift:.2f})",
                "gerekce": [f"residualControl tetiklenmedi ama Cd son %20 pencerede "
                            f"%{drift:.2f} sürükleniyor (sınır %{QOI_DURAGAN_DRIFT_PCT}) "
                            "ve salınım yok — hüküm QoI'ye dayanıyor, rezidüel "
                            "seviyesi onun vekilidir"]}
    gerekce = []
    eksik = [ad for ad, anahtar in (("kuvvet drifti", "drift_ok"), ("rezidüel", "rezidual_ok"))
             if not c.get(anahtar)]
    if eksik:
        gerekce.append(f"{', '.join(eksik)} hedefin dışında")
    if salinimda:
        gerekce.append(
            f"kuvvet SALINIYOR (genlik ±%{sal.get('genlik_pct', 0):.1f}, "
            f"{sal.get('gecis', 0)} işaret geçişi) — rezidüel ve drift ölçütleri sağlansa "
            "bile çözüm sabit noktaya oturmadı (limit çevrimi). Bildirilen katsayı "
            "salınımın ortalamasıdır; bu genlik gerçek bir belirsizlik bileşenidir ve "
            "GCI'ya GİRMEZ")
    # SALINIM: GENLİĞİ ÖLÇÜLMÜŞ ve BANDA KATILMIŞSA kabul edilebilir.
    # Bu "limit çevrimi yakınsadı" demek DEĞİLDİR — akış hâlâ zaman-bağımlıdır ve
    # onerilen sonraki cozum yolu URANS'tir ("kesin cozum" DEGIL: rejime gore
    # DES/LES gerekebilir ve bu platform muhafazakar dili tercih eder). Soylenen su: genlik %{SALINIM_KABUL_PCT}'nin altında VE
    # raporlanan sayısal belirsizliğe GERÇEKTEN girmişse, bildirilen "Cd ± band"
    # mühendislik açısından savunulabilir. Ölçüldü: genlikler %0.68-2.5 iken aynı
    # koşuların model-form belirsizliği %12 — salınım bandın beşte biri kadar.
    #
    # KAPI GEVŞEMİYOR: (a) genlik eşiği aşarsa düşer, (b) genlik banda GİRMEMİŞSE
    # düşer (bu doğrulanabilir bir koşuldur, iyi niyet beyanı değil), (c) etiket
    # "yakınsadı" DEMEZ — salınımı ve genliği açıkça yazar.
    if salinimda and c.get("drift_ok"):
        _g = sal.get("genlik_pct")
        _b = belirsizlik or {}
        _u_say = _b.get("u_sayisal_pct")
        _u_mod = _b.get("u_model_pct")
        _bandda = (_g is not None and _u_say is not None
                   and _u_say >= _g - 1e-9)          # genlik gercekten katilmis mi
        _kucuk = (_g is not None and _g <= SALINIM_KABUL_PCT
                  and (_u_mod is None or _g <= _u_mod / SALINIM_MODEL_ORANI))
        if _bandda and _kucuk:
            return {"seviye": "ok",
                    "etiket": f"✅ salınımlı ama genliği bantta (±%{_g:.1f})",
                    "gerekce": [
                        f"çözüm sabit noktaya oturmadı (limit çevrimi, ±%{_g:.1f}, "
                        f"{sal.get('gecis', 0)} işaret geçişi) — AMA genlik raporlanan "
                        f"sayısal belirsizliğe katıldı (%{_u_say:.2f}) ve model-form "
                        f"belirsizliğinin (%{_u_mod if _u_mod is not None else '?'}) "
                        "çok altında. Akış zaman-bağımlıdır; önerilen sonraki çözüm yolu "
                        "URANS'tır (rejime göre DES/LES de gerekebilir)"]}
    # ESKALASYON RECETESI EN SONDA: once sorun, sonra ne yapilacagi. Yalniz
    # REDDEDILEN salinimli kosuya verilir — yukaridaki dalda kosu KABUL ediliyor
    # ve orada recete gereksiz gurultu olur.
    if salinimda:
        gerekce += _urans_satirlari(sal, kosu)
    etiket = "⚠️ salınımlı (sabit nokta yok)" if salinimda else "⚠️ sınırda"
    return {"seviye": "uyari", "etiket": etiket, "gerekce": gerekce}


def _urans_satirlari(sal: dict, kosu: dict | None) -> list[str]:
    """Salınan koşu için URANS eskalasyon reçetesi (varsa)."""
    k = kosu or {}
    from urans_kapisi import recete_metni, urans_recetesi
    return recete_metni(urans_recetesi(
        sal, k.get("lref_m"), k.get("velocity"), k.get("rejim"),
        k.get("sure_s"), k.get("iterasyon")))


# Duvar-fonksiyonu log-bölgesi; dışındaysa sürtünme bileşeni çözülmüyor.
YPLUS_BANDI = (30.0, 300.0)
YPLUS_DUVAR_COZUNUR = 5.0
# Gecis modelleri DUVAR-COZUNUR ag ister. Ad listesi burada TEKRARLANMAZ,
# cozucu katmanindan alinir; iki yerde iki liste tutmak ayrisma demektir.
try:
    from analysis.openfoam_runner import GECIS_MODELLERI as GECIS_MODELLERI_ADLARI
# sessiz-yutma: kabul --- zarf katmani cozucu katmanindan BAGIMSIZ da
# kullanilabilmeli (testler, salt-veri tuketicileri). Ithal edilemezse
# bilinen tek gecis modeli adiyla devam edilir ve kapi YINE calisir.
except Exception:
    GECIS_MODELLERI_ADLARI = ("kOmegaSSTLM",)


def yplus_duvar_sinifi(ort: float | None, tepe: float | None = None) -> str | None:
    """y⁺ hangi duvar işlemine ait? Hiçbirine değilse None.

    ORTALAMA TEK BAŞINA YETMEZ: tepe y⁺ bandın dışına taşıyorsa duvarın bir
    bölümü hiçbir zaman log-bölgesinde değildir. Ölçüldü: Ahmed 25° ortalaması
    46 (bandın içinde) ama tepesi 1237 — o koşu duvar-fonksiyonunu temsil
    etmiyor.

    TEK KAYNAK: bu ölçüt `model_form_bandi._duvar_islemi` içinde bir kez daha
    yazılmıştı ve o dosyanın docstring'i "aynı ölçüt duvar_hukmu'nda da var"
    diyordu --- yani iki kaynak olduğu BİLİNİYORDU. İkisi ayrışırsa hangi
    koşunun savunulabilir sayıldığı çağıran modüle göre değişirdi.
    """
    if ort is None:
        return None
    if ort <= YPLUS_DUVAR_COZUNUR:
        return ("wall_resolved" if tepe is None or tepe <= YPLUS_BANDI[0]
                else None)
    if YPLUS_BANDI[0] <= ort <= YPLUS_BANDI[1]:
        return ("wall_function" if tepe is None or tepe <= YPLUS_BANDI[1]
                else None)
    return None          # bant dışı: o koşu zaten savunulabilir değil


def duvar_hukmu(sinir: dict | None, model: str | None = None) -> tuple[bool, str]:
    """Duvar çözünürlüğü savunulabilir mi? İki MEŞRU yol var, ikisi de kabul.

    MODEL FARK EDER. Duvar-fonksiyonu bandı (y⁺ 30–300) kOmegaSST için MEŞRU
    ama GEÇİŞ MODELİ (Langtry-Menter) için DEĞİLDİR: LM laminer bölgeyi ve
    geçiş noktasını sınır tabakanın İÇİNDE çözer, laminer altkatman
    ayrıklaştırılmazsa üretilen sayının fiziksel karşılığı yoktur.

    Ölçüldü (2026-08-19, küre çapası): 10 katman istendi, ortalama 0,535
    örüldü, y⁺ ortalaması 59 çıktı. Kapı modelden habersiz olduğu için bunu
    "duvar fonksiyonu bandında" diye GEÇİRİYORDU — oysa koşu kOmegaSSTLM ile
    yapılmıştı ve Cd 0,142 (referans 0,47) veriyordu. `gecis_modeli_onkosulu`
    zaten var ama o İSTEĞİ denetler; bu kapı GERÇEKLEŞENİ denetler.
    """
    s = sinir or {}
    _gecis = bool(model) and model in GECIS_MODELLERI_ADLARI
    yp = (s.get("yplus") or {})
    ort = yp.get("ort") if isinstance(yp, dict) else None
    kat = s.get("katman_olcumu") or {}
    if ort is None:
        return False, f"y+ ölçülemedi ({yp.get('neden') if isinstance(yp, dict) else 'yok'})"
    if kat.get("durum") == "COKTU":
        return False, (f"katman ÇÖKTÜ ({kat.get('istenen')} istendi, 0 örüldü) — "
                       f"duvar-çözünür iddiası geçersiz, y+={ort:.0f}")
    if kat.get("durum") == "ok" and ort <= YPLUS_DUVAR_COZUNUR:
        return True, f"duvar-çözünür: {kat['eklenen']} katman, y+={ort:.1f}"
    if _gecis:
        # GEÇİŞ MODELİ İÇİN DUVAR-FONKSİYONU BANDI MEŞRU DEĞİLDİR. Buraya
        # düşmek, y⁺'ın duvar-çözünür eşiğini aştığı anlamına gelir; LM o
        # ağda laminer altkatmanı hiç görmez ve ürettiği sayı fiziksel
        # değildir. kOmegaSST için aynı ağ meşru olurdu — hüküm MODELE bağlı.
        return False, (
            f"{model} DUVAR-ÇÖZÜNÜR ağ ister (y⁺≤{YPLUS_DUVAR_COZUNUR:g}) ama "
            f"ölçülen y⁺ ortalaması {ort:.1f}. Laminer altkatman "
            "ayrıklaştırılmadan geçiş modeli fiziksel olmayan bir sayı üretir; "
            "aynı ağ tam-türbülanslı model için meşru olurdu.")
    if YPLUS_BANDI[0] <= ort <= YPLUS_BANDI[1]:
        # ORTALAMA YETMEZ. Ozet istatistik dagilimi gizler: MiniHawk'ta
        # ort=129 (bandda) iken min=6.7 ve max=424 — ikisi de band DISI.
        # Yuzeyin yarisi y+=20, yarisi y+=240 olsa ortalama yine "iyi" gorunur
        # ama duvar modeli iki bolgede de tutarsiz calisir.
        #
        # UST ve ALT ASIM AYRI DEGERLENDIRILIR, cunku fizikleri farklidir:
        #   min < 30  DURMA NOKTASINDA KACINILMAZDIR (u_tau -> 0). Tek basina
        #             ret sebebi degildir; kaydedilir.
        #   max > 300 log-bolgesinin USTUNE cikildigini gosterir — orada duvar
        #             fonksiyonu gecerli degildir ve surtunme yanlis cozulur.
        _mx = yp.get("max")
        _mn = yp.get("min")
        _not = []
        if isinstance(_mn, (int, float)) and _mn < YPLUS_BANDI[0]:
            _not.append(f"min={_mn:.0f} bandin ALTINDA (durma noktasinda beklenir)")
        if isinstance(_mx, (int, float)) and _mx > YPLUS_BANDI[1]:
            return False, (
                f"y+ ORTALAMASI bandda ({ort:.0f}) ama max={_mx:.0f} "
                f"log-bolgesinin ustunde — yuzeyin bir kisminda duvar fonksiyonu "
                "gecersiz. Ortalama tek basina yeterli degildir. "
                "(NOT: bant-ici YUZEY ALANI ORANI olculmuyor; yPlus.dat yalniz "
                "min/max/ortalama veriyor.)")
        return True, (f"duvar fonksiyonu bandında: y+={ort:.0f}"
                      + (" [" + "; ".join(_not) + "]" if _not else ""))
    return False, (f"y+={ort:.0f} duvar-fonksiyonu bandının ({YPLUS_BANDI[0]:.0f}-"
                   f"{YPLUS_BANDI[1]:.0f}) dışında — sürtünme çözülmüyor")


def savunulabilir(s: dict) -> dict:
    """Bir koşu SONUCU (sonuc.json sözlüğü) savunulabilir mi — TEK TANIM.

    NEDEN BURADA: bu hüküm güvenilirlik taramasında yaşıyordu ve ÖĞRENME KATMANI
    ona hiç ulaşmıyordu. mesh_memory'nin başarı etiketi `status == "ok"` idi, yani
    "çözücü temiz çıktı" demekti — kapının hükmü değil.

    ÖLÇÜLDÜ (sabit ref_bump=0 taraması, 12 geometri): kapı 6 koşuyu savunulamaz
    saydı (gondol_dort y⁺=1222, su57 y⁺=3239, çiftkuyruk 426, kapsül 370 …) ama
    ONİKİSİNİN DE status'ü "ok" idi. Havuz bu etiketle hiçbir zaman ayırt edici
    olamazdı: kayıt sayısı artıyor, bilgi artmıyordu.

    Döner: {"savunulabilir": bool, "gerekce": [...], "kapi": str, "duvar": str}
    """
    ret = {"savunulabilir": False, "gerekce": []}
    if s.get("status") != "ok" or s.get("cd") is None:
        ret["gerekce"].append(f"koşu tamamlanmadı (status={s.get('status', '?')})")
        return ret
    _fr = next((a for a in (s.get("asama_sureleri") or [])
                if a.get("asama") == "foamRun"), {})
    kapi = sonuc_kapisi(s.get("fizik_kabul"), s.get("convergence"),
                        s.get("belirsizlik"),
                        kosu={"lref_m": (s.get("geometry") or {}).get("lmax_m"),
                              "velocity": s.get("velocity"),
                              "rejim": rejim_arac_tipinden(s.get("vehicle_type")),
                              "sure_s": _fr.get("sure_s"),
                              "iterasyon": _fr.get("iterasyon")})
    ret["kapi"] = kapi["etiket"]
    if kapi["seviye"] != "ok":
        ret["gerekce"].append(f"{kapi['etiket']}: {'; '.join(kapi['gerekce'])[:160]}")
    duvar_ok, duvar_not = duvar_hukmu(s.get("sinir_tabaka"))
    ret["duvar"] = duvar_not
    if not duvar_ok:
        ret["gerekce"].append(duvar_not)
    ret["savunulabilir"] = not ret["gerekce"]
    return ret


# Ağ yeterliliği için kabul edilen REFERANS AĞ AİLELERİ. Bu bir beyaz listedir ve
# depoda sürümlenir; çağıranın serbestçe True geçebileceği bir bayrak DEĞİLDİR.
# Neden: "bu vaka referans ağda koştu" beyanı doğrulanamıyorsa, ağ-yeterliliği
# kapısı bir kapı olmaktan çıkıp bir nezaket ricasına döner — kapının bütün değeri
# reddedebilmesinden gelir. Listeye ekleme, o ailenin depoda belgelenmiş ve
# yayımlanmış bir doğrulama kaydı olmasını gerektirir.
REFERANS_AG_AILELERI = frozenset({
    "nasa_tmr_naca0012",   # NASA Turbulence Modeling Resource, NACA0012 ailesi (§5.2)
})

# ARAÇ YOLUNDA BU BEYAN KULLANILMAZ ve bu bir eksiklik DEĞİLDİR. Listedeki tek
# aile 2B kanat profilidir; `app_analyzer` ise 3B araç STL'i sınıflandırır ve
# bir araç geometrisi o aileyi hiçbir zaman meşru olarak beyan edemez. Bu yüzden
# arayüze "referans ağ ailesi" kutusu EKLENMEDİ: kullanıcının yalnızca yanlış
# kullanabileceği bir kontrol olurdu. Araç geometrilerinde taşımanın design-grade
# olmasının tek yolu çok-ağlı asimptotik banddır (`has_gci_band`) ve uygulama
# onu zaten geçiriyor.
#
# Buraya bir ARAÇ referans ailesi eklenirse (ör. Ahmed gövdesi, DrivAer) o zaman
# çağıranların beyan edebilmesi gerekir; o gün gelene kadar beyan yolu bilerek
# yalnız kütüphane/doğrulama kodundadır.


def referans_ag_kabul(beyan) -> bool:
    """Referans-ağ beyanı GEÇERLİ mi? Yalnız beyaz listedeki aile adları sayılır.

    `True` gibi çıplak bir doğruluk-değeri KABUL EDİLMEZ: hangi ailenin
    kastedildiği yazılmadıkça beyan denetlenemez. Bilinmeyen ad da reddedilir;
    sessizce kabul etmek kapıyı işlevsizleştirirdi.
    """
    return isinstance(beyan, str) and beyan in REFERANS_AG_AILELERI


# CFD tarafinda REFERANS KABUL SINIRI. FEA'daki FEA_KABUL_SINIRI ile AYNI
# gerekcenin CFD'ye uygulanmis hali ve ayni sayiyi tasiyor (gerilme %10):
# mutlak kuvvet katsayisi da bir INTEGRAL turetilmis niceliktir, birincil
# bilinmeyenden bir mertebe kabadir.
#
# NEDEN GEREKLI (olculdu 2026-08-19, dis korpus): `classify_fea` referans
# hatasini KAPI olarak kullaniyordu ama `classify_cfd` C_D hukmunu YALNIZ
# banda bakarak veriyordu. GCI bandi olan bir kosu, referanstan ne kadar uzak
# olursa olsun DOGRULANMIS aliyordu (dogrudan sinandi: Cd=0,30 ve Cd=1,20
# ayni hukmu aldi). Ayni acik FEA tarafinda bilincli olarak kapatilmisti;
# CFD tarafinda ACIK kalmisti --- bu deponun "iki-hizli" dedigi ayrisma.
#
# YON: kapi yalnizca referans VERILDIGINDE calisir. Referanssiz cagrilar
# birebir eskisi gibi davranir, yani mevcut hicbir kosu yeniden siniflanmaz.
CD_REFERANS_KABUL_PCT = 10.0


def classify_cfd(vehicle_type: str, alpha_deg: float, mach: float,
                 has_gci_band: bool = False, band_pct: float | None = None,
                 Cl: float | None = None, Cd: float | None = None,
                 ag_yeterli: bool | None = None,
                 referans_hata_pct: float | None = None,
                 u_val_pct: float | None = None) -> list[Verdict]:
    """CFD aerodinamik çıktılarının zarf sınıfı. has_gci_band: 3-mesh asimptotik GCI var mı.

    İKİ KAPI, ÖLÇÜLMÜŞ İKİ KÖR NOKTAYI KAPATIR (n=44 doğrulayıcı korpus, 2026-08-13):

    1) FİZİKSEL AKLA-YATKINLIK (`Cl`, `Cd`). `force_admissibility` bu modülde ZATEN
       vardı ama `classify_cfd` onu HİÇ çağırmıyordu; kapı yalnızca app_analyzer'ın
       kendi yolunda uygulanıyordu. Sonuç ölçüldü: α=8° orta ağda çözücü ıraksayıp
       Cl=4769, Cd=293 döndürdü, tarama bunu HATASIZ kaydetti ve zarf DESIGN-GRADE
       sertifikası verdi. Bir kanat profilinde |Cl|>3 imkânsızdır; bu bir eşik
       AYARI değil, veriye bakılmadan söylenebilecek bir fizik sınırıdır.

    2) TAŞIMADA AĞ YETERLİLİĞİ (`ag_yeterli`). Zarf, taşıma güvenilirliğini YALNIZ
       hücum açısına bakarak kuruyordu: bağlı akıştaki her vaka, ağın o akışı
       çözüp çözmediğine BAKILMADAN design-grade alıyordu. Doğrulayıcı korpustaki
       yedi yanlış-negatifin ALTISI bu tek kusurdan geldi (hatalar %5,8, %10,7,
       %23,0 ve daha kötüsü). Kanıt yoksa kapı gevşemez, SIKILAŞIR: gösterilmemiş
       ağ yeterliliği DOĞRULANMIŞ değil EĞİLİM verir. Yön bilinçlidir — makalenin
       ilan ettiği maliyet asimetrisi (yanlış-negatif, yanlış-pozitiften pahalı)
       varsayılanı muhafazakâr olmaya zorlar.

    `ag_yeterli=None` "kanıt sunulmadı" demektir ve bu bir SESSİZ gevşeme değildir:
    hüküm metni kapının hangi nedenle sıkıldığını yazar.
    """
    a = abs(alpha_deg or 0.0)
    compressible = (mach or 0.0) >= MACH_INCOMP
    v: list[Verdict] = []
    # Ağ yeterliliği için kanıt: SÜRÜMLENMİŞ referans-ağ ailesi VEYA çok-ağlı
    # asimptotik band. `ag_yeterli` serbest bir bayrak DEĞİLDİR: aile adı
    # REFERANS_AG_AILELERI'nde olmalı, aksi halde beyan REDDEDİLİR (bkz. fonksiyon).
    ag_kanit = referans_ag_kabul(ag_yeterli) or bool(has_gci_band)

    # ── TAŞIMA (C_L) ──
    if a > ALPHA_VALID_DEG:
        _p = {"alpha": alpha_deg, "sinir": ALPHA_VALID_DEG}
        v.append(Verdict("C_L (taşıma)", OUT, False,
                         _mesaj("CL_ALPHA_ZARF_DISI", **_p), "CL_ALPHA_ZARF_DISI", _p))
    elif compressible:
        _p = {"mach": mach}
        v.append(Verdict("C_L (taşıma)", TREND, False,
                         _mesaj("CL_SIKISABILIR", **_p), "CL_SIKISABILIR", _p))
    elif not ag_kanit:
        _p = {"sinir": ALPHA_VALID_DEG}
        v.append(Verdict("C_L (taşıma)", TREND, False,
                         _mesaj("CL_AG_KANITI_YOK", **_p), "CL_AG_KANITI_YOK", _p))
    else:
        _p = {"sinir": ALPHA_VALID_DEG}
        v.append(Verdict("C_L (taşıma)", VALIDATED, True,
                         _mesaj("CL_GECERLI", **_p), "CL_GECERLI", _p))

    # ── SÜRÜKLEME (C_D, mutlak) ──
    if has_gci_band:
        v.append(Verdict("C_D (sürükleme)", VALIDATED, True,
                         _mesaj("CD_GCI_BANDI_VAR"), "CD_GCI_BANDI_VAR", {}))
    elif compressible:
        v.append(Verdict("C_D (sürükleme)", TREND, False,
                         _mesaj("CD_SIKISABILIR"), "CD_SIKISABILIR", {}))
    else:
        # ESKİ METİN BU KOŞUYU DEĞİL BAŞKA BİR ÇALIŞMAYI ANLATIYORDU: "bu O-grid
        # ailesinde mesh-yakınsamadı, p≈0.2" cümlesi kanat-profili O-grid
        # ailesinin ölçümüydü. Roket/araç STL'i için hem alakasız hem de yanlış
        # atıf; üstelik o aile TMR gridleriyle sonradan kapandı (GCI %1.7).
        # Doğru ifade bu koşu hakkında olan: ÇOK-AĞLI BAND HESAPLANMADI.
        extra = (f" Tek elde olan 2-ağ duyarlılığı: ±%{band_pct} — bu bir GCI bandı "
                 "DEĞİLDİR (gözlenen mertebe hesaplanamaz)." if band_pct is not None
                 else " Bu geometride hiç ağ-duyarlılığı ölçülmedi.")
        extra_en = (f" The only figure available is a two-grid sensitivity of ±{band_pct} %, "
                    "which is NOT a GCI band (the observed order cannot be computed)."
                    if band_pct is not None
                    else " No mesh sensitivity was measured for this geometry.")
        _p = {"ek": extra, "ek_en": extra_en}
        v.append(Verdict("C_D (sürükleme)", TREND, False,
                         _mesaj("CD_BAND_YOK", **_p), "CD_BAND_YOK", _p))

    # ── REFERANS KAPISI: band, DOĞRULUĞU garanti etmez ──
    # Yakınsamış bir çözüm "sayısal hatam küçük" der; referanstan uzaklığı
    # hakkında hiçbir şey söylemez. Bir referans BEYAN EDİLDİYSE ve sapma
    # kabul sınırını aşıyorsa, band ne olursa olsun tasarım-sınıfı verilemez.
    # Kapı yalnız referans verildiğinde çalışır: referanssız çağrılar birebir
    # eskisi gibi davranır.
    # SINIR SABİT DEĞİL, KANITA BAĞLI. İlk sürüm düz %10 kullanıyordu (FEA'dan
    # aynen alınmıştı) ve bu bir kategori hatası üretiyordu: geriye-basamak
    # koşusu %10,46 sapıyor ama o sapma, ölçülmüş `separated.wall_resolved`
    # model-form bandının (%12,0) İÇİNDE. Yani koşu kötü değil; model biasını
    # DOĞRU ölçmüş. Sabit eşik onu cezalandırıyordu.
    #
    # Doğrusu ASME V&V 20'nin kendi ölçütü: sapma, BEYAN EDİLEN u_val'i aşarsa
    # açıklanmamış bir tutarsızlık vardır (R_E>1). Aşmıyorsa gürültüden ayırt
    # edilemez ve hüküm düşürülmez. u_val verilmezse düz eşiğe düşülür --- o
    # da bir kanıt yokluğu hâli, ve muhafazakâr yön korunur.
    sinir = u_val_pct if u_val_pct is not None else CD_REFERANS_KABUL_PCT
    if referans_hata_pct is not None and referans_hata_pct > sinir:
        _p = {"hata": referans_hata_pct, "sinir": sinir}
        v = [x for x in v if not x.quantity.startswith("C_D")]
        v.append(Verdict("C_D (sürükleme)", TREND, False,
                         _mesaj("CD_REFERANS_HATASI", **_p), "CD_REFERANS_HATASI", _p))

    # ── L/D ve sürükleme kuvveti: mutlak Cd'ye bağlı → en zayıfı miras alır ──
    v.append(Verdict("L/D, sürükleme kuvveti/gücü", TREND, False,
                     _mesaj("LD_TUREV"), "LD_TUREV", {}))

    # ── FİZİK KAPISI EN SONDA VE EN ÜSTTE: fizik-dışı bir sayı hiçbir zarf
    # sınıfıyla kurtarılamaz, dolayısıyla yukarıdaki hükümlerin HEPSİNİ ezer.
    if Cl is not None or Cd is not None:
        v = apply_physics_gate(v, force_admissibility(
            Cd, Cl, alpha_deg, rejim=rejim_arac_tipinden(vehicle_type)))
    return v


# Kapali-form referansa karsi KABUL SINIRI. Nicelik sinifina gore, cunku
# turetilmis gerilme yer degistirme alaninin turevidir ve bir mertebe daha kabadir;
# yer degistirme ve ozdeger birincil FE bilinmeyenidir ve daha hizli yakinsar.
# AYNI ilke assay'in TAU_BY_Q'sunda da kullaniliyor -- iki yerde ayri sayi tutmak
# ikisinin ayrisması demek olurdu.
#
# NEDEN GEREKLI (dis hakem, 2026-08-13): onceki surumde referans hatasi yalniz
# RAPORLANIYOR, kapi gorevi GORMUYORDU. Mevcut alti benchmark %0,0-4,8 oldugu icin
# pratikte fark etmiyordu, ama mimari olarak %20 hatali yeni bir benchmark da
# design-grade alabilirdi. Kapi o acigi kapatir; mevcut alti vakanin hicbirini
# yeniden siniflandirmaz.
BURKULMA_MARJI = 1.5   # yapilandirilabilir gosterim marji, sertifikasyon faktoru DEGIL
FEA_KABUL_SINIRI = {"gerilme": 0.10, "yer_degistirme": 0.05, "ozdeger": 0.05}


# VLM'de STALL YOKTUR: çözücü bağlı-akış varsayar ve α büyüdükçe taşımayı
# lineer uzatır. Sınır CFD'ninkiyle AYNI tutuldu (ALPHA_VALID_DEG) çünkü ikisi de
# aynı fiziği --- akımın yüzeye bağlı kalmasını --- varsayıyor; iki ayrı sayı
# tutmak, aynı varsayımın iki yerde ayrışması demek olurdu.
#
# Panel bandı ÖLÇÜLDÜ (vlm_panel_yakinsamasi.json, gerçek araç mini_hawk):
# 6 seviye, LSR, asimptotik-altı → ±%28,32. Bu band bir kanıt DEĞİL, kanıt
# sunulmadığında ne kadar bilinmediğinin ölçüsüdür.
VLM_OLCULEN_BAND_PCT = 28.32

# e≤1 sınırı EXACT çözüm için geçerlidir; sayısal bir çözücü onu kendi hata
# payı kadar aşabilir. Tolerans veriye bakılarak SEÇİLMEDİ, çapadan alındı:
# `vlm_induklenen_capa` VSPAERO'nun Trefftz CDi'sini kapalı-form Prandtl
# taşıyıcı-çizgisiyle kıyasladı ve dikdörtgen kanatta +%7,2 sapma ölçtü. Yani
# bu çözücünün indüklenen direncinin exact cevaptan ne kadar uzakta durduğu
# BİLİNİYOR; kapı da o kadarını sayısal gürültü sayar, fazlasını ihlal.
#
# Ayrım ölçülmüş ve geniş: doğrulanmış temiz kanatta e≤1,005 (eşiğin altında),
# gerçek araçta e=1,096--1,276 (eşiğin üstünde, HER panel kademesinde).
# Sert e>1 eşiği çapanın kendi iyi vakasını yakıyordu.
VLM_SPAN_TOLERANSI = 0.072


def classify_vlm(alpha_deg: float, mach: float, *, Cl: float | None = None,
                 CDi: float | None = None, e_span: float | None = None,
                 panel_bandi_pct: float | None = None,
                 vehicle_type: str = "ucak") -> list[Verdict]:
    """VLM (VSPAERO) çıktılarının zarf sınıfı.

    CFD'den AYRI bir sınıflandırıcı olmasının nedeni kozmetik değil: VLM farklı
    bir denklem takımı çözer ve iki kusuru CFD'nin zarfında karşılığı olmayan
    türdendir.

    1) TOPLAM C_D YOKTUR. VLM viskoz terimi hiç hesaplamaz. Bu koşudan bir
       "Cd" döndürüp tüketicinin onu toplam sürükleme sanmasına izin vermek,
       bu deponun tekrar tekrar kapattığı kusurun ta kendisidir (sayı sınıfsız
       çıkar). Bu yüzden toplam C_D bir DEĞER değil, bir RET hükmü olarak döner.

    2) AÇIKLIK VERİMİ FİZİKSEL SINIRI AŞABİLİR. e = CL²/(π·AR·CDi) için eliptik
       yükleme üst sınırdır (e≤1). Ölçüldü: gerçek araçta e=1,20--1,28 çıkıyor ve
       ihlal 20--120 panel aralığının tamamında sürüyor. Yani indüklenen direnç
       fiziksel olarak mümkün olandan küçük; bu bir yakınsama sorunu değil.
       Kapı ölçümü hükme çevirir.
    """
    a = abs(alpha_deg or 0.0)
    compressible = (mach or 0.0) >= MACH_INCOMP
    band = panel_bandi_pct
    v: list[Verdict] = []

    # ── TAŞIMA (C_L) ──
    if a > ALPHA_VALID_DEG:
        _p = {"alpha": alpha_deg, "sinir": ALPHA_VALID_DEG}
        v.append(Verdict("C_L (taşıma)", OUT, False,
                         _mesaj("VLM_ALPHA_STALL_YOK", **_p), "VLM_ALPHA_STALL_YOK", _p))
    elif compressible:
        _p = {"mach": mach}
        v.append(Verdict("C_L (taşıma)", TREND, False,
                         _mesaj("VLM_SIKISABILIR", **_p), "VLM_SIKISABILIR", _p))
    elif band is None:
        _p = {"band": VLM_OLCULEN_BAND_PCT}
        v.append(Verdict("C_L (taşıma)", TREND, False,
                         _mesaj("VLM_PANEL_KANITI_YOK", **_p), "VLM_PANEL_KANITI_YOK", _p))
    else:
        _p = {"sinir": ALPHA_VALID_DEG, "band": band}
        v.append(Verdict("C_L (taşıma)", VALIDATED, True,
                         _mesaj("VLM_CL_BANDI_VAR", **_p), "VLM_CL_BANDI_VAR", _p))

    # ── İNDÜKLENEN SÜRÜKLEME (C_Di) ──
    # Fiziksel sınır ihlali her şeyi ezer: bandı ölçülmüş olması, imkânsız bir
    # sayıyı kullanılabilir yapmaz.
    if e_span is not None and e_span > 1.0 + VLM_SPAN_TOLERANSI:
        _p = {"e": e_span, "tol": VLM_SPAN_TOLERANSI * 100}
        v.append(Verdict("C_Di (indüklenen sürükleme)", OUT, False,
                         _mesaj("VLM_CDI_SPAN_IHLALI", **_p), "VLM_CDI_SPAN_IHLALI", _p))
    elif e_span is None:
        # KAPI BESLENMEDIYSE GEVSEMEZ. Ölçüldü (VLM yolunun ilk uçtan uca
        # koşusu): `e` hesaplanamadığı için None geliyordu ve CDi bu yüzden
        # DOĞRULANMIŞ alıyordu --- yani kurulan kapı sessizce devre dışıydı.
        # Sınanmamış bir fizik kontrolü, geçilmiş bir kontrol değildir.
        v.append(Verdict("C_Di (indüklenen sürükleme)", TREND, False,
                         _mesaj("VLM_SPAN_OLCULMEDI"), "VLM_SPAN_OLCULMEDI", {}))
    elif band is None:
        _p = {"band": VLM_OLCULEN_BAND_PCT}
        v.append(Verdict("C_Di (indüklenen sürükleme)", TREND, False,
                         _mesaj("VLM_PANEL_KANITI_YOK", **_p), "VLM_PANEL_KANITI_YOK", _p))
    elif compressible:
        _p = {"mach": mach}
        v.append(Verdict("C_Di (indüklenen sürükleme)", TREND, False,
                         _mesaj("VLM_SIKISABILIR", **_p), "VLM_SIKISABILIR", _p))
    else:
        _p = {"e": e_span if e_span is not None else float("nan"), "band": band}
        v.append(Verdict("C_Di (indüklenen sürükleme)", VALIDATED, True,
                         _mesaj("VLM_CDI_GECERLI", **_p), "VLM_CDI_GECERLI", _p))

    # ── TOPLAM C_D: bu yoldan ELDE EDİLEMEZ ──
    # Koşullu değil, KOŞULSUZ. Ne kadar ince panel kullanılırsa kullanılsın
    # potansiyel akış viskoz sürüklemeyi üretmez.
    v.append(Verdict("C_D (toplam sürükleme)", OUT, False,
                     _mesaj("VLM_CD_TOPLAM_YOK"), "VLM_CD_TOPLAM_YOK", {}))

    # ── L/D: toplam sürüklemeye bağlı → en zayıfı miras alır ──
    v.append(Verdict("L/D, sürükleme kuvveti/gücü", OUT, False,
                     _mesaj("LD_TUREV"), "LD_TUREV", {}))

    # Fizik kapısı CFD yolundaki ile AYNI: fizik-dışı bir Cl hiçbir zarfla
    # kurtarılamaz. Cd olarak indüklenen direnç verilir --- toplam olmadığı
    # zaten yukarıda hükme bağlandı.
    if Cl is not None or CDi is not None:
        v = apply_physics_gate(v, force_admissibility(
            CDi, Cl, alpha_deg, rejim=rejim_arac_tipinden(vehicle_type)))
    return v


def classify_fea(has_singularity: bool = False,
                 buckling_margin: float | None = None,
                 referans_hata_pct: float | None = None,
                 nicelik: str = "gerilme") -> list[Verdict]:
    """FEA yapısal çıktılarının zarf sınıfı (tasarım-güvenli kısım).

    buckling_margin: λ_kritik / yük (verilirse stabilite verdikti eklenir). λ>1 stabil.
    referans_hata_pct: kapalı-forma karşı |q−q_ref|/|q_ref| [%]. Verilirse KAPI olarak
        kullanılır; verilmezse eski davranış (yalnız raporlama) korunur.
    nicelik: FEA_KABUL_SINIRI anahtarı — gerilme / yer_degistirme / ozdeger.
    """
    sinir = FEA_KABUL_SINIRI.get(nicelik, FEA_KABUL_SINIRI["gerilme"]) * 100.0
    if referans_hata_pct is not None and referans_hata_pct > sinir:
        _p = {"hata": referans_hata_pct, "sinir": sinir, "nicelik": nicelik}
        return [Verdict("Kapalı-form referans hatası", TREND, False,
                        _mesaj("FEA_REFERANS_HATASI", **_p), "FEA_REFERANS_HATASI", _p)]
    v = [Verdict("Gerilme (temsili, %99-persentil)", VALIDATED, True,
                 _mesaj("FEA_GERILME_GECERLI"), "FEA_GERILME_GECERLI", {})]
    if has_singularity:
        v.append(Verdict("Tepe gerilme (tekillik noktası)", TREND, False,
                         _mesaj("FEA_TEKILLIK"), "FEA_TEKILLIK", {}))
    if buckling_margin is not None:
        # Lineer-elastik özdeğer burkulması Euler'e %0.2 doğrulandı (fea_validation_buckling).
        # İdeal-geometri üst-sınırdır: gerçek kusur/eksantriklik kritik yükü DÜŞÜRÜR → marj
        # 1'e yakınsa güvenli değil; muhafazakâr tasarım marjı ≥1.5 beklenir.
        # 1.5 bir SERTIFIKASYON faktoru degildir (FAR/CS turevli degil); bu aracin
        # yapilandirilabilir muhafazakar gosterim marjidir. Gerekcesi: lineer ozdeger
        # IDEAL geometri ust-sinirini verir, imalat kusuru/eksantriklik kritik yuku
        # DUSURUR, dolayisiyla 1'e yakin marj guvenli degildir.
        safe = buckling_margin >= BURKULMA_MARJI
        _p = {"marj": buckling_margin, "esik": BURKULMA_MARJI,
              "hukum": "sağlandı" if safe else "SAĞLANMADI — yalnız eğilim",
              "hukum_en": "met" if safe else "NOT met — trend-grade only"}
        v.append(Verdict("Burkulma marjı (lineer özdeğer)",
                         VALIDATED if safe else TREND, safe,
                         _mesaj("FEA_BURKULMA", **_p), "FEA_BURKULMA", _p))
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


# ── VLM (VSPAERO) kabul edilebilirliği ───────────────────────────────────────
# İndüklenen direnç negatif OLAMAZ; |Cl| bu mertebeyi aşarsa çözüm ıraksamıştır
# (ince kanatta stall öncesi Cl ~1.5'i geçmez).
CL_SACMA_ESIGI = 3.0


def vlm_kabul_edilebilir(nokta: dict) -> str | None:
    """Iraksamis VLM noktasi icin GEREKCE dondur; saglamsa None.

    NEDEN: VLM yolu iraksamis bir kosuyu HICBIR kontrolden gecirmeden kanit
    dosyasina yaziyordu. OLCULDU (insidans denemesi, 2026-08-05): Cl=3.8814,
    CDi=-5.184165, Cm=-147.28 degerleri vspaero_polar.json'a yazildi ve dosya
    "polar" olarak yayinlandi. Ayni kusur C-grid kosucusunda da bulunmustu
    (iraksak kosu icin status: ok yaziliyordu) — orada kapatilmis, VLM yolunda
    ACIK kalmisti.
    """
    cl, cdi = nokta.get("Cl"), nokta.get("Cd_i")
    if cl is None or cdi is None:
        return "Cl veya Cd_i sonuçta yok"
    # NaN/inf SESSIZCE GECIYORDU: `cdi < 0` ve `abs(cl) > 3` NaN icin False
    # doner, yani bozuk sayi "kabul edilebilir" sayilirdi. Karsilastirmaya
    # dayanan her kapinin ilk isi sayinin SONLU oldugunu dogrulamaktir.
    for ad, v in (("Cl", cl), ("Cd_i", cdi)):
        if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            return f"{ad}={v} SONLU BIR SAYI DEGIL (NaN/inf) — cozum iraksamis"
    if cdi < 0:
        return (f"NEGATIF INDUKLENEN DIRENC (CDi={cdi:g}) — fiziksel olarak "
                "imkansiz, cozum iraksamis")
    if abs(cl) > CL_SACMA_ESIGI:
        return (f"|Cl|={abs(cl):g} > {CL_SACMA_ESIGI} — ince kanatta stall "
                "oncesi bu mertebe gorulmez, cozum iraksamis")
    return None
