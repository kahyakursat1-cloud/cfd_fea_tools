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

from dataclasses import dataclass

VALIDATED = "VALIDATED"
TREND = "TREND"
OUT = "OUT"

ALPHA_VALID_DEG = 8.0   # |α|≤8° bağlı akış, doğrulanmış; üstü erken-stall (~%45 @10°)
MACH_INCOMP = 0.3

_TR = {VALIDATED: "DOĞRULANMIŞ", TREND: "YALNIZ-EĞİLİM", OUT: "ZARF-DIŞI"}
_ICON = {VALIDATED: "✅", TREND: "🟡", OUT: "🔴"}
_RANK = {VALIDATED: 0, TREND: 1, OUT: 2}


@dataclass
class Verdict:
    quantity: str
    klass: str
    design_safe: bool
    message: str


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
