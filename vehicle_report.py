"""
Araç analizi mühendis raporu: figürler + tablolar + yorumlar (300 DPI, Markdown).
vehicle_pipeline.run_vehicle_analysis() sonunda otomatik çağrılır.
Verdiktler proje eşiklerinden hesaplanır; sınırlar dürüstçe yazılır.
"""
from __future__ import annotations

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

NONORTHO_LIMIT = 70.0
SKEW_LIMIT = 4.0

TYPE_COMMENT = {
    "ucak": ("Sabit kanatlı araçta birincil metrikler C_L, C_D ve L/D'dir. "
             "Planform referans alanı konveks-zarf izdüşümünden kestirildi; "
             "kanat dışı gövde izdüşümü alanı bir miktar büyütür, katsayılar "
             "buna göre hafif iyimser/kötümser olabilir. Hücum açısı taraması "
             "ve trim/moment analizi bu tek-nokta koşusunun kapsamı dışındadır."),
    "roket": ("Roket gövdesinde birincil metrik ön-alan bazlı C_D'dir. Tipik "
              "model roket gövdesi C_D ≈ 0.4–0.8 bandındadır (fin ve yüzey "
              "pürüzlülüğüne bağlı). Burun basıncı + taban (base) sürüklemesi "
              "toplamı baskındır; taban sürüklemesi RANS'ta sistematik olarak "
              "hatalı çözülebilir."),
    "multikopter": ("Küt gövdede anlamlı metrik CdA (sürükleme alanı)'dır; "
                    "ileri uçuş güç bütçesi P ≈ q·V·CdA ile kestirilebilir. "
                    "Pervane/rotor etkileri modellenmedi — yalnız gövde."),
    "genel": ("Küt cisim sürüklemesi ayrılma noktasına duyarlıdır; RANS "
              "(kOmegaSST) masif ayrılmada ±%20+ belirsizlik taşır."),
}


def _fig_convergence(history, out):
    if len(history) < 3:
        return False
    t = [h[0] for h in history]
    cd = [h[1] for h in history]
    cl = [h[2] for h in history]
    has_cl = any(math.isfinite(v) for v in cl)
    fig, ax = plt.subplots(figsize=(5, 3.2))
    ax.plot(t, cd, color="#1f4e79", lw=1.2, label="$C_D$")
    if has_cl:
        ax2 = ax.twinx()
        ax2.plot(t, cl, color="#2e7d32", lw=1.2, label="$C_L$")
        ax2.set_ylabel("$C_L$", color="#2e7d32")
        ax2.grid(False)
    ax.set_xlabel("İterasyon")
    ax.set_ylabel("$C_D$", color="#1f4e79")
    ax.set_title("Kuvvet Katsayısı Yakınsaması", fontsize=10)
    n = len(cd)
    if n >= 10:
        w = max(2, n // 5)
        lo, hi = min(cd[-w:]), max(cd[-w:])
        ax.axhspan(lo, hi, color="#1f4e79", alpha=0.08)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return True


def _fig_residuals(residuals, out):
    fields = [f for f in ("Ux", "Uy", "Uz", "p", "k", "omega") if residuals.get(f)]
    if not fields:
        return False
    fig, ax = plt.subplots(figsize=(5, 3.2))
    for f in fields:
        ax.semilogy(residuals[f], lw=1.0, label=f)
    ax.axhline(1e-4, ls="--", color="#c00000", lw=1, label="hedef 1e-4")
    ax.set_xlabel("İterasyon")
    ax.set_ylabel("Initial residual")
    ax.set_title("Çözücü Rezidüelleri", fontsize=10)
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return True


def _fig_geometry(geo, out):
    labels = ["Ön alan\n(m²)", "Planform\n(m²)", "Yüzey\n(m²)"]
    vals = [geo["on_alan_m2"], geo["planform_alan_m2"], geo["yuzey_alani_m2"]]
    fig, ax = plt.subplots(figsize=(4, 2.8))
    ax.bar(labels, vals, color=["#1f4e79", "#2e7d32", "#7b1fa2"], width=0.55)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.4g}", ha="center", va="bottom", fontsize=8)
    ax.set_title("Geometri Referans Alanları", fontsize=10)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return True


