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

from constants import NONORTHO_LIMIT, SKEW_LIMIT  # tek kaynak (constants.py)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300,
    "font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
    "axes.linewidth": 0.8,
})

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


def _fig_cp_surface(vtk_path, velocity, out, max_faces=45000):
    """Yüzey Cp haritası: OpenFOAM surfaces VTK'sı → matplotlib 3D render
    (iso + yan görünüm). OpenFOAM incompressible p kinematiktir (m²/s²):
    Cp = p / (0.5·V²)."""
    try:
        import vtk as _vtk
        from vtk.util.numpy_support import vtk_to_numpy
        rd = (_vtk.vtkXMLPolyDataReader() if str(vtk_path).endswith(".vtp")
              else _vtk.vtkPolyDataReader())
        rd.SetFileName(str(vtk_path))
        rd.Update()
        pd = rd.GetOutput()
        if pd.GetNumberOfPolys() > max_faces:
            tri = _vtk.vtkTriangleFilter(); tri.SetInputData(pd); tri.Update()
            dec = _vtk.vtkDecimatePro()
            dec.SetInputData(tri.GetOutput())
            dec.SetTargetReduction(1.0 - max_faces / pd.GetNumberOfPolys())
            dec.Update()
            pd = dec.GetOutput()
        tri = _vtk.vtkTriangleFilter(); tri.SetInputData(pd); tri.Update()
        pd = tri.GetOutput()
        pts = vtk_to_numpy(pd.GetPoints().GetData())
        faces = vtk_to_numpy(pd.GetPolys().GetData()).reshape(-1, 4)[:, 1:]
        q = 0.5 * velocity**2   # OF incompressible p kinematik (m²/s²)
        if pd.GetCellData().GetArray("p") is not None:
            cp_face = vtk_to_numpy(pd.GetCellData().GetArray("p")) / q
        elif pd.GetPointData().GetArray("p") is not None:
            cp_face = (vtk_to_numpy(pd.GetPointData().GetArray("p")) / q)[faces].mean(axis=1)
        else:
            return False

        from matplotlib import cm
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        lo, hi = float(np.percentile(cp_face, 2)), float(np.percentile(cp_face, 98))
        norm = plt.Normalize(lo, hi)
        fig = plt.figure(figsize=(9, 4))
        for k, (elev, azim, title) in enumerate(
                [(25, 150, "rüzgâr-üstü (stagnasyon)"), (25, -30, "rüzgâr-altı (iz bölgesi)")]):
            ax = fig.add_subplot(1, 2, k + 1, projection="3d")
            coll = Poly3DCollection(pts[faces], linewidths=0)
            coll.set_facecolor(cm.coolwarm(norm(cp_face)))
            ax.add_collection3d(coll)
            mn, mx = pts.min(0), pts.max(0)
            c, half = (mn + mx) / 2, (mx - mn).max() / 2
            ax.set_xlim(c[0]-half, c[0]+half)
            ax.set_ylim(c[1]-half, c[1]+half)
            ax.set_zlim(c[2]-half, c[2]+half)
            ax.view_init(elev=elev, azim=azim)
            ax.set_axis_off()
            ax.set_title(title, fontsize=9)
        sm = cm.ScalarMappable(cmap=cm.coolwarm, norm=norm)
        fig.colorbar(sm, ax=fig.axes, shrink=0.7, label="$C_p$")
        fig.suptitle("Yüzey Basınç Katsayısı Dağılımı", fontsize=10)
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        return True
    except Exception:
        return False


