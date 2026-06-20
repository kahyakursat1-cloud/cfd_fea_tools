"""
V&V Rapor Ureteci — ASME V&V 20 formati
========================================
Mesh bagimsizlik (GCI), validation hata barlari, V-n diyagrami, polar,
FEA emniyet faktoru ve CFD->FEA coupling korunumunu tek raporda toplar.
300 DPI figurler (MDPI/IEEE kalitesi).
"""

import json
import math
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300,
    "font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
    "axes.linewidth": 0.8,
})

# Arastirma-sinifi kabul esikleri — rapor verdiktleri girdi JSON'undaki
# pass bayraklarindan DEGIL, bu esiklerden yeniden hesaplanir.
TOL_CD_PCT = 15.0    # NACA0012 Cd validation (RANS, bagli akis)
TOL_CL_PCT = 5.0     # NACA0012 Cl validation
TOL_CL_ABS = 0.01    # |Cl_ref| ~ 0 durumunda mutlak kriter (yuzde anlamsiz)
TOL_FEA_PCT = 5.0    # analitik kiris sehimi
TOL_FEA_SUITE_PCT = 8.0   # kanonik FEA V&V suite (en kotu ~%4.8 ozagirlik kok-konsantrasyonu)
GCI_PASS_PCT = 5.0
P_RANGE = (0.5, 3.0)  # gozlemlenen mertebe makul araligi (teorik ~2)


# ─────────────────────────────────────────────────────────────────────────────
# GCI — Richardson Extrapolation (ASME V&V 20)
# ─────────────────────────────────────────────────────────────────────────────

def compute_gci(h_coarse, h_med, h_fine, f_coarse, f_med, f_fine, Fs=1.25):
    """3 kademeli mesh icin Grid Convergence Index.
    Donduru: p (gozlemlenen mertebe), f_exact (Richardson), gci_fine (%).
    """
    r21 = h_med / h_fine
    r32 = h_coarse / h_med
    e21 = f_fine - f_med
    e32 = f_med - f_coarse
    if abs(e21) < 1e-15 or abs(e32) < 1e-15:
        return None
    monotonic = (e32 / e21) > 0
    # Sabit r icin: p = ln|e32/e21| / ln(r)
    p = math.log(abs(e32 / e21)) / math.log(r21)
    f_exact = f_fine + e21 / (r21 ** p - 1)
    gci_fine = Fs * abs(e21 / f_fine) / (r21 ** p - 1) * 100
    gci_med = Fs * abs(e32 / f_med) / (r32 ** p - 1) * 100
    return {
        "p": round(p, 3), "f_exact": round(f_exact, 6),
        "gci_fine_pct": round(gci_fine, 4), "gci_med_pct": round(gci_med, 4),
        "asymptotic": round((r21 ** p) * gci_fine / gci_med, 4) if gci_med else None,
        "monotonic": monotonic,
        "p_in_range": P_RANGE[0] <= p <= P_RANGE[1],
    }


def _fea_val_error_pct(d):
    """fea_validation*.json şemalarından en kötü 'hata_pct'yi çıkar (şema-bağımsız:
    sehim/gerilme/analitik/fem altında farklı yerlerde durur). Recursive tarama."""
    worst = None
    stack = [d]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if k.endswith("hata_pct") and isinstance(v, (int, float)):
                    worst = v if worst is None else max(worst, v)
                else:
                    stack.append(v)
        elif isinstance(o, list):
            stack.extend(o)
    return worst


def gci_verdict(gci):
    """ASME V&V 20 uyumlu durust verdikt: GCI esigi tek basina yetmez —
    monotonluk, gozlemlenen mertebenin makullugu ve asimptotik oran da gerekir."""
    problems = []
    if not gci.get("monotonic"):
        problems.append("yakinsamamis/salinimli dizi")
    if not gci.get("p_in_range"):
        problems.append(f"p={gci['p']} makul aralik {P_RANGE} disi — asimptotik aralikta degil")
    asy = gci.get("asymptotic")
    if asy is not None and not (0.5 <= asy <= 2.0):
        problems.append(f"asimptotik oran {asy} (≈1 beklenir)")
    if gci["gci_fine_pct"] >= GCI_PASS_PCT:
        problems.append(f"GCI={gci['gci_fine_pct']}% ≥ {GCI_PASS_PCT}%")
    if not problems:
        return f"✅ Yakınsadı (GCI<{GCI_PASS_PCT}%, monoton, p makul, asimptotik oran≈1)"
    return "⚠️ Mesh bağımsızlığı GÖSTERİLEMEDİ: " + "; ".join(problems)


# ─────────────────────────────────────────────────────────────────────────────
# FIGURLER
# ─────────────────────────────────────────────────────────────────────────────

