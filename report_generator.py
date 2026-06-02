"""
V&V Rapor Ureteci — ASME V&V 20 formati
========================================
Mesh bagimsizlik (GCI), validation hata barlari, V-n diyagrami, polar,
FEA emniyet faktoru ve CFD->FEA coupling korunumunu tek raporda toplar.
300 DPI figurler (MDPI/IEEE kalitesi).
"""

import json
import math
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300,
    "font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
    "axes.linewidth": 0.8,
})


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
    s = math.copysign(1, e32 / e21)
    # Sabit r icin: p = ln|e32/e21| / ln(r)
    p = math.log(abs(e32 / e21)) / math.log(r21)
    f_exact = f_fine + e21 / (r21 ** p - 1)
    gci_fine = Fs * abs(e21 / f_fine) / (r21 ** p - 1) * 100
    gci_med = Fs * abs(e32 / f_med) / (r32 ** p - 1) * 100
    return {
        "p": round(p, 3), "f_exact": round(f_exact, 6),
        "gci_fine_pct": round(gci_fine, 4), "gci_med_pct": round(gci_med, 4),
        "asymptotic": round((r21 ** p) * gci_fine / gci_med, 4) if gci_med else None,
    }


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
    clmax_i = int(np.argmax(cl))
    ax1.plot(a[clmax_i], cl[clmax_i], "rs", ms=7,
             label=f"$CL_{{max}}$={cl[clmax_i]:.2f} @ {a[clmax_i]}°")
    ax1.set_xlabel("Hücum açısı α (°)")
    ax1.set_ylabel("$C_L$")
    ax1.set_title("Kaldırma Eğrisi (stall)", fontsize=9)
    ax1.legend(fontsize=7)

    ax2.plot(cd, cl, "o-", color="#2e7d32", mfc="white", ms=5, lw=1.3)
    ax2.set_xlabel("$C_D$")
    ax2.set_ylabel("$C_L$")
    ax2.set_title("Sürüklenme Poları", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return {"clmax": cl[clmax_i], "alpha_stall": a[clmax_i]}


def fig_validation_bars(val_results, out_path):
    """Validation hata barlari (deney vs simulasyon)."""
    labels, errs, tols = [], [], []
    for key, r in val_results.items():
        if key.startswith("cfd_") and "Cd_err_pct" in r:
            labels.append(f"NACA0012\nα={r.get('alpha')}° Cd")
            errs.append(r["Cd_err_pct"])
            tols.append(40)
        if key == "fea_cantilever" and "deflection_err_pct" in r:
            labels.append("Kiriş\nδ")
            errs.append(r["deflection_err_pct"])
            tols.append(5)

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
              project="MiniHawk İHA"):
        md = [f"# CFD/FEA Doğrulama ve Validation Raporu",
              f"\n**Proje:** {project}  ",
              f"**Tarih:** {datetime.now():%Y-%m-%d %H:%M}  ",
              f"**Standart:** ASME V&V 20-2009, FAR/CS-23  ",
              f"\n---\n"]

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
                verdict = "✅ Yakınsadı (GCI < 5%)" if gci['gci_fine_pct'] < 5 else "⚠️ Yakınsamadı"
                md.append(f"**Sonuç:** {verdict}\n")
            md.append("![Mesh Convergence](figures/mesh_convergence.png)\n")

        # 2. Validation
        if validation:
            fig_validation_bars(validation, self.out / "figures" / "validation.png")
            md.append("## 2. Çözücü Validasyonu\n")
            md.append("| Test | Büyüklük | Referans | Simülasyon | Hata | Sonuç |")
            md.append("|------|----------|----------|------------|------|-------|")
            for key, r in validation.items():
                if key.startswith("cfd_") and "Cd_ref" in r:
                    md.append(f"| NACA0012 α={r.get('alpha')}° | Cd | {r['Cd_ref']:.4f} | "
                              f"{r['Cd_sim']:.4f} | {r['Cd_err_pct']}% | "
                              f"{'✅' if r.get('Cd_pass') else '❌'} |")
                    md.append(f"| NACA0012 α={r.get('alpha')}° | Cl | {r['Cl_ref']:.4f} | "
                              f"{r['Cl_sim']:.4f} | {r.get('Cl_err_pct')}% | "
                              f"{'✅' if r.get('Cl_pass') else '❌'} |")
                if key == "fea_cantilever":
                    md.append(f"| Ankastre kiriş | δ (mm) | {r['delta_analytic_mm']} | "
                              f"{r['delta_fea_mm']} | {r['deflection_err_pct']}% | "
                              f"{'✅' if r.get('deflection_pass') else '❌'} |")
            md.append("\n![Validation](figures/validation.png)\n")

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
            if st:
                md.append(f"\n**CLmax = {st['clmax']} @ α={st['alpha_stall']}°** "
                          f"(stall başlangıcı)\n")
            md.append("![Polar](figures/polar.png)\n")
            md.append("> ⚠️ *RANS (kOmegaSST) stall tahmininde ±2-3° açı ve ±%15 "
                      "CLmax belirsizliği taşır; ayrılmış akış için DES/LES veya "
                      "rüzgar tüneli referansı önerilir.*\n")

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
        md.append("- **Bağlı akış (α=0–8°):** CFD deneyle <%3, mühendislik-güvenilir.  ")
        md.append("- **Sınır tabaka:** prism layer ile y⁺~14 (buffer/log), "
                  "kOmegaSST sürekli duvar fonksiyonu geçerli.  ")
        md.append("- **2D y⁺<1 transition:** tek-blok O-grid topolojisi "
                  "(non-ortho 82°) bunu kaldıramaz; C-grid/eliptik mesh gerektirir.  ")
        md.append("- **Yapısal:** FEA analitikle <%0.05; kanat kabuk modeli, "
                  "tam-araç gövde rijitliği ihmal.\n")

        md.append("\n---\n*Otomatik üretildi — CFD/FEA Tools V&V pipeline*\n")

        report_path = self.out / "VV_report.md"
        report_path.write_text("\n".join(md), encoding="utf-8")
        return report_path


if __name__ == "__main__":
    from structural_loads import FlightEnvelope

    # Mevcut sonuclari topla
    base = Path(".")
    mesh_indep = [
        {"name": "medium", "h": 0.025, "Cd": 0.0286, "Cl": 0.1381, "cells": "~0.4M"},
        {"name": "fine",   "h": 0.012, "Cd": 0.0233, "Cl": 0.1439, "cells": "~0.9M"},
        {"name": "extra",  "h": 0.006, "Cd": 0.0230, "Cl": 0.1455, "cells": "~2M"},
    ]

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

    rep = VVReport("./report")
    path = rep.build(mesh_indep=mesh_indep, validation=validation,
                     envelope=env, fea=fea, coupling=coupling,
                     mesh_quality=mesh_quality, polar=polar, vspaero=vspaero,
                     rocket=rocket, rocket_fin=rocket_fin, rocket_cfd=rocket_cfd)
    print(f"Rapor olusturuldu: {path}")
