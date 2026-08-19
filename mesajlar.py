"""Geçerlilik hükümlerinin ÇOK DİLLİ katalogu — kod kararlı, proza sunumdur.

NEDEN KOD: sonuç sözleşmesi bugüne kadar hükmü yalnız serbest Türkçe metinle
taşıyordu. Türkçe okumayan bir ortak (Erasmus+ KA220 konsorsiyumu) sınıfı
(`TREND`) ve `tasarimda_kullanilir` bayrağını okuyabiliyor ama NEDEN öyle
sınıflandığını okuyamıyordu --- oysa bu aracın tüm iddiası hükmün gerekçesiyle
birlikte yolculuk etmesidir.

Çeviri yaklaşımı bilinçli olarak DAR: depoda 160'tan fazla Türkçe kullanıcı
metni var ve hepsini çevirmek İKİ KAYNAK yaratır, ki bu depo o kusuru tekrar
tekrar ölçtü. Çevrilen şey sözleşme düzeyindeki KAPALI KÜME: geçerlilik
sınıfları ve onları üreten hükümler. Tanısal uyarılar (ağ, y⁺, yakınsama)
Türkçe kalır ve bu bir eksiklik olarak açıkça yazılır --- sessizce yarım
çevrilmiş bir arayüzden dürüst bir sınır iyidir.

KOD SÖZLEŞMENİN PARÇASIDIR: çeviri eksik olsa bile kod her zaman döner, yani
tüketici hükmü makine düzeyinde ayırt edebilir.
"""
from __future__ import annotations

DILLER = ("tr", "en")
VARSAYILAN_DIL = "tr"

# Geçerlilik sınıfı adları. Anahtarlar validity_envelope'daki sabitlerdir ve
# DEĞİŞMEZ; yalnız gösterim çevrilir.
# ANAHTAR = MAKİNE SABİTİ, görünen ad değil. İlk sürüm Türkçe görünen adla
# ("DOĞRULANMIŞ", "ZARF-DIŞI") anahtarlanmıştı ama zarf katmanı sabit yayıyor
# (VALIDATED / TREND / OUT). Üç sınıfın YALNIZ biri ("TREND") tesadüfen
# eşleşiyordu; diğer ikisi her iki dilde de çevrilmeden geçiyordu. `cevir`
# eksik anahtarda istisna atmayıp anahtarın kendisini döndürdüğü için kusur
# sessiz kaldı --- ölçüldü 2026-08-18, VLM yolunun ilk uçtan uca koşusunda
# `genel_metni` tr ve en'de birden "OUT" bastı. Sözleşme sabittir, sunum değişir.
SINIF = {
    "VALIDATED": {"tr": "DOĞRULANMIŞ", "en": "VALIDATED"},
    "TREND": {"tr": "YALNIZ-EĞİLİM", "en": "TREND-GRADE"},
    "OUT": {"tr": "ZARF-DIŞI", "en": "OUT-OF-ENVELOPE"},
}

# Nicelik adları.
NICELIK = {
    "C_L (taşıma)": {"tr": "C_L (taşıma)", "en": "C_L (lift)"},
    "C_D (sürükleme)": {"tr": "C_D (sürükleme)", "en": "C_D (drag)"},
    "L/D, sürükleme kuvveti/gücü": {
        "tr": "L/D, sürükleme kuvveti/gücü", "en": "L/D, drag force/power"},
    "Kapalı-form referans hatası": {
        "tr": "Kapalı-form referans hatası", "en": "Closed-form reference error"},
    "Gerilme (temsili, %99-persentil)": {
        "tr": "Gerilme (temsili, %99-persentil)",
        "en": "Stress (representative, 99th percentile)"},
    "Tepe gerilme (tekillik noktası)": {
        "tr": "Tepe gerilme (tekillik noktası)", "en": "Peak stress (singular point)"},
    "Burkulma marjı (lineer özdeğer)": {
        "tr": "Burkulma marjı (lineer özdeğer)",
        "en": "Buckling margin (linear eigenvalue)"},
    "C_Di (indüklenen sürükleme)": {
        "tr": "C_Di (indüklenen sürükleme)", "en": "C_Di (induced drag)"},
    "C_D (toplam sürükleme)": {
        "tr": "C_D (toplam sürükleme)", "en": "C_D (total drag)"},
}