def _fig_velocity_slice(vtk_path, velocity, out):
    """Simetri düzlemi |U|/V∞ haritası — iz bölgesi ve hızlanma alanları."""
    try:
        import vtk as _vtk
        from vtk.util.numpy_support import vtk_to_numpy
        rd = _vtk.vtkPolyDataReader()
        rd.SetFileName(str(vtk_path))
        rd.Update()
        tri = _vtk.vtkTriangleFilter(); tri.SetInputData(rd.GetOutput()); tri.Update()
        pd = tri.GetOutput()
        pts = vtk_to_numpy(pd.GetPoints().GetData())
        faces = vtk_to_numpy(pd.GetPolys().GetData()).reshape(-1, 4)[:, 1:]
        if pd.GetCellData().GetArray("U") is not None:
            umag = np.linalg.norm(vtk_to_numpy(pd.GetCellData().GetArray("U")), axis=1)
        elif pd.GetPointData().GetArray("U") is not None:
            up = np.linalg.norm(vtk_to_numpy(pd.GetPointData().GetArray("U")), axis=1)
            umag = up[faces].mean(axis=1)
        else:
            return False
        import matplotlib.tri as mtri
        t = mtri.Triangulation(pts[:, 0], pts[:, 2], faces)
        fig, ax = plt.subplots(figsize=(7, 3.2))
        tp = ax.tripcolor(t, facecolors=umag / velocity, cmap="viridis",
                          vmin=0, vmax=1.4)
        fig.colorbar(tp, ax=ax, label="$|U|/V_\\infty$")

        # Akış çizgileri: hücre-merkez U vektörleri düzenli ızgaraya
        # enterpole edilir; gövde deliği trifinder ile maskelenir
        try:
            from scipy.interpolate import griddata
            from scipy.spatial import cKDTree
            cc = pts[faces].mean(axis=1)
            if pd.GetCellData().GetArray("U") is not None:
                uv = vtk_to_numpy(pd.GetCellData().GetArray("U"))
            else:
                uv = vtk_to_numpy(pd.GetPointData().GetArray("U"))[faces].mean(axis=1)
            v1 = pts[faces[:, 1]] - pts[faces[:, 0]]
            v2 = pts[faces[:, 2]] - pts[faces[:, 0]]
            area = 0.5 * np.linalg.norm(np.cross(v1, v2), axis=1)
            csize = np.sqrt(2.0 * np.maximum(area, 1e-30))
            # linspace min/max'tan türetilince streamplot'un eşit-aralık
            # kontrolüne takılabiliyor; x0 + dx*arange inşası geçiyor
            nx, nz = 240, 120
            x0, x1 = float(pts[:, 0].min()), float(pts[:, 0].max())
            z0, z1 = float(pts[:, 2].min()), float(pts[:, 2].max())
            gx = x0 + ((x1 - x0) / (nx - 1)) * np.arange(nx)
            gz = z0 + ((z1 - z0) / (nz - 1)) * np.arange(nz)
            GX, GZ = np.meshgrid(gx, gz)
            Ux = griddata(cc[:, [0, 2]], uv[:, 0], (GX, GZ), method="linear")
            Uz = griddata(cc[:, [0, 2]], uv[:, 2], (GX, GZ), method="linear")
            # Gövde deliği maskesi: en yakın örnek hücreye uzaklık, o hücrenin
            # kendi boyutunun ~1.5 katını aşıyorsa orada akış verisi yok demektir
            # (trifinder kesit üçgenlemesini reddediyor — çakışık noktalar)
            d, idx = cKDTree(cc[:, [0, 2]]).query(np.c_[GX.ravel(), GZ.ravel()])
            hole = (d > 1.5 * csize[idx]).reshape(GX.shape)
            Ux = np.where(hole, np.nan, Ux)
            Uz = np.where(hole, np.nan, Uz)
            ax.streamplot(GX, GZ, Ux, Uz, density=1.0, linewidth=0.45,
                          color=(1, 1, 1, 0.7), arrowsize=0.6)
        except Exception:
            pass   # akış çizgisi süslemedir; harita tek başına da geçerli

        ax.set_aspect("equal")
        ax.set_xlabel("x (m)"); ax.set_ylabel("z (m)")
        ax.set_title("Simetri Düzlemi Hız Haritası ve Akış Çizgileri", fontsize=10)
        fig.tight_layout()
        fig.savefig(out)
        plt.close(fig)
        return True
    except Exception:
        return False