def fig_mesh_convergence(meshes, out_path):
    """Cd-h mesh yakinsama grafigi + Richardson asimptotu."""
    h = np.array([m["h"] for m in meshes])
    cd = np.array([m["Cd"] for m in meshes])
    order = np.argsort(h)
    h, cd = h[order], cd[order]

    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    ax.plot(h, cd, "o-", color="#1f4e79", mfc="white", ms=6, lw=1.3)
    gci = compute_gci(h[-1], h[1] if len(h) > 2 else h[-1], h[0],
                      cd[-1], cd[1] if len(cd) > 2 else cd[-1], cd[0])
    if gci:
        ax.axhline(gci["f_exact"], ls="--", color="#c00000", lw=1,
                   label=f"Richardson: Cd={gci['f_exact']:.4f}")
        ax.legend(fontsize=8)
    ax.set_xlabel("Mesh boyutu h (m)")
    ax.set_ylabel("Sürükleme katsayısı $C_d$")
    ax.set_title("Mesh Bağımsızlık Analizi", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return gci


def fig_airfoil_gci(levels, refs, out_path):
    """2D airfoil GCI: Cd-h (h=1/sqrt(N)) + Richardson + referans bandi.
    Sadece status=ok seviyeleri cizilir; en ince 3 gecerli seviyeden GCI."""
    ok = [lv for lv in levels if lv.get("status") == "ok" and lv.get("Cd") is not None]
    if len(ok) < 2:
        return None
    ok.sort(key=lambda lv: lv["cells"])
    h = np.array([1.0 / math.sqrt(lv["cells"]) for lv in ok])
    cd = np.array([lv["Cd"] for lv in ok])

    gci = None
    if len(ok) >= 3:
        f3, f2, f1 = ok[-3], ok[-2], ok[-1]   # coarse->fine (en ince 3)
        gci = compute_gci(1/math.sqrt(f3["cells"]), 1/math.sqrt(f2["cells"]),
                          1/math.sqrt(f1["cells"]), f3["Cd"], f2["Cd"], f1["Cd"])

    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    ax.plot(h, cd, "o-", color="#1f4e79", mfc="white", ms=6, lw=1.3, label="kOmegaSSTLM")
    if gci and gci.get("monotonic") and gci.get("p_in_range"):
        ax.axhline(gci["f_exact"], ls="--", color="#c00000", lw=1,
                   label=f"Richardson: Cd={gci['f_exact']:.5f}")
    for name, val, c in (("ref (serbest geçiş)", refs.get("Cd_free"), "#2e7d32"),
                         ("ref (türbülanslı)", refs.get("Cd_turb"), "#7b1fa2")):
        if val:
            ax.axhline(val, ls=":", color=c, lw=1, label=f"{name}={val}")
    ax.set_xlabel("h = N$^{-1/2}$")
    ax.set_ylabel("$C_d$")
    ax.set_title("2D NACA0012 GCI (O-grid, geçiş modeli)", fontsize=10)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return gci


def fig_transition_polar(tr, out_path):
    """2D NACA0012 gecis-modeli polar: Cl-a ve Cd-a, serbest-gecis referanslariyla."""
    rows = [(int(k), v) for k, v in tr.items()
            if k.isdigit() and isinstance(v, dict) and v.get("Cd") is not None]
    if len(rows) < 2:
        return None
    rows.sort()
    a = [r[0] for r in rows]
    cl = [r[1]["Cl"] for r in rows]
    cd = [r[1]["Cd"] for r in rows]
    clr = [r[1].get("Cl_ref") for r in rows]
    cdr = [r[1].get("Cd_ref_free") for r in rows]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7, 3))
    ax1.plot(a, cl, "o-", color="#1f4e79", mfc="white", ms=6, lw=1.3, label="kOmegaSSTLM")
    if all(v is not None for v in clr):
        ax1.plot(a, clr, "s--", color="#2e7d32", ms=5, lw=1, label="Ladson (serbest geçiş)")
    ax1.set_xlabel("α (°)")
    ax1.set_ylabel("$C_l$")
    ax1.legend(fontsize=7)
    ax2.plot(a, cd, "o-", color="#1f4e79", mfc="white", ms=6, lw=1.3)
    if all(v is not None for v in cdr):
        ax2.plot(a, cdr, "s--", color="#2e7d32", ms=5, lw=1)
    ax2.set_xlabel("α (°)")
    ax2.set_ylabel("$C_d$")
    fig.suptitle("2D NACA0012 Geçiş-Modeli Polar (260×130 O-grid)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return True


def fig_vn_diagram(envelope_summary, out_path):
    """V-n manevra + gust zarfi."""
    man = envelope_summary["speeds_ms"]
    gust = envelope_summary["gust"]["lines"]

    up = np.array(man["upper_curve"])
    lo = np.array(man["lower_curve"])

    fig, ax = plt.subplots(figsize=(5, 3.5))
    ax.plot(up[:, 0], up[:, 1], "-", color="#1f4e79", lw=1.5, label="Manevra zarfı")
    ax.plot(lo[:, 0], lo[:, 1], "-", color="#1f4e79", lw=1.5)
    ax.axhline(0, color="k", lw=0.5)

    # Gust hatlari
    for key, gc in gust.items():
        V = gc["V"]
        ax.plot([0, V], [1, gc["n_up"]], "--", color="#c00000", lw=0.9)
        ax.plot([0, V], [1, gc["n_down"]], "--", color="#c00000", lw=0.9)
        ax.plot(V, gc["n_up"], "rs", ms=4)

    # Hiz isaretleri
    for sp, lbl in [("Va", "Va"), ("Vc", "Vc"), ("Vd", "Vd")]:
        ax.axvline(man[sp], color="gray", ls=":", lw=0.7)
        ax.text(man[sp], ax.get_ylim()[1]*0.95, lbl, fontsize=7, ha="center")

    ax.set_xlabel("Eşdeğer hava hızı V (m/s)")
    ax.set_ylabel("Yük faktörü n")
    ax.set_title("V-n Uçuş Zarfı (FAR/CS-23)", fontsize=10)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def fig_polar(polar, out_path):
    """CL-alpha egrisi + suruklenme polari (stall yakalanir)."""
    ok = [r for r in polar if r.get("Cl") is not None]
    if len(ok) < 2:
        return None
    ok.sort(key=lambda r: r["alpha"])
    a = [r["alpha"] for r in ok]
    cl = [r["Cl"] for r in ok]
    cd = [r["Cd"] for r in ok]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7, 3))
    ax1.plot(a, cl, "o-", color="#1f4e79", mfc="white", ms=5, lw=1.3)
    # CFD'nin GÖRÜNÜR Cl tepesi — bu CLmax DEĞİL (steady-RANS stall'da ~%45 düşük;
    # gerçek CLmax yalnız deneysel referanstan, bkz. validity_envelope.analyze_polar_envelope).
    peak_i = int(np.argmax(cl))
    ax1.plot(a[peak_i], cl[peak_i], "rs", ms=7,
             label=f"Görünür tepe $C_L$={cl[peak_i]:.2f} @ {a[peak_i]}° (≠$CL_{{max}}$)")
    ax1.set_xlabel("Hücum açısı α (°)")
    ax1.set_ylabel("$C_L$")
    ax1.set_title("Kaldırma Eğrisi (RANS görünür tepe — CLmax değil)", fontsize=9)
    ax1.legend(fontsize=7)

    ax2.plot(cd, cl, "o-", color="#2e7d32", mfc="white", ms=5, lw=1.3)
    ax2.set_xlabel("$C_D$")
    ax2.set_ylabel("$C_L$")
    ax2.set_title("Sürüklenme Poları", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return {"cfd_peak_cl": cl[peak_i], "alpha_peak": a[peak_i]}


def _cl_pass(r):
    """|Cl_ref|~0 ise yuzde hata anlamsiz — mutlak kriter kullan."""
    if abs(r.get("Cl_ref", 0)) < 0.05:
        return abs(r.get("Cl_sim", 1e9) - r.get("Cl_ref", 0)) <= TOL_CL_ABS
    return r.get("Cl_err_pct", 1e9) <= TOL_CL_PCT


def fig_validation_bars(val_results, out_path):
    """Validation hata barlari (deney vs simulasyon)."""
    labels, errs, tols = [], [], []
    for key, r in val_results.items():
        if key.startswith("cfd_") and "Cd_err_pct" in r:
            labels.append(f"NACA0012\nα={r.get('alpha')}° Cd")
            errs.append(r["Cd_err_pct"])
            tols.append(TOL_CD_PCT)
        if key.startswith("cfd_") and "Cl_err_pct" in r and abs(r.get("Cl_ref", 0)) >= 0.05:
            labels.append(f"NACA0012\nα={r.get('alpha')}° Cl")
            errs.append(r["Cl_err_pct"])
            tols.append(TOL_CL_PCT)
        if key == "fea_cantilever" and "deflection_err_pct" in r:
            labels.append("Kiriş\nδ")
            errs.append(r["deflection_err_pct"])
            tols.append(TOL_FEA_PCT)

    if not labels:
        return
    fig, ax = plt.subplots(figsize=(4.5, 3))
    x = np.arange(len(labels))
    colors = ["#2e7d32" if e < t else "#c00000" for e, t in zip(errs, tols)]
    ax.bar(x, errs, color=colors, width=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Hata (%)")
    ax.set_title("Validation: |Sim − Referans| / Referans", fontsize=10)
    for i, (e, t) in enumerate(zip(errs, tols)):
        ax.text(i, e + 0.5, f"{e:.1f}%", ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# RAPOR
# ─────────────────────────────────────────────────────────────────────────────

class VVReport:
    def __init__(self, out_dir="./report"):
        self.out = Path(out_dir)
        self.out.mkdir(exist_ok=True)
        (self.out / "figures").mkdir(exist_ok=True)
        self.sections = []

    def build(self, mesh_indep=None, validation=None, envelope=None,
              fea=None, coupling=None, mesh_quality=None, polar=None,
              vspaero=None, rocket=None, rocket_fin=None, rocket_cfd=None,
              airfoil_gci=None, transition=None, fea_validations=None,
              fea_stress_gci=None, project="MiniHawk İHA"):
        md = ["# CFD/FEA Doğrulama ve Validation Raporu",
              f"\n**Proje:** {project}  ",
              f"**Tarih:** {datetime.now():%Y-%m-%d %H:%M}  ",
              "**Standart:** ASME V&V 20-2009, FAR/CS-23  ",
              "\n---\n"]

        # 0. Mesh kalitesi / y+ (prism layer)
        if mesh_quality:
            mq = mesh_quality
            md.append("## 0. Mesh Kalitesi ve Sınır Tabaka Çözünürlüğü\n")
            md.append(f"- Hücre sayısı: **{mq.get('cells')}**  ")
            md.append(f"- Prism katman: **{mq.get('layers_avg')}** ort. "
                      f"(%{mq.get('coverage_pct')} kalınlık kapsamı)  ")
            md.append(f"- Max non-orthogonality: **{mq.get('non_ortho_max')}°** "
                      f"(ort. {mq.get('non_ortho_avg')}°)  ")
            md.append(f"- **y⁺**: min={mq.get('yplus_min')}, "
                      f"ort=**{mq.get('yplus_avg')}**, max={mq.get('yplus_max')}  ")
            yavg = mq.get('yplus_avg', 0)
            reg = ("viskoz alt-tabaka (y⁺<5)" if yavg < 5 else
                   "buffer/log bölgesi (5<y⁺<30) — kOmegaSST sürekli duvar fn." if yavg < 30 else
                   "log bölgesi (wall function)")
            md.append(f"- Çözüm rejimi: {reg}\n")

        # 1. Mesh bagimsizlik
        if mesh_indep:
            gci = fig_mesh_convergence(mesh_indep, self.out / "figures" / "mesh_convergence.png")
            md.append("## 1. Mesh Bağımsızlık Analizi (GCI)\n")
            md.append("| Mesh | h (m) | Hücre | $C_d$ | $C_l$ |")
            md.append("|------|-------|-------|-------|-------|")
            for m in sorted(mesh_indep, key=lambda x: -x["h"]):
                md.append(f"| {m.get('name','-')} | {m['h']:.4f} | "
                          f"{m.get('cells','-')} | {m['Cd']:.4f} | {m.get('Cl','-')} |")
            if gci:
                md.append(f"\n**Richardson ekstrapolasyon:** $C_d$ = {gci['f_exact']:.4f}  ")
                md.append(f"**Gözlemlenen mertebe** p = {gci['p']}  ")
                md.append(f"**GCI (fine)** = {gci['gci_fine_pct']}%  ")
                md.append(f"**Asimptotik oran** = {gci.get('asymptotic')}  ")
                md.append(f"**Sonuç:** {gci_verdict(gci)}\n")
            md.append("![Mesh Convergence](figures/mesh_convergence.png)\n")

        # 1b. 2D airfoil GCI (O-grid, gecis modeli)
        if airfoil_gci and airfoil_gci.get("levels"):
            levels = airfoil_gci["levels"]
            refs = airfoil_gci.get("reference", {})
            gci2 = fig_airfoil_gci(levels, refs, self.out / "figures" / "airfoil_gci.png")
            md.append(f"## 1b. 2D Airfoil GCI — NACA0012 α={airfoil_gci.get('alpha')}° "
                      f"({airfoil_gci.get('model')})\n")
            md.append("| Seviye | Grid | Hücre | $C_d$ | $C_l$ | İter. drift | Durum |")
            md.append("|--------|------|-------|-------|-------|-------------|-------|")
            for lv in sorted(levels, key=lambda x: x["cells"]):
                stat = "✅ ok" if lv.get("status") == "ok" else f"❌ {lv.get('status')}"
                cd_s = f"{lv['Cd']:.5f}" if lv.get("Cd") is not None else "—"
                cl_s = f"{lv['Cl']:.4f}" if lv.get("Cl") is not None else "—"
                dr_s = f"{lv['drift']:.1e}" if lv.get("drift") is not None else "—"
                md.append(f"| {lv['name']} | {lv.get('grid','-')} | {lv['cells']} | "
                          f"{cd_s} | {cl_s} | {dr_s} | {stat} |")
            if gci2:
                md.append(f"\n**Gözlemlenen mertebe** p = {gci2['p']}  ")
                if gci2.get("monotonic") and gci2.get("p_in_range"):
                    md.append(f"**Richardson (en ince 3 geçerli seviye):** $C_d$ = "
                              f"{gci2['f_exact']:.5f}  ")
                    md.append(f"**GCI (fine)** = {gci2['gci_fine_pct']}%  ")
                else:
                    md.append("**Richardson ekstrapolasyonu raporlanmadı** "
                              "(asimptotik aralık dışı — değer anlamsız olur)  ")
                md.append(f"**Sonuç:** {gci_verdict(gci2)}\n")
            if refs:
                md.append(f"*Referans: Ladson — serbest geçiş Cd={refs.get('Cd_free')}, "
                          f"türbülanslı Cd={refs.get('Cd_turb')}, Cl={refs.get('Cl')}.*\n")
            if airfoil_gci.get("note"):
                md.append(f"> ⚠️ *{airfoil_gci['note']}*\n")
            md.append("![Airfoil GCI](figures/airfoil_gci.png)\n")

        # 1c. 2D gecis-modeli polar
        if transition:
            ok = fig_transition_polar(transition, self.out / "figures" / "transition_polar.png")
            md.append(f"## 1c. 2D Geçiş-Modeli Polar — NACA0012 "
                      f"({transition.get('model', 'kOmegaSSTLM')}, "
                      f"{transition.get('mesh', '-')})\n")
            md.append("| α (°) | $C_l$ | $C_l$ ref | Hata | Sonuç | $C_d$ | $C_d$ ref (serbest) |")
            md.append("|-------|-------|-----------|------|-------|-------|---------------------|")
            for k in sorted([k for k in transition if k.isdigit()], key=int):
                r = transition[k]
                if not isinstance(r, dict) or r.get("Cl") is None:
                    md.append(f"| {k} | — | — | — | ❌ {r.get('status', '?')} | — | — |")
                    continue
                clr = r.get("Cl_ref", 0)
                if abs(clr) < 0.05:
                    cl_ok = abs(r["Cl"] - clr) <= TOL_CL_ABS
                    err_s = f"ΔCl={abs(r['Cl'] - clr):.4f} (mutlak)"
                else:
                    cl_ok = r.get("errCl", 1e9) <= TOL_CL_PCT
                    err_s = f"{r.get('errCl')}%"
                md.append(f"| {k} | {r['Cl']:.4f} | {clr} | "
                          f"{err_s} | {'✅' if cl_ok else '❌'} | "
                          f"{r['Cd']:.5f} | {r.get('Cd_ref_free', '-')} |")
            md.append("\n> ⚠️ *Cd bu çözünürlükte mesh-bağımsız değil (Bölüm 1b) — "
                      "Cd sütunu bilgilendirme amaçlı, doğrulama kanıtı değil. "
                      "Cl doğrulaması geçerlidir.*\n")
            if ok:
                md.append("![Transition Polar](figures/transition_polar.png)\n")

        # 2. Validation
        if validation:
            fig_validation_bars(validation, self.out / "figures" / "validation.png")
            md.append("## 2. Çözücü Validasyonu\n")
            md.append("| Test | Büyüklük | Referans | Simülasyon | Hata | Sonuç |")
            md.append("|------|----------|----------|------------|------|-------|")
            for key, r in validation.items():
                if key.startswith("cfd_") and "Cd_ref" in r:
                    cd_ok = r["Cd_err_pct"] <= TOL_CD_PCT
                    md.append(f"| NACA0012 α={r.get('alpha')}° | Cd | {r['Cd_ref']:.4f} | "
                              f"{r['Cd_sim']:.4f} | {r['Cd_err_pct']}% | "
                              f"{'✅' if cd_ok else '❌'} |")
                    cl_note = " (mutlak kriter)" if abs(r.get("Cl_ref", 0)) < 0.05 else ""
                    md.append(f"| NACA0012 α={r.get('alpha')}° | Cl | {r['Cl_ref']:.4f} | "
                              f"{r['Cl_sim']:.4f} | {r.get('Cl_err_pct')}%{cl_note} | "
                              f"{'✅' if _cl_pass(r) else '❌'} |")
                if key == "fea_cantilever":
                    md.append(f"| Ankastre kiriş | δ (mm) | {r['delta_analytic_mm']} | "
                              f"{r['delta_fea_mm']} | {r['deflection_err_pct']}% | "
                              f"{'✅' if r['deflection_err_pct'] <= TOL_FEA_PCT else '❌'} |")
            md.append(f"\n*Kabul eşikleri: Cd ≤ %{TOL_CD_PCT:.0f}, Cl ≤ %{TOL_CL_PCT:.0f} "
                      f"(|Cl_ref|≈0 için |ΔCl| ≤ {TOL_CL_ABS}), FEA ≤ %{TOL_FEA_PCT:.0f}.*\n")
            md.append("![Validation](figures/validation.png)\n")

        # 2b. FEA cozucu V&V suite — kanonik analitik dogrulamalar (gercek ccx kosulari)
        if fea_validations:
            md.append("## 2b. FEA Çözücü V&V Suite (Kanonik Analitik Doğrulamalar)\n")
            md.append("Üretim FEA hattının (gmsh → calculix_writer → ccx → frd-parse) her "
                      "yük mekanizması, bağımsız kapalı-form çözümle ayrı ayrı doğrulanır.\n")
            md.append("| Kanonik Vaka | Doğrulanan yol | Hata | Durum |")
            md.append("|--------------|----------------|------|-------|")
            worst_all, n_pass = 0.0, 0
            for fv in fea_validations:
                vaka = fv.get("vaka", "?")
                err = _fea_val_error_pct(fv)
                passed = "GECTI" in (fv.get("sonuc", "") or "")
                n_pass += int(passed)
                if err is not None:
                    worst_all = max(worst_all, err)
                err_s = f"%{err:.1f}" if err is not None else "—"
                formul = (fv.get("analitik") or {}).get("formul") \
                    or (fv.get("sehim") or {}).get("formul") or "—"
                md.append(f"| {vaka} | `{formul}` | {err_s} | {'✅' if passed else '⚠️'} |")
            md.append(f"\n*{n_pass}/{len(fea_validations)} vaka geçti; en kötü hata "
                      f"%{worst_all:.1f} (suite kabul eşiği %{TOL_FEA_SUITE_PCT:.0f}). "
                      "Doğrulanan mekanizmalar: uç-yük/sehim (kiriş), gerilme-konsantrasyonu "
                      "(delik Kt), iç-basınç (silindir hoop), gövde-kuvveti (öz-ağırlık / "
                      "manevra g-yükü), termal (engellenmiş genleşme), stabilite (Euler "
                      "burkulması). Bu mekanizmalar araç-FEA'sının ve CFD→FEA kuplajının "
                      "dayandığı kod yollarıdır.*\n")
            md.append("> ℹ️ *Bu suite üretim FEA **kod yollarını** doğrular (V&V), tasarım "
                      "marjı vermez. Burkulma vakasındaki λ₁, keyfi referans yüke göre "
                      "özdeğerdir — gerçek tasarım marjı için araç-FEA'sındaki fiili "
                      "basınç/eksenel yük kullanılır.*\n")

        # 2c. FEA gerilme mesh-yakınsaması (SOLUTION verification — code-verification'a ek)
        if fea_stress_gci:
            g = fea_stress_gci
            gci = g.get("gci", {})
            an = g.get("analitik_Kt_MPa")
            fex = gci.get("f_exact")
            dev = abs(fex - an) / an * 100 if (an and fex) else None
            md.append("## 2c. FEA Gerilme Mesh-Yakınsaması (Solution Verification, GCI)\n")
            md.append("Code-verification (2b) çözücü yolunu doğrular; bu bölüm en mesh-"
                      "duyarlı niceliğin (tepe gerilme) **mesh-bağımsız** olduğunu gösterir "
                      "— emniyet faktörü ancak bu durumda savunulabilir.\n")
            md.append(f"*{g.get('vaka', '')} — {g.get('yontem', '')}*\n")
            md.append("| h (mm) | Düğüm | σ_tepe (MPa) | tepe/temsili |")
            md.append("|--------|-------|--------------|--------------|")
            for lv in g.get("seviyeler", []):
                md.append(f"| {lv['h_mm']} | {lv['dugum']:,} | {lv['sigma_tepe_MPa']} | "
                          f"{lv['tepe_temsili']} |")
            md.append(f"\n- **Gözlemlenen mertebe** p = {gci.get('p')}  ")
            md.append(f"- **Richardson** σ = {fex:.2f} MPa"
                      + (f" (Heywood analitiğine %{dev:.1f})  " if dev is not None else "  "))
            md.append(f"- **GCI (ince)** = {gci.get('gci_fine_pct')}%, "
                      f"tepe-değer yayılımı (6× düğüm) = %{g.get('tepe_yayilim_pct')}  ")
            md.append(f"\n> {g.get('fiziksel_sonuc', '')}\n")
            md.append(f"> *Strict-GCI: {g.get('strict_gci_verdict', '')} — değer <%1 gürültü-"
                      "tabanında salınır (monoton değil ama yakınsamış); fiziksel hüküm "
                      "yayılım+analitik-sapmaya dayanır.*\n")

        # 3. Yapisal yuk zarfi
        if envelope:
            fig_vn_diagram(envelope, self.out / "figures" / "vn_diagram.png")
            md.append("## 3. Yapısal Yük Zarfı (V-n)\n")
            sp = envelope["speeds_ms"]
            md.append(f"- Kategori: **{envelope['category']}**, n_max=**{envelope['n_max']}**, "
                      f"n_min=**{envelope['n_min']}**  ")
            md.append(f"- Kanat yüklemesi W/S = **{envelope['wing_loading_Pa']} Pa**  ")
            md.append(f"- Vs1={sp['Vs1']}, Va={sp['Va']}, Vc={sp['Vc']}, Vd={sp['Vd']} m/s\n")
            md.append("**Kritik yük durumları:**\n")
            md.append("| Durum | V (m/s) | n | Limit (N) | Ultimate (N) |")
            md.append("|-------|---------|---|-----------|--------------|")
            for c in envelope["critical_cases"]:
                star = " ⭐" if c.get("is_design_critical") else ""
                md.append(f"| {c['name']}{star} | {c['V']} | {c['n']} | "
                          f"{c['limit_load_N']} | {c['ultimate_load_N']} |")
            md.append("\n![V-n Diagram](figures/vn_diagram.png)\n")

        # 4. FEA
        if fea:
            md.append("## 4. Yapısal Analiz (FEA)\n")
            md.append(f"- Malzeme: {fea.get('material')}, kalınlık {fea.get('shell_thickness_mm')} mm  ")
            md.append(f"- Kanat: span {fea.get('span_m')} m, kök {fea.get('root_chord_m')} m\n")
            md.append("| Yük | g | Tip sehim (mm) | von Mises (MPa) | SF | Güvenli |")
            md.append("|-----|---|----------------|-----------------|----|----|")
            for lt in ("limit", "ultimate"):
                if lt in fea and "safety_factor" in fea[lt]:
                    d = fea[lt]
                    md.append(f"| {lt} | {d['g_factor']} | {d['tip_deflection_mm']} | "
                              f"{d['max_von_mises_MPa']} | {d['safety_factor']} | "
                              f"{'✅' if d['is_safe'] else '❌'} |")
            md.append("")

        # 5. CFD->FEA coupling
        if coupling:
            md.append("## 5. CFD→FEA Basınç Coupling (1-way FSI)\n")
            md.append(f"- CFD yüzey: {coupling.get('n_cfd_faces')} → FEA düğüm: "
                      f"{coupling.get('n_loaded_nodes')}  ")
            md.append(f"- Basınç aralığı: [{coupling.get('p_min_Pa'):.1f}, "
                      f"{coupling.get('p_max_Pa'):.1f}] Pa  ")
            md.append(f"- Aktarılan kuvvet: Drag={coupling.get('drag_Fx_N')} N, "
                      f"Lift={coupling.get('lift_Fz_N')} N  ")
            ce = coupling.get("conservation_error", 0)
            md.append(f"- **Korunum hatası: {ce:.2e}** "
                      f"({'✅ makine hassasiyeti' if ce < 1e-10 else '⚠️'})\n")

        # 6. Aerodinamik polar / stall
        if polar:
            st = fig_polar(polar, self.out / "figures" / "polar.png")
            md.append("## 6. Aerodinamik Polar ve Stall (3D)\n")
            md.append("| α (°) | $C_L$ | $C_D$ | L/D |")
            md.append("|-------|-------|-------|-----|")
            for r in sorted([p for p in polar if p.get("Cl") is not None],
                            key=lambda x: x["alpha"]):
                md.append(f"| {r['alpha']} | {r['Cl']} | {r['Cd']} | {r.get('LD','-')} |")
            md.append("![Polar](figures/polar.png)\n")
            # DÜRÜST çalışma-zarfı: CLmax'ı steady-RANS'tan TÜRETME (stall'da ~%45 düşük —
            # NACA0012'de α=10/12°'de ölçüldü). Stall-onset yalnız zarf-sınırı sinyali;
            # CLmax ancak DENEYSEL referanstan verilir (3D araç için tanımlı değilse VERİLMEZ).
            from validity_envelope import analyze_polar_envelope, polar_envelope_md
            _pp = [p for p in polar if p.get("Cl") is not None]
            if _pp:
                md.append(polar_envelope_md(analyze_polar_envelope(_pp, clmax_ref=None)))

        # 7. VSPAERO VLM çapraz-doğrulama
        if vspaero:
            vok = [v for v in vspaero if v.get("Cl") is not None]
            md.append("## 7. VSPAERO VLM Çapraz-Doğrulama (Hızlı)\n")
            md.append("Bağımsız ikinci yöntem (vortex-lattice, inviscid, ~saniyeler). "
                      "Lift eğimini OpenFOAM'dan bağımsız doğrular.\n")
            md.append("| α (°) | $C_L$ (VLM) | $C_{Di}$ (induced) |")
            md.append("|-------|-------------|--------------------|")
            for v in sorted(vok, key=lambda x: x["alpha"]):
                md.append(f"| {v['alpha']} | {v['Cl']} | {v['Cd_i']} |")
            if len(vok) >= 2:
                sv = (vok[-1]["Cl"] - vok[0]["Cl"]) / (vok[-1]["alpha"] - vok[0]["alpha"])
                line = f"\n**VSPAERO lift eğimi = {sv:.4f}/°**"
                if polar:
                    pok = sorted([p for p in polar if p.get("Cl") is not None],
                                 key=lambda x: x["alpha"])
                    if len(pok) >= 2:
                        sf = (pok[1]["Cl"] - pok[0]["Cl"]) / (pok[1]["alpha"] - pok[0]["alpha"])
                        agree = abs(sv - sf) / (abs(sf) + 1e-9) * 100
                        line += f"  vs **OpenFOAM = {sf:.4f}/°** → uyum %{agree:.0f} fark"
                md.append(line + "\n")
            md.append("> *VLM inviscid: $C_{Di}$ sadece induced drag (viskoz yok), "
                      "stall yakalamaz. Camber VSP modelinde uygulanmadığından "
                      "$C_L(α{=}0){=}0$ — eğim geçerli, mutlak değer camber kadar kayık.*\n")

        # 8. Roket analizi (OpenRocket)
        if rocket and rocket.get("status") == "SUCCESS":
            md.append("## 8. Roket Uçuş Analizi (OpenRocket)\n")
            md.append("Barrowman + 6-DOF uçuş simülasyonu (hızlı katman, "
                      "sabit-kanattaki VSPAERO'nun roket karşılığı).\n")
            md.append("| Metrik | Değer |")
            md.append("|--------|-------|")
            md.append(f"| Apogee | **{rocket.get('apogee_m')} m** |")
            md.append(f"| Apogee süresi | {rocket.get('time_to_apogee_s')} s |")
            md.append(f"| Max hız | {rocket.get('max_velocity_ms')} m/s (Mach {rocket.get('max_mach')}) |")
            md.append(f"| Max ivme | {rocket.get('max_accel_g')} g |")
            md.append(f"| Burnout | {rocket.get('burnout_time_s')} s @ {rocket.get('burnout_altitude_m')} m |")
            md.append(f"| Kalkış kütlesi | {rocket.get('liftoff_mass_kg')} kg |")
            smin = rocket.get('stability_min_cal')
            smax = rocket.get('stability_max_cal')
            safe_stab = smin is not None and smin >= 1.0
            md.append(f"| **Stabilite marjı** | {smin}–{smax} cal "
                      f"{'✅ (>1 stabil)' if safe_stab else '⚠️ (<1 kararsız!)'} |")
            cdm = rocket.get("cd_vs_mach", [])
            if cdm:
                md.append("\n**Cd–Mach (Barrowman):**\n")
                md.append("| Mach | $C_d$ |")
                md.append("|------|-------|")
                for p in cdm:
                    md.append(f"| {p['Mach']} | {p['Cd']} |")
            md.append("> *Düşük-irtifa model roketi: stabilite >1 cal gerekli "
                      "(FAA/NAR güvenlik). Barrowman ~Mach 0.8'e kadar geçerli.*\n")

            # Roket CFD Cd çapraz-doğrulama (R2)
            if rocket_cfd and rocket_cfd.get("status") == "SUCCESS":
                md.append("**8.1 Cd Çapraz-Doğrulama (OpenFOAM CFD):**\n")
                md.append(f"- CFD $C_d$ = **{rocket_cfd.get('Cd_cfd')}** "
                          f"(V={rocket_cfd.get('V_ms')} m/s, S_ref={rocket_cfd.get('S_ref_m2')} m²)  ")
                if "Cd_openrocket" in rocket_cfd:
                    md.append(f"- OpenRocket Barrowman $C_d$ = {rocket_cfd.get('Cd_openrocket')}  ")
                    md.append(f"- **Fark: %{rocket_cfd.get('cross_val_err_pct')}** "
                              "(iki bağımsız yöntem)\n")

            # Fin yapısal (R3): flutter + FEA
            if rocket_fin:
                fl = rocket_fin.get("flutter", {})
                fe = rocket_fin.get("static_fea", {})
                md.append("**8.2 Fin Yapısal Analizi:**\n")
                md.append("| Kriter | Değer | Durum |")
                md.append("|--------|-------|-------|")
                md.append(f"| Flutter hızı | {fl.get('flutter_velocity_ms')} m/s "
                          f"(Mach {fl.get('flutter_mach')}) | — |")
                fm = rocket_fin.get("flutter_margin")
                md.append(f"| Flutter marjı | **{fm}×** (Vuçuş={rocket_fin.get('v_flight_ms')} m/s) | "
                          f"{'✅' if rocket_fin.get('flutter_safe') else '⚠️ KRİTİK'} |")
                if fe.get("status") == "SUCCESS":
                    md.append(f"| Fin sehim (max-q) | {fe.get('tip_deflection_mm')} mm | — |")
                    md.append(f"| Fin von Mises | {fe.get('max_von_mises_MPa')} MPa | — |")
                    md.append(f"| Fin SF | {fe.get('safety_factor')} | "
                              f"{'✅' if fe.get('is_safe') else '⚠️'} |")
                md.append(f"\n> *Flutter = roketin baskın fin kriteri (NACA TN 4197). "
                          f"Malzeme: {fl.get('material')}, G={fl.get('shear_modulus_GPa')} GPa. "
                          f"Vf<Vuçuş olursa fin titreşip kopar.*\n")

        # V&V notları / dürüst limitasyonlar
        md.append("## V&V Notları ve Geçerlilik Sınırları\n")
        md.append("- **2D y⁺<1 + kOmegaSSTLM geçiş modeli:** kapalı-TE eliptik O-grid "
                  "(non-ortho ≤65°, 0 açık hücre) ile çalışır; iki aşamalı başlatma "
                  "(SST → LM, geçiş alanları restart zamanına kopyalanır) gerekir.  ")
        md.append("- **2D Cl:** mesh-stabil ve referansla uyumlu — kaldırma doğrulaması "
                  "için bu O-grid ailesi yeterli.  ")
        md.append("- **2D Cd:** wake-kümelemesiz O-grid ailesinde kaba seviyeler asimptotik "
                  "aralık dışı kalabilir (negatif basınç sürüklemesi); sürükleme GCI'ı ancak "
                  "yeterince ince, iterasyon-yakınsamış seviyelerle raporlanır. Kesin Cd "
                  "doğrulaması için wake-çözünürlüklü (C-grid) topoloji önerilir.  ")
        md.append("- **3D MiniHawk:** prism layer y⁺~14 (buffer/log), kOmegaSST sürekli "
                  "duvar fonksiyonu geçerli; stall bölgesi RANS belirsizliği yüksek.  ")
        md.append("- **Yapısal:** FEA analitikle <%0.05; kanat kabuk modeli, "
                  "tam-araç gövde rijitliği ihmal.  ")
        md.append("- **İterasyon yakınsaması:** GCI öncesi her seviyede kuvvet drifti "
                  "grid-farklarının küçüğü olmalı (ASME V&V 20 ön-koşulu); tablodaki "
                  "drift sütunu son 500 iterasyondaki |ΔCd|.\n")

        md.append("\n---\n*Otomatik üretildi — CFD/FEA Tools V&V pipeline*\n")

        report_path = self.out / "VV_report.md"
        report_path.write_text("\n".join(md), encoding="utf-8")
        return report_path


if __name__ == "__main__":
    from structural_loads import FlightEnvelope

    # Mevcut sonuclari topla
    base = Path(".")
    mesh_indep = None
    mifile = base / "mesh_independence.json"
    if mifile.exists():
        mesh_indep = json.loads(mifile.read_text(encoding="utf-8-sig")).get("levels")

    validation = {}
    vfile = base / "validation" / "validation_results.json"
    if vfile.exists():
        validation = json.loads(vfile.read_text(encoding="utf-8-sig"))

    env = FlightEnvelope(
        mass_kg=1.8, wing_area_m2=0.45, wing_span_m=1.5, mac_m=0.30,
        cl_max=1.3, cl_min=-1.04, cl_alpha=5.0, v_cruise_ms=18.0,
    ).summary()

    coupling = None
    cfile = base / "coupling_result.json"
    if cfile.exists():
        coupling = json.loads(cfile.read_text(encoding="utf-8-sig"))

    fea = None
    ffile = base / "fea_critical.json"
    if ffile.exists():
        fea = json.loads(ffile.read_text(encoding="utf-8-sig"))

    mesh_quality = None
    mqfile = base / "mesh_quality.json"
    if mqfile.exists():
        mesh_quality = json.loads(mqfile.read_text(encoding="utf-8-sig"))

    polar = None
    pfile = base / "aoa_polar.json"
    if pfile.exists():
        polar = json.loads(pfile.read_text(encoding="utf-8-sig"))

    vspaero = None
    vfile = base / "vspaero_polar.json"
    if vfile.exists():
        vspaero = json.loads(vfile.read_text(encoding="utf-8-sig"))

    def _load(name):
        f = base / name
        return json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else None

    rocket     = _load("openrocket_result.json")
    rocket_fin = _load("rocket_fin_result.json")
    rocket_cfd = _load("rocket_cfd_result.json")
    airfoil_gci = _load("gci_airfoil.json")
    transition  = _load("transition_results.json")

    # Kanonik FEA V&V suite — fea_validation*.json (kiriş, delik, silindir, gravite,
    # termal, burkulma). Mantıklı sıra: ana kiriş önce, ötekiler ada göre.
    fea_validations = []
    for f in sorted(base.glob("fea_validation*.json")):
        d = json.loads(f.read_text(encoding="utf-8-sig"))
        if isinstance(d, dict) and d.get("vaka"):
            fea_validations.append(d)

    fea_stress_gci = _load("fea_stress_gci.json")   # FEA solution-verification (GCI)

    rep = VVReport("./report")
    path = rep.build(mesh_indep=mesh_indep, validation=validation,
                     envelope=env, fea=fea, coupling=coupling,
                     mesh_quality=mesh_quality, polar=polar, vspaero=vspaero,
                     rocket=rocket, rocket_fin=rocket_fin, rocket_cfd=rocket_cfd,
                     airfoil_gci=airfoil_gci, transition=transition,
                     fea_validations=fea_validations, fea_stress_gci=fea_stress_gci)
    print(f"Rapor olusturuldu: {path}")