# "Tasarımda kullanılır" hükmü — sözleşmenin en kısa ve en önemli alanı.
KULLANIM = {
    True: {"tr": "tasarım kararında kullanılabilir",
           "en": "usable in a design decision"},
    False: {"tr": "TASARIM KARARINDA KULLANILMAZ",
            "en": "NOT usable in a design decision"},
}

# ── HÜKÜM GEREKÇELERİ ────────────────────────────────────────────────────
# Türkçe şablonlar mevcut metnin BİREBİR aynısıdır: bu katalog bir yeniden
# yazım değil, tek-kaynağa toplamadır. Metin değişirse iki dilde birlikte
# değişir; testler Türkçe alt dizgilere bakmaya devam edebilir.
GEREKCE: dict[str, dict[str, str]] = {
    "CL_ALPHA_ZARF_DISI": {
        "tr": ("α={alpha:.0f}° > {sinir:.0f}°: 2D RANS taşımayı ~%45 DÜŞÜK tahmin "
               "eder (erken stall — α=10/12°'de ölçüldü). Tasarım sayısı DEĞİL; yalnız "
               "'bu açıda stall başlıyor' sezgisi için."),
        "en": ("α={alpha:.0f}° > {sinir:.0f}°: 2D RANS underpredicts lift by ~45 % "
               "(early stall, measured at α=10/12°). Not a design number; use only as "
               "an indication that stall begins near this angle."),
    },
    "CL_SIKISABILIR": {
        "tr": "Ma={mach:.2f}≥0.3 sıkışabilir rejim — taşıma yalnız eğilim düzeyinde.",
        "en": ("Ma={mach:.2f} ≥ 0.3, compressible regime: lift is trend-level only."),
    },
    "CL_AG_KANITI_YOK": {
        "tr": ("Bağlı akış (|α|≤{sinir:.0f}°) ama AĞ YETERLİLİĞİ GÖSTERİLMEDİ: "
               "bu ağın taşımayı çözdüğüne dair çok-ağlı band ya da referans-ağ ailesi "
               "beyanı yok. Hücum açısı tek başına taşıma güvenilirliğini kurmaz — "
               "ölçüldü: bağlı akışta ağ-kaynaklı %5,8–%23 taşıma hatası. Eğilim ve "
               "aynı ağla A/B karşılaştırması geçerlidir."),
        "en": ("Attached flow (|α| ≤ {sinir:.0f}°) but MESH ADEQUACY NOT DEMONSTRATED: "
               "no multi-grid band and no reference-grid family declared for this run. "
               "Angle of attack alone does not establish lift reliability — measured: "
               "5.8–23 % mesh-induced lift error in attached flow. Trends and A/B "
               "comparisons at identical mesh settings remain valid."),
    },
    "CL_GECERLI": {
        "tr": ("Bağlı akış (|α|≤{sinir:.0f}°) + ağ yeterliliği gösterildi: "
               "NACA0012'de NASA Ladson'a karşı ≤%8 — tasarım kararı için kullanılabilir."),
        "en": ("Attached flow (|α| ≤ {sinir:.0f}°) with demonstrated mesh adequacy: "
               "≤8 % against NASA Ladson on NACA0012 — usable in a design decision."),
    },
    "CD_GCI_BANDI_VAR": {
        "tr": "3-mesh GCI asimptotik bandı — mutlak değer savunulabilir.",
        "en": ("Three-grid GCI within the asymptotic range — the absolute value is "
               "defensible."),
    },
    "CD_SIKISABILIR": {
        "tr": ("Süpersonik inviscid kayma-duvar taban-drag'ı ~%15 fazla — mutlak Cd tasarım "
               "sayısı DEĞİL; Mach-eğilimi ve A/B karşılaştırması güvenilir."),
        "en": ("Supersonic inviscid slip-wall base drag is ~15 % high: absolute Cd is not "
               "a design number; the Mach trend and A/B comparisons are reliable."),
    },
    "CD_BAND_YOK": {
        "tr": ("Bu koşu için çok-ağlı yakınsama bandı (GCI/LSR) hesaplanmadı, dolayısıyla "
               "mutlak sürüklemenin sayısal belirsizliği BİLİNMİYOR.{ek}"
               " Tasarım sayısı DEĞİL; aynı ağ ayarıyla yapılan A/B karşılaştırması ve "
               "eğilim geçerlidir."),
        "en": ("No multi-grid convergence band (GCI/LSR) was computed for this run, so the "
               "numerical uncertainty of the absolute drag is UNKNOWN.{ek_en}"
               " Not a design number; A/B comparisons at identical mesh settings and "
               "trends remain valid."),
    },
    "LD_TUREV": {
        "tr": ("Mutlak sürüklemeden türetilir → tasarım sayısı değil; "
               "karşılaştırmalı kullanın."),
        "en": ("Derived from the absolute drag, therefore not a design number; use "
               "comparatively."),
    },
    "FIZIK_KAPISI": {
        "tr": "FİZİK KAPISI: {gerekce}",
        "en": "PHYSICS GATE: {gerekce}",
    },
    "FIZIK_KAPISI_SUPHELI": {
        "tr": "FİZİK KAPISI (şüpheli): {gerekce}",
        "en": "PHYSICS GATE (suspect): {gerekce}",
    },
    "FEA_REFERANS_HATASI": {
        "tr": ("%{hata:.1f} > kabul sınırı %{sinir:.0f} ({nicelik}): "
               "uygulama-doğrulaması bu vakada GEÇMEDİ, sonuç yalnız eğilim."),
        "en": ("{hata:.1f} % > acceptance limit {sinir:.0f} % ({nicelik}): "
               "implementation verification FAILED for this case; trend-grade only."),
    },
    "FEA_GERILME_GECERLI": {
        "tr": ("6 kanonik V&V %0.0–4.8 (kuvvet/basınç/gövde/termal/buckling) — temsili gerilme "
               "ve emniyet faktörü tasarım kararı için kullanılabilir."),
        "en": ("Six canonical V&V cases at 0.0–4.8 % (force/pressure/self-weight/thermal/"
               "buckling): representative stress and safety factor are usable in a design "
               "decision."),
    },
    "FEA_TEKILLIK": {
        "tr": ("Sivri-köşe tekilliği: tepe değer mesh inceldikçe büyür, fiziksel değil — "
               "temsili (%99-persentil) değeri kullanın."),
        "en": ("Sharp-corner singularity: the peak value grows without bound under mesh "
               "refinement and is not physical; use the representative (99th percentile) "
               "value."),
    },
    "FEA_BURKULMA": {
        "tr": ("λ={marj:.2f}× — *BUCKLE yolu Euler'e %0.2 doğrulandı. "
               "İdeal-geometri ÜST-SINIRıdır; imalat kusuru/eksantriklik kritik yükü düşürür, "
               "bu yüzden marj ≥{esik} beklenir ({hukum})."),
        "en": ("λ={marj:.2f}× — the *BUCKLE path was verified to 0.2 % against Euler. "
               "This is an IDEAL-GEOMETRY UPPER BOUND; manufacturing defects and "
               "eccentricity reduce the critical load, so a margin ≥{esik} is expected "
               "({hukum_en})."),
    },

    "CD_REFERANS_HATASI": {
        "tr": ("Yerleşik referanstan sapma %{hata:.2f} > %{sinir:.2f}: yakınsamış "
               "bir çözüm 'sayısal hatam küçük' der, DOĞRU olduğunu söylemez. "
               "Ağ bandı ne kadar dar olursa olsun bu sapmayla tasarım sınıfı "
               "verilemez; sonuç eğilim düzeyindedir. (Aynı kapı FEA tarafında "
               "kapalı-form referansı için zaten uygulanıyordu.)"),
        "en": ("Deviation from the established reference is {hata:.2f} % > "
               "{sinir:.2f} %: a converged solution says 'my numerical error is "
               "small', not that it is correct. However tight the mesh band, this "
               "deviation cannot earn design grade; the result is trend-level. "
               "(The same gate was already applied on the FEA side for "
               "closed-form references.)"),
    },

    # ── VLM (VSPAERO) ────────────────────────────────────────────────────
    # Hızlı çözücü CFD'nin yerine geçmez ve bu, hükümde yazılı olmak zorunda:
    # VLM potansiyel akış çözer, viskoz terimi HİÇ hesaplamaz.
    "VLM_CD_TOPLAM_YOK": {
        "tr": ("VLM potansiyel akış çözücüsüdür ve viskoz sürüklemeyi (yüzey "
               "sürtünmesi + ayrılma) HİÇ hesaplamaz. Bu koşunun ürettiği tek "
               "sürükleme bileşeni indüklenen dirençtir; TOPLAM C_D bu yoldan "
               "ELDE EDİLEMEZ. Toplam sürükleme gerekiyorsa CFD yolu kullanılır."),
        "en": ("VLM is a potential-flow solver and does not compute viscous drag "
               "(skin friction + separation) at all. The only drag component this "
               "run yields is induced drag; TOTAL C_D CANNOT be obtained this way. "
               "Use the CFD path when total drag is required."),
    },
    "VLM_CDI_SPAN_IHLALI": {
        "tr": ("Açıklık verimi e={e:.2f}, fiziksel sınırı çözücünün kendi hata "
               "payından (%{tol:.1f}) fazla aşıyor. Eliptik yükleme matematiksel "
               "ÜST SINIRDIR; e>1 indüklenen direncin FİZİKSEL OLARAK MÜMKÜN "
               "OLANDAN küçük çıktığı anlamına gelir. Tolerans keyfî değil ölçülmüş: "
               "çapada VSPAERO'nun Trefftz C_Di'si kapalı-form taşıyıcı-çizgiden "
               "%7,2 sapıyor. İhlal 20--120 panel aralığının TAMAMINDA sürüyor, "
               "yani ayrıklaştırma artefaktı değil sistematiktir."),
        "en": ("Span efficiency e={e:.2f} exceeds the physical bound by more than the "
               "solver's own error margin ({tol:.1f} %). Elliptic loading is the "
               "mathematical UPPER BOUND, so e>1 means the induced drag came out "
               "smaller than physically possible. The tolerance is measured, not "
               "chosen: in the anchor case VSPAERO's Trefftz C_Di deviates 7.2 % from "
               "closed-form lifting-line. The violation persists across the whole "
               "20--120 panel range, so it is systematic rather than a discretisation "
               "artefact."),
    },
    "VLM_SPAN_OLCULMEDI": {
        "tr": ("Açıklık verimi e HESAPLANAMADI (kanat açıklığı/alanı okunamadı), "
               "dolayısıyla indüklenen direncin fiziksel sınırı SINANMADI. "
               "Sınanmamış bir kontrol geçilmiş sayılmaz: sayı eğilim düzeyindedir."),
        "en": ("Span efficiency e could NOT be computed (wing span/area unavailable), "
               "so the physical bound on induced drag was NOT tested. An untested "
               "check does not count as a passed one: the number is trend-level."),
    },
    "VLM_CDI_GECERLI": {
        "tr": ("Açıklık verimi e={e:.2f} fiziksel sınırla tutarlı ve panel bandı "
               "ölçülmüş (±%{band}). İndüklenen direnç bu bandla tasarım kararında "
               "kullanılabilir; TOPLAM sürükleme değildir."),
        "en": ("Span efficiency e={e:.2f} is consistent with the physical bound and a "
               "panel band was measured (±{band} %). Induced drag is usable in a design "
               "decision within that band; it is not total drag."),
    },
    "VLM_PANEL_KANITI_YOK": {
        "tr": ("Panel yakınsaması GÖSTERİLMEDİ: bu geometride VLM çözümünün panel "
               "sayısından bağımsız olduğuna dair ölçüm yok. Ölçülen referans vakada "
               "band ±%{band} çıkmıştı ve dizi son kademede hâlâ %1,22 değişiyordu; "
               "kanıtsız bir koşuya o bandı taşımak olmayan bir kesinlik yayınlamaktır."),
        "en": ("Panel convergence was NOT demonstrated: there is no measurement showing "
               "this geometry's VLM solution is panel-independent. In the measured "
               "reference case the band was ±{band} % and the series still moved 1.22 % "
               "at the finest step; carrying that band to an unproven run would publish "
               "a precision that does not exist."),
    },
    "VLM_CL_BANDI_VAR": {
        "tr": ("Bağlı akış (|α|≤{sinir:.0f}°) ve panel bandı ölçülmüş (±%{band}). "
               "Taşıma bu bandla tasarım kararında kullanılabilir."),
        "en": ("Attached flow (|α| ≤ {sinir:.0f}°) with a measured panel band "
               "(±{band} %). Lift is usable in a design decision within that band."),
    },
    "VLM_ALPHA_STALL_YOK": {
        "tr": ("α={alpha:.0f}° > {sinir:.0f}°: VLM'de STALL YOKTUR — çözücü taşımayı "
               "lineer olarak uzatmaya devam eder ve gerçek stall'ı göremez. Bu açıda "
               "üretilen taşıma bir eğilim bile değildir, bir uzatmadır."),
        "en": ("α={alpha:.0f}° > {sinir:.0f}°: VLM HAS NO STALL — the solver keeps "
               "extending lift linearly and cannot see the real stall. Lift produced at "
               "this angle is not even a trend; it is an extrapolation."),
    },
    "VLM_SIKISABILIR": {
        "tr": ("Ma={mach:.2f}≥0.3: VSPAERO Prandtl--Glauert düzeltmesi uygular ama "
               "bu düzeltme bu depoda hiçbir referansa karşı ölçülmedi — yalnız eğilim."),
        "en": ("Ma={mach:.2f} ≥ 0.3: VSPAERO applies a Prandtl--Glauert correction, but "
               "that correction has not been measured against any reference in this "
               "repository, so the result is trend-level only."),
    },
}