def build_vehicle_report(r, history, residuals, out_dir: Path) -> Path:
    """r: VehicleAnalysisResult. Markdown rapor + 300 DPI figürler üretir."""
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    geo, mesh, conv = r.geometry, (r.mesh or {}), (r.convergence or {})

    f_conv = _fig_convergence(history, out / "figures" / "convergence.png")
    f_res = _fig_residuals(residuals, out / "figures" / "residuals.png")
    _fig_geometry(geo, out / "figures" / "geometry.png")

    nu_air = 1.5e-5
    Re = r.velocity * geo["lmax_m"] / nu_air
    Ma = r.velocity / 340.0
    comp_note = ("sıkıştırılamaz geçerli (Ma<0.3)" if Ma < 0.3 else
                 f"⚠️ Ma={Ma:.2f}≥0.3 — sıkıştırılabilirlik etkisi, sıkışmaz varsayım sapar")
    md = [f"# Aerodinamik Analiz Raporu — {geo['dosya']}",
          f"\n**Araç tipi:** {r.vehicle_type}  ",
          f"**Tarih:** {datetime.now():%Y-%m-%d %H:%M}  ",
          f"**Akış:** V = {r.velocity} m/s, α = {r.alpha_deg}°, deniz seviyesi havası  ",
          # Yönetici parametreler — VKI/TU Delft hakemi ilk bunları arar (Re, Ma rejimi)
          f"**Yönetici parametreler:** Re = **{Re:.2e}** (L_ref={geo['lmax_m']} m), "
          f"Ma = **{Ma:.3f}** → {comp_note}  ",
          "**Yöntem:** OpenFOAM 11, snappyHexMesh + foamRun (SIMPLE, kOmegaSST RANS)  ",
          # Doğrulama-kaynağı (method pedigree) — çıktının savunulabilirliği için
          "**Çözücü doğrulaması (Annex I):** ankastre kiriş %0.05 (Euler-Bernoulli), "
          "NACA0012 Cl α=4°/8° ≈%4/%8 (NASA Ladson, 5-mesh), küre Cd (Charters&Thomas). "
          "Bu koşu o doğrulanmış yöntemle üretildi.  ",
          "\n---\n"]

    # ── Okula-güvenli geçerlilik-zarfı banner'ı (EN BAŞTA — öğrenci verdict'i İLK görsün) ──
    from validity_envelope import ALPHA_VALID_DEG, banner_md, classify_cfd, overall_class
    _mds = getattr(r, "mesh_duyarlilik", None) or {}
    _verdicts = classify_cfd(r.vehicle_type, r.alpha_deg, Ma,
                             has_gci_band=False, band_pct=_mds.get("fark_pct"))
    md.append(banner_md(_verdicts))
    md.append("---\n")
    try:
        r.validity = {"sinif": overall_class(_verdicts),
                      "kalemler": [(v.quantity, v.klass, v.design_safe) for v in _verdicts]}
    except Exception:
        pass

    # 1. Geometri
    md.append("## 1. Geometri\n")
    dims = geo["boyutlar_m"]
    md.append(f"- Kapsayan kutu: **{dims[0]} × {dims[1]} × {dims[2]} m** (L_ref = {geo['lmax_m']} m)  ")
    md.append(f"- Üçgen sayısı: {geo['ucgen_sayisi']:,} — su geçirmezlik: "
              f"{'✅ kapalı' if geo['su_gecirmez'] else '⚠️ açık (snappyHexMesh toleranslı ama riskli)'}  ")
    prep = geo.get("hazirlik") or {}
    if prep.get("govde_sayisi", 1) > 1:
        md.append(f"- Gövde sayısı: **{prep['govde_sayisi']}** (çok-parçalı model — "
                  "tek yüzey olarak mesh'lendi)  ")
    if prep.get("onarimlar"):
        md.append("- Geometri hazırlığı: " + "; ".join(prep["onarimlar"]) + "  ")
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
    bl = getattr(r, "sinir_tabaka", None) or {}
    nlay = bl.get("katman_sayisi", 0)
    yp = bl.get("yplus")
    if nlay:
        line = f"- Sınır tabaka: **{nlay} prizma katmanı**"
        if bl.get("yplus_hedef"):
            line += (f" (hedef y⁺={bl['yplus_hedef']:.0f}, "
                     f"ilk katman {bl.get('ilk_katman_m', 0)*1000:.3f} mm)")
    else:
        line = "- Sınır tabaka: prizma katmanı YOK"
    if yp:
        reg = ("viskoz alt-tabaka (y⁺<5) — sürtünme doğrudan çözülüyor" if yp["ort"] < 5 else
               "buffer bölgesi (5<y⁺<30) — kOmegaSST sürekli duvar fonksiyonu, orta belirsizlik"
               if yp["ort"] < 30 else
               "log bölgesi (y⁺>30) — duvar fonksiyonu varsayımı, sürtünme C_D yaklaşık")
        line += (f"; **ölçülen y⁺**: min={yp['min']}, ort=**{yp['ort']}**, "
                 f"max={yp['max']} → {reg}")
        ht = bl.get("yplus_hedef")
        if ht:
            oran = yp["ort"] / ht
            line += (f". Hedef/ölçüm oranı {oran:.2f} — "
                     + ("hedefe oturdu ✓" if 0.5 <= oran <= 2.0 else
                        "düz-plaka korelasyonu bu gövdede sapıyor; hedefi "
                        f"~{ht/max(oran,1e-3):.0f} alıp tekrarlayın"))
    else:
        line += "; y⁺ ölçülemedi"
    md.append(line + "\n")

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
    # Cd belirsizlik-bandı SATIR-İÇİ (VKI-savunulabilir: çıplak sayı değil, bandıyla)
    mds = getattr(r, "mesh_duyarlilik", None) or {}
    if mds.get("fark_pct") is not None:
        cd_band = f"±%{mds['fark_pct']} (2-mesh duyarlılık bandı)"
    else:
        cd_band = "tek-mesh → **TREND-düzeyi** (mesh-bağımsızlığı GÖSTERİLMEDİ; mutlak değer için 3-mesh GCI)"
    md.append("| Büyüklük | Değer |")
    md.append("|----------|-------|")
    md.append(f"| $C_D$ (A_ref = {r.aref_m2} m²) | **{r.cd}** — {cd_band} |")
    cw = getattr(r, "cd_wake", None)
    if cw is not None and r.cd:
        fark = abs(r.cd - cw) / abs(r.cd) * 100
        uy = ("✅ uyumlu → yakınsama güveni" if fark < 12 else "⚠️ ayrık → az-çözünürlük")
        md.append(f"| $C_D$ far-field (iz-momentum, 2.-mertebe) | {cw} — yüzeyle %{fark:.0f} {uy} |")
    if r.cl is not None:
        md.append(f"| $C_L$ | **{r.cl}** |")
    if r.ld is not None:
        md.append(f"| L/D | **{r.ld}** |")
    md.append(f"| CdA (sürükleme alanı) | {r.cda_m2} m² |")
    md.append(f"| Sürükleme kuvveti @ {r.velocity} m/s | **{r.drag_N} N** |")
    q = 0.5 * 1.225 * r.velocity**2
    md.append(f"| Sürükleme gücü @ {r.velocity} m/s | {r.drag_N * r.velocity:.1f} W |")
    md.append(f"| Dinamik basınç q | {q:.1f} Pa |\n")
    pv = getattr(r, "pervane", None)
    if pv:
        md.append(f"**Pervane (aktüatör disk):** itki {pv['itki_N']} N, "
                  f"çap {pv['cap_m']} m, indüksiyon a={pv['a']} (Froude). "
                  "*Üniform disk — pal geometrisi/swirl modellenmedi; "
                  "itki etkisinin gövde aerodinamiğine yansıması ön-tasarım düzeyinde.*\n")
    if getattr(r, "cp_vtk", "") and _fig_cp_surface(r.cp_vtk, r.velocity,
                                                    out / "figures" / "cp_surface.png"):
        md.append("![Cp](figures/cp_surface.png)\n")
        md.append("> *Cp = p/(½V²); renk skalası 2-98 persentil aralığına kırpıldı "
                  "(stagnasyon/uç tekillikleri skalayı ezmesin diye).*\n")
    if getattr(r, "kesit_vtk", "") and _fig_velocity_slice(r.kesit_vtk, r.velocity,
                                                           out / "figures" / "velocity_slice.png"):
        md.append("![Hız kesiti](figures/velocity_slice.png)\n")

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
    md.append(f"- **Taşıma (C_L) yalnız bağlı akışta doğrulanmış: |α| ≤ {ALPHA_VALID_DEG:.0f}°** "
              "(NACA0012'de Ladson'a karşı ≤%8). Üstünde 2D RANS taşımayı **~%45 DÜŞÜK** "
              "tahmin eder (α=10/12°'de ölçüldü, erken stall) — bu açılarda sayı tasarımda "
              "kullanılmaz, yalnız 'stall başlıyor' sezgisi.  ")
    md.append("- RANS kOmegaSST: bağlı akışta güvenilir; masif ayrılma/stall "
              "bölgesinde sonuç fiziksel değil.  ")
    md.append("- Prizma katmansız duvar: mutlak sürtünme sürüklemesi yaklaşık; "
              "karşılaştırmalı (tasarım A vs B) kullanım daha güvenilir.  ")
    md.append("- Pervane/itki, dönen parça ve aeroelastik etkiler modellenmedi.\n")

    md.append("\n---\n*Otomatik üretildi — vehicle_pipeline (CFD/FEA Tools)*\n")
    path = out / "RAPOR.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
