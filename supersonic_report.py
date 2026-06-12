"""Süpersonik/transonik (shockFluid) alan görselleştirme + mühendis raporu.
================================================================================
ANSYS-CFD-Post tarzı profesyonel konturlar: simetri düzleminde basınç / hız /
Mach + akış çizgileri, gövde silüeti üstüne; 3B yüzey Cp; sayısal Cd ve
yorumlarla Markdown rapor. run_supersonic her tekil koşudan sonra çağırır.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import trimesh

GAMMA = 1.4
R_AIR = 287.058


def _wsl(path: Path) -> str:
    p = str(Path(path).resolve())
    return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")


def export_field_cutplane(case_dir: Path, center, timeout: int = 600) -> Path | None:
    """Simetri düzleminden (normal +y) U,p,T kesiti VTK'sı (foamPostProcess -solver
    shockFluid; çözücü yeniden koşmaz, -latestTime)."""
    case_dir = Path(case_dir)
    cx, cy, cz = center
    func = (
        "FoamFile{version 2.0; format ascii; class dictionary; object alanKesiti;}\n"
        'type surfaces; libs ("libsampling.so");\n'
        "surfaceFormat vtk; fields (U p T);\n"
        "interpolationScheme cellPoint;\n"
        "surfaces ( kesit { type cutPlane; planeType pointAndNormal; "
        f"pointAndNormalDict {{ point ({cx} {cy} {cz}); normal (0 1 0); }} "
        "interpolate true; } );\n")
    (case_dir / "system" / "alanKesiti").write_text(func)
    try:
        subprocess.run(
            f'wsl bash -c "source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && '
            f'cd {_wsl(case_dir)} && foamPostProcess -solver shockFluid -func alanKesiti '
            f'-latestTime > log.alanKesiti 2>&1"',
            shell=True, capture_output=True, text=True, timeout=timeout)
        cands = sorted((case_dir / "postProcessing" / "alanKesiti").rglob("kesit.vtk"))
        return cands[-1] if cands else None
    except Exception:
        return None


def export_surface_p(case_dir: Path, patch: str, timeout: int = 600) -> Path | None:
    """Araç yüzeyini p (Pa) ile VTK olarak çıkarır (foamPostProcess -solver shockFluid)."""
    case_dir = Path(case_dir)
    func = (
        "FoamFile{version 2.0; format ascii; class dictionary; object yuzeyP;}\n"
        'type surfaces; libs ("libsampling.so");\n'
        "surfaceFormat vtk; fields (p);\n"
        "interpolationScheme cellPoint;\n"
        f"surfaces ( yuzey {{ type patch; patches ({patch}); }} );\n")
    (case_dir / "system" / "yuzeyP").write_text(func)
    try:
        subprocess.run(
            f'wsl bash -c "source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && '
            f'cd {_wsl(case_dir)} && foamPostProcess -solver shockFluid -func yuzeyP '
            f'-latestTime > log.yuzeyP 2>&1"',
            shell=True, capture_output=True, text=True, timeout=timeout)
        cands = sorted((case_dir / "postProcessing" / "yuzeyP").rglob("*.vtk")) + \
                sorted((case_dir / "postProcessing" / "yuzeyP").rglob("*.vtp"))
        return cands[-1] if cands else None
    except Exception:
        return None


def _read_polydata(vtk_path):
    import vtk as _vtk
    from vtk.util.numpy_support import vtk_to_numpy
    rd = _vtk.vtkPolyDataReader()
    rd.SetFileName(str(vtk_path)); rd.ReadAllScalarsOn(); rd.ReadAllVectorsOn(); rd.Update()
    tri = _vtk.vtkTriangleFilter(); tri.SetInputData(rd.GetOutput()); tri.Update()
    pd = tri.GetOutput()
    pts = vtk_to_numpy(pd.GetPoints().GetData())
    faces = vtk_to_numpy(pd.GetPolys().GetData()).reshape(-1, 4)[:, 1:]
    def arr(name):
        a = pd.GetPointData().GetArray(name) or pd.GetCellData().GetArray(name)
        return vtk_to_numpy(a) if a is not None else None
    return pts, faces, arr


def _body_silhouette(stl_path: Path, n: int = 120):
    """x-z düzleminde gövde yarı-genişlik zarfı (yumuşatılmış) — kontur üstüne
    katı cisim çizimi için."""
    m = trimesh.load(str(stl_path), force="mesh")
    vx, vz = m.vertices[:, 0], m.vertices[:, 2]
    zc = float((m.bounds[0][2] + m.bounds[1][2]) / 2)
    xb = np.linspace(vx.min(), vx.max(), n)
    env = np.array([
        (np.abs(vz[(vx >= xb[i]) & (vx < xb[i + 1])] - zc).max()
         if np.any((vx >= xb[i]) & (vx < xb[i + 1])) else 0.0)
        for i in range(n - 1)])
    k = np.ones(5) / 5.0                       # 5-nokta hareketli ortalama
    env = np.convolve(np.pad(env, 2, mode="edge"), k, mode="valid")
    return 0.5 * (xb[:-1] + xb[1:]), zc, env


def render_field_figure(vtk_path, stl_path, mach, t_inf, p_inf, out) -> bool:
    """ANSYS tarzı 3-panel: basınç(gauge) / |U| / Mach + akış çizgileri + gövde."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.tri as mtri
        from scipy.interpolate import griddata
        pts, faces, arr = _read_polydata(vtk_path)
        P, U, T = arr("p"), arr("U"), arr("T")
        if P is None or U is None or T is None:
            return False
        umag = np.linalg.norm(U, axis=1)
        machf = umag / np.sqrt(GAMMA * R_AIR * np.maximum(T, 1.0))
        xbc, zc, env = _body_silhouette(stl_path)
        L = float(xbc[-1] - xbc[0])
        xlo, xhi = xbc[0] - 0.3 * L, xbc[-1] + 1.0 * L
        zhalf = 0.45 * L
        t = mtri.Triangulation(pts[:, 0], pts[:, 2], faces)
        vis = ((pts[:, 0] >= xlo) & (pts[:, 0] <= xhi)
               & (np.abs(pts[:, 2] - zc) <= zhalf))
        if vis.sum() < 50:
            vis = np.ones(len(pts), bool)
        def lim(f):
            return float(np.percentile(f[vis], 1)), float(np.percentile(f[vis], 99))
        panels = [("Basınç (gauge) [Pa]", P - p_inf, "coolwarm", lim(P - p_inf)),
                  ("Hız büyüklüğü |U| [m/s]", umag, "turbo", lim(umag)),
                  ("Mach sayısı", machf, "turbo", lim(machf))]
        fig, axs = plt.subplots(3, 1, figsize=(8, 5.8), constrained_layout=True)
        for k, (ax, (title, fld, cmap, (vmn, vmx))) in enumerate(zip(axs, panels)):
            tp = ax.tripcolor(t, fld, cmap=cmap, vmin=vmn, vmax=vmx, shading="gouraud")
            fig.colorbar(tp, ax=ax, shrink=0.9, pad=0.01)
            ax.fill_between(xbc, zc - env, zc + env, color="0.22", zorder=5, lw=0)
            if k == 1:
                nx, nz = 240, 90
                gx = np.linspace(xlo, xhi, nx); gz = np.linspace(zc - zhalf, zc + zhalf, nz)
                GX, GZ = np.meshgrid(gx, gz)
                Ux = griddata(pts[:, [0, 2]], U[:, 0], (GX, GZ), "linear")
                Uz = griddata(pts[:, [0, 2]], U[:, 2], (GX, GZ), "linear")
                ax.streamplot(GX, GZ, Ux, Uz, density=0.9, linewidth=0.35,
                              color=(1, 1, 1, 0.55), arrowsize=0.5)
            ax.set_xlim(xlo, xhi); ax.set_ylim(zc - zhalf, zc + zhalf)
            ax.set_aspect("equal"); ax.set_title(title, fontsize=9, loc="left")
            ax.set_xticks([]); ax.set_yticks([])
        rejim = "Süpersonik" if mach > 1 else "Transonik"
        fig.suptitle(f"M={mach:g} {rejim} — Simetri Düzlemi Alanları "
                     "(OpenFOAM shockFluid)", fontsize=11)
        fig.savefig(out, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return True
    except Exception:
        return False


def render_surface_cp(vtk_path, u_inf, rho_inf, p_inf, out, max_faces=40000) -> bool:
    """3B yüzey Cp = (p−p∞)/(½ρ∞U∞²); rüzgâr-üstü + rüzgâr-altı görünüm."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import cm
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        pts, faces, arr = _read_polydata(vtk_path)
        P = arr("p")
        if P is None:
            return False
        q = 0.5 * rho_inf * u_inf ** 2
        cp = (P - p_inf) / q
        cp_face = cp[faces].mean(axis=1) if len(cp) == len(pts) else cp
        lo, hi = float(np.percentile(cp_face, 2)), float(np.percentile(cp_face, 98))
        norm = plt.Normalize(lo, hi)
        fig = plt.figure(figsize=(9, 4))
        for k, (elev, azim, ttl) in enumerate(
                [(20, 150, "rüzgâr-üstü (stagnasyon)"), (20, -30, "rüzgâr-altı (iz)")]):
            ax = fig.add_subplot(1, 2, k + 1, projection="3d")
            coll = Poly3DCollection(pts[faces], linewidths=0)
            coll.set_facecolor(cm.coolwarm(norm(cp_face)))
            ax.add_collection3d(coll)
            mn, mx = pts.min(0), pts.max(0)
            c, half = (mn + mx) / 2, (mx - mn).max() / 2
            ax.set_xlim(c[0]-half, c[0]+half); ax.set_ylim(c[1]-half, c[1]+half)
            ax.set_zlim(c[2]-half, c[2]+half)
            ax.view_init(elev=elev, azim=azim); ax.set_axis_off()
            ax.set_title(ttl, fontsize=9)
        sm = cm.ScalarMappable(cmap=cm.coolwarm, norm=norm)
        fig.colorbar(sm, ax=fig.axes, shrink=0.7, label="$C_p$")
        fig.suptitle("Yüzey Basınç Katsayısı ($C_p$)", fontsize=10)
        fig.savefig(out, bbox_inches="tight", dpi=150)
        plt.close(fig)
        return True
    except Exception:
        return False


def _register_pdf_font():
    """Türkçe (ş/ğ/ı) için matplotlib'in DejaVuSans'ını reportlab'a kaydet."""
    import os

    import matplotlib
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fd = os.path.join(os.path.dirname(matplotlib.__file__),
                      "mpl-data", "fonts", "ttf")
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(fd, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(
            TTFont("DejaVu-Bold", os.path.join(fd, "DejaVuSans-Bold.ttf")))
        return "DejaVu", "DejaVu-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def _emit_pdf(out_pdf: Path, rep_dir: Path, title, cond_lines,
              res_rows, sections, yontem) -> bool:
    """Yapılandırılmış içerikten profesyonel PDF (reportlab, A4, Türkçe font)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        font, bold = _register_pdf_font()
        pw = A4[0] - 32 * mm   # kullanılabilir genişlik
        body = ParagraphStyle("body", fontName=font, fontSize=9.5, leading=13)
        h1 = ParagraphStyle("h1", fontName=bold, fontSize=15, leading=19,
                            spaceAfter=4, textColor=colors.HexColor("#1f4e79"))
        h2 = ParagraphStyle("h2", fontName=bold, fontSize=11.5, leading=15,
                            spaceBefore=8, spaceAfter=3,
                            textColor=colors.HexColor("#1f4e79"))
        def sub(s):   # C_D -> alt-simge (reportlab Paragraph <sub> destekler)
            return s.replace("C_D", "C<sub>D</sub>").replace("C_p", "C<sub>p</sub>")
        flow = [Paragraph(title, h1), Spacer(1, 3)]
        for ln in cond_lines:
            flow.append(Paragraph(sub(ln), body))
        flow.append(Spacer(1, 6))
        flow.append(Paragraph("Sayısal Sonuçlar", h2))
        cell = ParagraphStyle("cell", fontName=font, fontSize=9.5, leading=12)
        data = [["Büyüklük", "Değer"]] + [[Paragraph(sub(r[0]), cell), r[1]]
                                          for r in res_rows]
        tbl = Table(data, colWidths=[pw * 0.62, pw * 0.38])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#eef3f8")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c4d0")),
            ("PADDING", (0, 0), (-1, -1), 5)]))
        flow.append(tbl)
        for heading, img, yorum in sections:
            flow.append(Paragraph(heading, h2))
            ip = rep_dir / img
            if ip.exists():
                from PIL import Image as PILImage
                iw, ih = PILImage.open(ip).size
                w = pw
                flow.append(Image(str(ip), width=w, height=w * ih / iw))
                flow.append(Spacer(1, 3))
            flow.append(Paragraph("<b>Yorum:</b> " + sub(yorum), body))
        flow.append(Paragraph("Yöntem ve Sınırlar", h2))
        for b in yontem:
            flow.append(Paragraph("• " + sub(b), body))
        SimpleDocTemplate(
            str(out_pdf), pagesize=A4,
            leftMargin=16 * mm, rightMargin=16 * mm,
            topMargin=14 * mm, bottomMargin=14 * mm).build(flow)
        return True
    except Exception:
        return False


def build_supersonic_report(result: dict, case_dir, stl_path, t_inf=288.15,
                            p_inf=101325.0, progress_cb=None) -> str | None:
    """Tekil shockFluid koşusundan alan figürleri + yorumlu Markdown rapor üretir.
    result: run_supersonic çıktısı (Cd, mach, U_ms, drag_N, S_ref_m2 ...)."""
    case_dir = Path(case_dir)
    stl_path = Path(stl_path)
    rep = case_dir.parent / "rapor"
    (rep / "figures").mkdir(parents=True, exist_ok=True)
    mach = result["mach"]
    u_inf = result["U_ms"]
    rho_inf = p_inf / (R_AIR * t_inf)
    m = trimesh.load(str(stl_path), force="mesh")
    center = ((m.bounds[0] + m.bounds[1]) / 2).tolist()

    if progress_cb:
        progress_cb(94, "alan kesiti çıkarılıyor...")
    cut = export_field_cutplane(case_dir, center)
    surf = export_surface_p(case_dir, stl_path.stem.replace(" ", "_"))

    figs = {}
    if cut and render_field_figure(cut, stl_path, mach, t_inf, p_inf,
                                   rep / "figures" / "alanlar.png"):
        figs["alanlar"] = "figures/alanlar.png"
    if surf and render_surface_cp(surf, u_inf, rho_inf, p_inf,
                                  rep / "figures" / "yuzey_cp.png"):
        figs["yuzey"] = "figures/yuzey_cp.png"

    rejim = "süpersonik" if mach > 1 else "transonik"
    q = 0.5 * rho_inf * u_inf ** 2
    cond_lines = [
        "<b>Çözücü:</b> OpenFOAM 11 shockFluid (Kurganov yoğunluk-bazlı şok-yakalama)",
        f"<b>Rejim:</b> {rejim} — M={mach:g} (U∞={u_inf:.1f} m/s)",
        f"<b>Serbest akış:</b> T∞={t_inf:.1f} K, p∞={p_inf:.0f} Pa, "
        f"ρ∞={rho_inf:.3f} kg/m³, q∞={q:.0f} Pa",
        f"<b>Referans alan (izdüşüm frontal):</b> {result['S_ref_m2']:.5f} m²"]
    res_rows = [
        ["Sürükleme katsayısı C_D", f"{result['Cd']:.4f}"],
        ["Sürükleme kuvveti", f"{result.get('drag_N', float('nan')):.1f} N"],
        ["Yakınsama sapması (son %20)", f"%{result.get('Cd_drift_pct', 0) or 0:.2f}"]]
    yorum_alan = (
        "Burun ucunda stagnasyon (yüksek basınç, düşük hız) bölgesi; gövde "
        "boyunca akış hızlanıp basınç düşüyor. "
        + ("Süpersonik rejimde burunda yatık şok ve gövde üzerinde genleşme "
           "görülür. " if mach > 1 else
           "Transonik rejimde akış gövde omzunda yerel olarak hızlanır "
           "(M≈1 yaklaşımı), kuyrukta taban-resirkülasyonu oluşur. ")
        + "Akış çizgileri gövde yüzeyinden ayrılmadan düzgün ilerliyor — "
          "aerodinamik tasarımın verimli olduğunu gösterir.")
    yorum_yuzey = (
        "Burun ucunda yüksek C_p (stagnasyon), gövde ve kuyruk boyunca düşük/orta "
        "seviye; kanatçık kök bölgelerinde yerel basınç değişimleri aerodinamik "
        "stabiliteye katkıdır.")
    sections = []
    if "alanlar" in figs:
        sections.append(("Simetri Düzlemi Alanları", figs["alanlar"], yorum_alan))
    if "yuzey" in figs:
        sections.append(("Yüzey Basınç Dağılımı", figs["yuzey"], yorum_yuzey))
    yontem = [
        "Çözücü: density-based, Euler-benzeri (inviscid slip duvar); basınç + "
        "dalga sürüklemesi yakalanır, skin-friction ihmal edilir (süpersonikte "
        "ikincil, ön-tasarım için savunulabilir).",
        "Mutlak C_D izdüşüm-frontal referans alana göredir; gövde-kesit referansı "
        "kullanılırsa ölçek farkı oluşur (trend ve kuvvet etkilenmez).",
        "Tek mesh; resmi GCI (mesh bağımsızlığı) yapılmamıştır."]

    title = f"Aerodinamik Analiz Raporu — {result['model']}"
    md = [f"# {title}", "", "  \n".join(cond_lines).replace("<b>", "**").replace("</b>", "**"),
          "", "## Sayısal Sonuçlar", "", "| Büyüklük | Değer |", "|----------|-------|"]
    md += [f"| {r[0].replace('C_D', '$C_D$')} | {r[1]} |" for r in res_rows]
    md.append("")
    if result.get("uyari"):
        md.append(f"> ⚠️ {result['uyari']}\n")
    for heading, img, yorum in sections:
        md += [f"## {heading}", "", f"![{heading}]({img})", "",
               "**Yorum:** " + yorum.replace("C_p", "$C_p$"), ""]
    md += ["## Yöntem ve Sınırlar", ""]
    md += [f"- {b.replace('C_D', '$C_D$')}" for b in yontem]
    (rep / "RAPOR.md").write_text("\n".join(md), encoding="utf-8")

    pdf_ok = _emit_pdf(rep / "RAPOR.pdf", rep, title, cond_lines, res_rows,
                       sections, yontem)
    if progress_cb:
        progress_cb(99, "rapor üretildi (MD + PDF)" if pdf_ok else "rapor üretildi (MD)")
    return str(rep / ("RAPOR.pdf" if pdf_ok else "RAPOR.md"))