def dil_dogrula(dil: str | None) -> str:
    """Bilinmeyen dil SESSİZCE Türkçeye düşmez; çağıran ne aldığını bilir."""
    d = (dil or VARSAYILAN_DIL).lower()
    return d if d in DILLER else VARSAYILAN_DIL


def cevir(sozluk: dict, anahtar, dil: str) -> str:
    """Katalogdan çeviri; anahtar yoksa anahtarın KENDİSİ döner.

    Eksik çeviri bir istisna atmaz ve boş dize de döndürmez: ikisi de bilgiyi
    yok eder. Anahtarın kendisi dönerse tüketici en azından makine düzeyinde
    ne olduğunu görür.
    """
    e = sozluk.get(anahtar)
    return e.get(dil, e.get(VARSAYILAN_DIL, str(anahtar))) if e else str(anahtar)


def gerekce_metni(kod: str, dil: str, **p) -> str:
    """Kodu verilen dilde metne çevir. Kod katalogda yoksa kodun kendisi döner."""
    kalip = GEREKCE.get(kod, {}).get(dil_dogrula(dil))
    if not kalip:
        return kod
    try:
        return kalip.format(**p)
    except KeyError as e:
        # Eksik parametre SESSİZ kalmasın: yarım cümle yerine kod + eksik alan.
        return f"{kod} (çeviri parametresi eksik: {e})"