def build_vehicle_report(r, history, residuals, out_dir: Path) -> Path:
    """r: VehicleAnalysisResult. Markdown rapor + 300 DPI figürler üretir."""
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    geo, mesh, conv = r.geometry, (r.mesh or {}), (r.convergence or {})

    f_conv = _fig_convergence(history, out / "figures" / "convergence.png")
    f_res = _fig_residuals(residuals, out / "figures" / "residuals.png")
    _fig_geometry(geo, out / "figures" / "geometry.png")

    md = [f"# Aerodinamik Analiz Raporu — {geo['dosya']}",
          f"\n**Araç tipi:** {r.vehicle_type}  ",
          f"**Tarih:** {datetime.now():%Y-%m-%d %H:%M}  ",
          f"**Akış:** V = {r.velocity} m/s, α = {r.alpha_deg}°, deniz seviyesi havası  ",
          "**Yöntem:** OpenFOAM 11, snappyHexMesh + foamRun (SIMPLE, kOmegaSST RANS)  ",
          "\n---\n"]

    # 1. Geometri
    md.append("## 1. Geometri\n")
    dims = geo["boyutlar_m"]
    md.append(f"- Kapsayan kutu: **{dims[0]} × {dims[1]} × {dims[2]} m** (L_ref = {geo['lmax_m']} m)  ")
    md.append(f"- Üçgen sayısı: {geo['ucgen_sayisi']:,} — su geçirmezlik: "
              f"{'✅ kapalı' if geo['su_gecirmez'] else '⚠️ açık (snappyHexMesh toleranslı ama riskli)'}  ")
    md.append(f"- Referans alan ({r.aref_mode}): **{r.aref_m2} m²** "
              "(konveks-zarf izdüşümü — içbükey kesitlerde üst sınır)\n")
    md.append("![Geometri](figures/geometry.png)\n")

    # 2. Mesh kalitesi
    md.append("## 2. Mesh Kalitesi\n")
    no, sk = mesh.get("non_ortho_max"), mesh.get("skew_max")
    md.append(f"- Hücre sayısı: **{mesh.get('cells'):,}**  " if mesh.get("cells") else "- Hücre sayısı: ?  ")
    if no is not None:
        md.append(f"- Max non-orthogonality: **{no}°** "
                  f"{'✅' if no < NONORTHO_LIMIT else f'❌ (limit {NONORTHO_LIMIT}°)'}  ")
    if sk is not None:
        md.append(f"- Max skewness: **{sk}** "
                  f"{'✅' if sk < SKEW_LIMIT else f'❌ (limit {SKEW_LIMIT})'}  ")
    md.append("- Sınır tabaka: prizma katmanı YOK — duvar y⁺ kontrolsüz; "
              "sürtünme sürüklemesi duvar fonksiyonu varsayımıyla, mutlak C_D "
              "buna bağlı belirsizlik taşır.\n")

    # 3. Yakınsama
    md.append("## 3. Yakınsama\n")
    md.append(f"- İterasyon: {conv.get('iterasyon')}  ")
    d = conv.get("cd_drift_son20pct")
    if d is not None:
        md.append(f"- C_D drifti (son %20 pencere): **%{d}** "
                  f"{'✅' if conv.get('drift_ok') else '⚠️ (hedef <%2 — daha uzun koşu önerilir)'}  ")
    rr = conv.get("son_rezidualler", {})
    if rr:
        md.append("- Son rezidüeller: " + ", ".join(f"{k}={v}" for k, v in rr.items()) +
                  (" ✅" if conv.get("rezidual_ok") else " ⚠️ (hedef <1e-4)") + "  ")
    md.append("")
    if f_conv:
        md.append("![Yakınsama](figures/convergence.png)\n")
    if f_res:
        md.append("![Rezidüeller](figures/residuals.png)\n")

    # 4. Sonuçlar
    md.append("## 4. Aerodinamik Sonuçlar\n")
    md.append("| Büyüklük | Değer |")
    md.append("|----------|-------|")
    md.append(f"| $C_D$ (A_ref = {r.aref_m2} m²) | **{r.cd}** |")
    if r.cl is not None:
        md.append(f"| $C_L$ | **{r.cl}** |")
    if r.ld is not None:
        md.append(f"| L/D | **{r.ld}** |")
    md.append(f"| CdA (sürükleme alanı) | {r.cda_m2} m² |")
    md.append(f"| Sürükleme kuvveti @ {r.velocity} m/s | **{r.drag_N} N** |")
    q = 0.5 * 1.225 * r.velocity**2
    md.append(f"| Sürükleme gücü @ {r.velocity} m/s | {r.drag_N * r.velocity:.1f} W |")
    md.append(f"| Dinamik basınç q | {q:.1f} Pa |\n")

    # 4b. Uyarılar + mesh duyarlılığı
    if getattr(r, "uyarilar", None):
        for u in r.uyarilar:
            md.append(f"> ⚠️ **UYARI:** {u}\n")
    md_s = getattr(r, "mesh_duyarlilik", None)
    if md_s:
        if "fark_pct" in md_s:
            band = md_s["fark_pct"]
            ok = band < 10
            md.append(f"**Mesh duyarlılık bandı:** kaba seviye $C_D$={md_s['kaba_cd']} → "
                      f"iki-seviye farkı **±%{band}** "
                      f"{'✅ (<%10 — sonuç bu bantla savunulabilir)' if ok else '⚠️ (≥%10 — daha ince mesh önerilir)'}  ")
            md.append(f"*{md_s['yorum']}*\n")
        else:
            md.append(f"**Mesh duyarlılık:** {md_s.get('durum')}\n")

    # 5. Mühendis yorumu
    md.append("## 5. Mühendislik Değerlendirmesi\n")
    md.append(TYPE_COMMENT.get(r.vehicle_type, "") + "\n")
    bullet = []
    if r.vehicle_type == "ucak" and r.ld is not None:
        if r.ld > 10:
            bullet.append(f"L/D = {r.ld}: planör/verimli İHA sınıfı — süzülme oranı iyi.")
        elif r.ld > 5:
            bullet.append(f"L/D = {r.ld}: tipik küçük İHA bandı.")
        else:
            bullet.append(f"L/D = {r.ld}: düşük — α={r.alpha_deg}° tasarım noktası "
                          "olmayabilir, polar taraması önerilir.")
    if r.vehicle_type == "roket" and r.cd is not None:
        if 0.3 <= r.cd <= 0.9:
            bullet.append(f"C_D = {r.cd}: model roket beklenti bandında (0.4–0.8).")
        else:
            bullet.append(f"C_D = {r.cd}: tipik bandın dışında — referans alanı ve "
                          "mesh çözünürlüğünü kontrol edin.")
    if conv.get("drift_ok") is False:
        bullet.append("Kuvvet drifti hedefi aşıyor: sonuç ön-tasarım kararı için "
                      "kullanılabilir ama rapor değeri için koşu uzatılmalı.")
    if mesh.get("non_ortho_max") is not None and mesh["non_ortho_max"] >= NONORTHO_LIMIT:
        bullet.append("Mesh non-ortho limit üstünde: snappy refinement/feature "
                      "ayarı gözden geçirilmeli.")
    for b in bullet:
        md.append(f"- {b}")
    md.append("")

    # 6. Geçerlilik sınırları
    md.append("## 6. Geçerlilik Sınırları (V&V)\n")
    md.append("- Tek mesh, tek koşu: **mesh bağımsızlığı gösterilmedi** — kritik "
              "kararlar öncesi en az 3 seviyeli GCI çalışması gerekir (proje kuralı).  ")
    md.append("- RANS kOmegaSST: bağlı akışta güvenilir; masif ayrılma/stall "
              "bölgesinde ±%15-20 belirsizlik.  ")
    md.append("- Prizma katmansız duvar: mutlak sürtünme sürüklemesi yaklaşık; "
              "karşılaştırmalı (tasarım A vs B) kullanım daha güvenilir.  ")
    md.append("- Pervane/itki, dönen parça ve aeroelastik etkiler modellenmedi.\n")

    md.append("\n---\n*Otomatik üretildi — vehicle_pipeline (CFD/FEA Tools)*\n")
    path = out / "RAPOR.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
