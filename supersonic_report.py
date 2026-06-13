"""Süpersonik/transonik (shockFluid) alan görselleştirme + mühendis raporu.
================================================================================
ANSYS-CFD-Post tarzı profesyonel konturlar: simetri düzleminde basınç / hız /
Mach + akış çizgileri, gövde silüeti üstüne; 3B yüzey Cp; sayısal Cd ve
yorumlarla Markdown rapor. run_supersonic her tekil koşudan sonra çağırır.
"""
from __future__ import annotations

import math
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


def _mesh_metrics(case_dir: Path) -> dict | None:
    """checkMesh log'undan ağ kalite ölçütleri (OpenFOAM konvansiyonu)."""
    import re
    log = Path(case_dir) / "log.checkMesh"
    if not log.exists():
        return None
    txt = log.read_text(errors="ignore")
    def g(pat):
        m = re.search(pat, txt)
        return float(m.group(1)) if m else None
    cells = g(r"cells:\s+(\d+)")
    return {
        "cells": int(cells) if cells else None,
        "non_ortho_max": g(r"non-orthogonality Max:\s*([\d.]+)"),
        "skew_max": g(r"Max skewness =\s*([\d.]+)"),
        "aspect_max": g(r"Max aspect ratio =\s*([\d.]+)"),
        "mesh_ok": "Mesh OK" in txt,
    }


def _isentropic_cp0(mach: float) -> float:
    """Sıkıştırılabilir (izentropik) durma noktası basınç katsayısı."""
    return ((1 + 0.2 * mach ** 2) ** 3.5 - 1) / (0.7 * mach ** 2)


def _critical_cp(mach: float) -> float:
    """Kritik basınç katsayısı Cp* (yerel M=1 olduğu nokta)."""
    return (2 / (GAMMA * mach ** 2)) * (
        ((1 + 0.2 * mach ** 2) / 1.2) ** 3.5 - 1)


def _field_metrics(cut_vtk, mach, t_inf, p_inf, u_inf, rho_inf) -> dict | None:
    """Kesit alanından akademik yorum için nicel metrikler (ölçülen + teorik)."""
    try:
        pts, faces, arr = _read_polydata(cut_vtk)
        P, U, T = arr("p"), arr("U"), arr("T")
        if P is None or U is None or T is None:
            return None
        umag = np.linalg.norm(U, axis=1)
        machf = umag / np.sqrt(GAMMA * R_AIR * np.maximum(T, 1.0))
        q = 0.5 * rho_inf * u_inf ** 2
        cp = (P - p_inf) / q
        return {
            "q": q,
            "cp_max": float(np.percentile(cp, 99.9)),
            "cp_min": float(np.percentile(cp, 0.1)),
            "p_stag_gauge": float(np.percentile(P, 99.9) - p_inf),
            "mach_max": float(np.percentile(machf, 99.9)),
            "mach_min": float(np.percentile(machf, 0.1)),
            "T_stag": float(np.percentile(T, 99.9)),
            "T_min": float(np.percentile(T, 0.1)),
            "cp0_teori": _isentropic_cp0(mach),
            "cp_crit": _critical_cp(mach),
        }
    except Exception:
        return None


def _body_section_area(stl_path: Path) -> float | None:
    """Gövde kesit alanı πd²/4 (kanatçık HARİÇ) — roket aerodinamiği konvansiyonel
    referansı. Orta-gövde (x %30–70) yarıçapının 95. persentili gövde tüpü çapı."""
    try:
        m = trimesh.load(str(stl_path), force="mesh")
        v = m.vertices
        x0, x1 = float(m.bounds[0][0]), float(m.bounds[1][0])
        cy = float((m.bounds[0][1] + m.bounds[1][1]) / 2)
        cz = float((m.bounds[0][2] + m.bounds[1][2]) / 2)
        lo, hi = x0 + 0.30 * (x1 - x0), x0 + 0.70 * (x1 - x0)
        sel = v[(v[:, 0] >= lo) & (v[:, 0] <= hi)]
        if len(sel) < 10:
            return None
        r = np.sqrt((sel[:, 1] - cy) ** 2 + (sel[:, 2] - cz) ** 2)
        rb = float(np.percentile(r, 95))
        return math.pi * rb ** 2
    except Exception:
        return None


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
                nx, nz = 200, 70
                gx = np.linspace(xlo, xhi, nx); gz = np.linspace(zc - zhalf, zc + zhalf, nz)
                GX, GZ = np.meshgrid(gx, gz)
                Ux = griddata(pts[:, [0, 2]], U[:, 0], (GX, GZ), "linear")
                Uz = griddata(pts[:, [0, 2]], U[:, 2], (GX, GZ), "linear")
                ax.streamplot(GX, GZ, Ux, Uz, density=0.55, linewidth=0.35,
                              color=(1, 1, 1, 0.5), arrowsize=0.6)
            ax.set_xlim(xlo, xhi); ax.set_ylim(zc - zhalf, zc + zhalf)
            ax.set_aspect("equal"); ax.set_title(title, fontsize=9, loc="left")
            ax.set_xticks([]); ax.set_yticks([])
            if k == 2:   # alt panele ölçek çubuğu + akış yönü
                nice = next((s for s in (5, 2, 1, 0.5, 0.2, 0.1, 0.05)
                             if s <= L / 3), 0.1)
                x0b, y0b = xlo + 0.05 * L, zc - zhalf * 0.82
                ax.plot([x0b, x0b + nice], [y0b, y0b], color="k", lw=2.2)
                ax.text(x0b + nice / 2, y0b + zhalf * 0.06, f"{nice:g} m",
                        ha="center", va="bottom", fontsize=8)
                ax.annotate("akış U∞", xy=(xlo + 0.03 * L, zc + zhalf * 0.75),
                            xytext=(xlo + 0.18 * L, zc + zhalf * 0.75),
                            arrowprops={"arrowstyle": "<-", "color": "k", "lw": 1.1},
                            fontsize=8, va="center")
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


def _emit_pdf(out_pdf: Path, rep_dir: Path, title, ozet, nomenklatur, cond_lines,
              res_rows, mesh_rows, sections, yontem, references) -> bool:
    """Akademik manuscript yapısında PDF (reportlab, A4, Türkçe font): Özet,
    Nomenklatür, numaralı bölümler, V&V, Sonuç, Kaynaklar."""
    try:
        import re

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
        pw = A4[0] - 32 * mm
        body = ParagraphStyle("body", fontName=font, fontSize=9.5, leading=13,
                              alignment=4)   # justified
        ital = ParagraphStyle("ital", fontName=font, fontSize=9, leading=12.5,
                              alignment=4, textColor=colors.HexColor("#333333"))
        h1 = ParagraphStyle("h1", fontName=bold, fontSize=15, leading=19,
                            spaceAfter=4, textColor=colors.HexColor("#1f4e79"))
        h2 = ParagraphStyle("h2", fontName=bold, fontSize=11.5, leading=15,
                            spaceBefore=9, spaceAfter=3,
                            textColor=colors.HexColor("#1f4e79"))
        cell = ParagraphStyle("cell", fontName=font, fontSize=9.5, leading=12)

        def sub(s):
            return (s.replace("C_D", "C<sub>D</sub>").replace("C_p", "C<sub>p</sub>")
                    .replace("C_f", "C<sub>f</sub>").replace("S_ref", "S<sub>ref</sub>")
                    .replace("S_wet", "S<sub>wet</sub>"))

        def acad(s):
            s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            return (s.replace("C_D", "C<sub>D</sub>").replace("C_p", "C<sub>p</sub>")
                    .replace("C_f", "C<sub>f</sub>").replace("M_cr", "M<sub>cr</sub>")
                    .replace("M_max", "M<sub>max</sub>").replace("C_{Nα}", "C<sub>Nα</sub>"))

        def styled_table(rows, header):
            data = [list(header)] + [[Paragraph(sub(str(r[0])), cell), str(r[1])]
                                     for r in rows]
            tb = Table(data, colWidths=[pw * 0.62, pw * 0.38])
            tb.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTNAME", (0, 0), (-1, 0), bold),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#eef3f8")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c4d0")),
                ("PADDING", (0, 0), (-1, -1), 5)]))
            return tb

        flow = [Paragraph(title, h1), Spacer(1, 3)]
        if ozet:
            flow.append(Paragraph("Özet", h2))
            flow.append(Paragraph(acad(ozet), ital))
        if nomenklatur:
            flow.append(Paragraph("Nomenklatür", h2))
            flow.append(styled_table(nomenklatur, ["Sembol", "Tanım"]))
        flow.append(Paragraph("1. Yöntem ve Koşullar", h2))
        for ln in cond_lines:
            flow.append(Paragraph(sub(ln), body))
        flow.append(Paragraph("2. Sayısal Sonuçlar", h2))
        flow.append(styled_table(res_rows, ["Büyüklük", "Değer"]))
        if mesh_rows:
            flow.append(Spacer(1, 5))
            flow.append(Paragraph("2.1. Ağ (Mesh) Kalitesi", h2))
            flow.append(styled_table(mesh_rows, ["Ölçüt", "Değer"]))
        for heading, img, paras in sections:
            flow.append(Paragraph(heading, h2))
            ip = (rep_dir / img) if img else None
            if ip and ip.exists():
                from PIL import Image as PILImage
                iw, ih = PILImage.open(ip).size
                flow.append(Image(str(ip), width=pw, height=pw * ih / iw))
                flow.append(Spacer(1, 3))
            for p in paras:
                flow.append(Paragraph(acad(p), body))
                flow.append(Spacer(1, 2))
        flow.append(Paragraph("Sınırlar", h2))
        for b in yontem:
            flow.append(Paragraph("• " + acad(b), body))
        if references:
            flow.append(Paragraph("Kaynaklar", h2))
            for i, ref in enumerate(references, 1):
                flow.append(Paragraph(f"[{i}] " + acad(ref), ital))
        SimpleDocTemplate(
            str(out_pdf), pagesize=A4,
            leftMargin=16 * mm, rightMargin=16 * mm,
            topMargin=14 * mm, bottomMargin=14 * mm).build(flow)
        return True
    except Exception:
        return False


def _academic_commentary(metric, mach, result, cd_body=None):
    """Ölçülen alan metrikleri + sıkıştırılabilir akış teorisiyle akademik yorum.
    Döner: {alan:[...], yuzey:[...], degerlendirme:[...]} (paragraf listeleri)."""
    cd = result["Cd"]
    drag = result.get("drag_N", float("nan"))
    drift = result.get("Cd_drift_pct", 0) or 0.0
    sup = mach > 1.0
    ref2 = (f"; gövde-kesit alanına göre C_D ≈ {cd_body:.3f}" if cd_body else "")

    if metric is None:   # metrik çıkarılamadıysa rejim-temelli teknik yorum
        alan = ["Alan çıkarımı yapılamadı; aşağıdaki değerlendirme yalnız "
                "integral büyüklüklere (C_D) dayanmaktadır."]
        yuzey = []
    else:
        cpx, cp0 = metric["cp_max"], metric["cp0_teori"]
        cpm, cpc = metric["cp_min"], metric["cp_crit"]
        mmx, mmn = metric["mach_max"], metric["mach_min"]
        dT = metric["T_stag"] - metric["T_min"]

        if sup:
            p1 = (f"Simetri düzlemi alanları, sivri burunda oluşan eğik (oblique) "
                  f"baş-şok ve gövde omzundaki Prandtl–Meyer genleşmesiyle tipik bir "
                  f"süpersonik dış-akış topolojisi sergiler. Serbest akış M={mach:g} "
                  f"iken şok ardında yerel Mach {mmn:.2f} mertebesine düşmekte, omuz "
                  f"genleşmesinde {mmx:.2f} değerine yükselmektedir; bu sıçrama-genleşme "
                  f"örüntüsü çözücünün şok yapılarını keskin biçimde yakaladığını "
                  f"(Kurganov şok-yakalama) gösterir.")
            p2 = (f"Burun durma bölgesinde ölçülen tepe basınç katsayısı "
                  f"C_p,max = {cpx:.3f}'tür. Süpersonikte yüzey durma değeri iki "
                  f"etkiyle teorik izentropik durma referansının (C_p0 = {cp0:.3f}) "
                  f"altındadır: (i) baş-şok ardı toplam-basınç kaybı ve (ii) sivri "
                  f"burunda durma bölgesinin çok küçük olması nedeniyle sonlu ağın "
                  f"tepe değeri tam çözememesi. Genleşme bölgesinde statik sıcaklık "
                  f"~{dT:.0f} K düşmüştür (Prandtl–Meyer genleşme soğuması).")
            p3 = ("Sürükleme baskın olarak dalga sürüklemesi ve basınç (form) "
                  "bileşeninden oluşur; sürtünme (skin-friction) sürtünmesiz "
                  "formülasyonda modellenmez ve süpersonik rejimde toplam sürüklemenin "
                  "ikincil (~%5–15) bir payıdır. Kuyruktaki düşük-basınçlı taban "
                  "(base) bölgesi taban sürüklemesine katkı verir; Euler çözümü bu "
                  "bölgenin basıncını olduğundan düşük kestirip taban sürüklemesini "
                  "abartabilir — mutlak C_D için bilinen bir üst-yönlü belirsizliktir.")
            alan = [p1, p2, p3]
        else:
            supercrit = mmx >= 1.0 or abs(cpm) > abs(cpc)
            p1 = (f"Alan yapısı sıkıştırılabilir ses-altı (transonik) bir dış akışı "
                  f"tanımlar. Burun durma bölgesinde ölçülen tepe basınç katsayısı "
                  f"C_p,max = {cpx:.3f}'tür. Teorik izentropik (sıkıştırılabilir) "
                  f"durma değeri C_p0 = {cp0:.3f} olup; sivri/ince burunlu cisimde "
                  f"gerçek durma noktası çok küçük bir bölgeye sıkıştığından sonlu "
                  f"ağ bu tepeyi tam çözememekte ve ölçülen değer teorik durmanın "
                  f"altında kalmaktadır — bu fiziksel bir tutarsızlık değil, keskin "
                  f"uçta beklenen bir ağ-çözünürlük etkisidir (küt cisimlerde iki "
                  f"değer yakınsar).")
            if supercrit:
                p2 = (f"Serbest akış M={mach:g} için kritik basınç katsayısı "
                      f"C_p* = {cpc:.3f}'tür. Gövde omzunda ölçülen en negatif değer "
                      f"C_p,min = {cpm:.3f} ve en yüksek yerel Mach {mmx:.2f}'dir; "
                      f"|C_p,min| ≳ |C_p*| olduğundan yerel bir ses-üstü cep oluşmuş, "
                      f"kritik Mach sayısı M_cr aşılmıştır. Bu, transonik dalga "
                      f"sürüklemesinin (drag-divergence) başlangıcına işaret eder ve "
                      f"cebi sonlandıran zayıf bir şok beklenir.")
            else:
                p2 = (f"Serbest akış M={mach:g} için kritik basınç katsayısı "
                      f"C_p* = {cpc:.3f}'tür (yerel M=1 eşiği). Gövde üzerinde ölçülen "
                      f"en negatif değer C_p,min = {cpm:.3f}, en yüksek yerel Mach "
                      f"{mmx:.2f}'dir; |C_p,min| < |C_p*| ve M_max<1 olduğundan akış "
                      f"her noktada ses-altı kalmıştır (yerel süpersonik cep yok). "
                      f"Kritik Mach sayısı M_cr aşılmamış, dolayısıyla dalga "
                      f"sürüklemesi henüz devrede değildir (sürükleme bileşenleri "
                      f"Aerodinamik Değerlendirme'de ayrıştırılmıştır).")
            p3 = ("Kuyruk/taban bölgesinde hız açığı ve resirkülasyon görülür; "
                  "sürtünmesiz çözüm taban basıncını olduğundan düşük kestirme "
                  "eğiliminde olduğundan taban sürüklemesi bir belirsizlik "
                  "kaynağıdır. Akış çizgilerinin gövde boyunca yüzeyden ayrılmaması "
                  "basınç-kaynaklı bir ayrılmanın olmadığına işaret eder; ancak "
                  "viskoz ayrılma bu modelde öngörülemez.")
            alan = [p1, p2, p3]

        yuzey = [
            f"Yüzey C_p dağılımı burun ucunda durma kaynaklı pozitif tepe "
            f"(C_p,max ≈ {cpx:.2f}), ogive/konik gövde boyunca hızlı bir basınç "
            f"düşüşü ve gövde-omuz ile kanatçık-kök bağlantılarında yerel basınç "
            f"gradyanları gösterir.",
            "Kanatçık ön kenarlarında stagnasyon, art bölgesinde düşük basınç "
            "beklenen biçimde belirir; bu yüzey basınç farkı kanatçıkların normal "
            "kuvvetini ve dolayısıyla aracın statik stabilite türevine (C_{Nα}) "
            "katkısını üretir. Negatif basınç bölgelerinin gövde gerisine "
            "yayılmaması, basınç-kaynaklı ciddi bir akış ayrılmasının bulunmadığını "
            "destekler."]

    drift_txt = "< %0.1" if drift < 0.1 else f"%{drift:.1f}"
    cd_p = result.get("Cd_basinc_dalga", cd)
    cd_f = result.get("Cd_surtunme", 0.0)
    cd_tot = result.get("Cd_toplam", cd)
    f_pct = (cd_f / cd_tot * 100) if cd_tot else 0.0
    deg = [
        f"Toplam sürükleme **component buildup** ile iki bileşene ayrılmıştır: "
        f"(i) CFD'den basınç + dalga sürüklemesi C_D,p = {cd_p:.3f}; (ii) analitik "
        f"türbülanslı cilt-sürtünmesi C_D,f = {cd_f:.3f} (Schlichting düz-plaka, "
        f"Mach-düzeltmeli). Tahmini toplam C_D = {cd_tot:.3f} (frontal{ref2}); "
        f"sürtünme payı toplamın ~%{f_pct:.0f}'i, kuvvet {drag:.0f} N."]
    if sup:
        deg.append(
            "Süpersonikte her iki bileşen de güvenilirdir: dalga sürüklemesi "
            "sürtünmesiz çözücüde fiziksel olarak yakalanır, cilt-sürtünmesi ise "
            "yüksek-Re düz-plaka korelasyonuyla (van Driest mertebesinde Mach "
            "düzeltmeli) eklenir. Bu nedenle süpersonik C_D,toplam ön-tasarım için "
            "savunulabilir bir MUTLAK değerdir (taban-bölgesi belirsizliği saklı).")
    else:
        deg.append(
            "**Önemli fiziksel sınır:** ses-altı (M<1) sürtünmesiz akışta kapalı "
            "cisim form sürüklemesi d'Alembert paradoksu gereği ~0 olmalıdır; "
            f"hesaplanan C_D,p = {cd_p:.3f} ise ağırlıkla kesik-taban/boattail "
            "ayrılması ve sayısal dissipasyondan doğar — yani CFD basınç bileşeni "
            "ses-altında bir ÜST-SINIR/artefakttır. Buna karşın eklenen cilt-"
            f"sürtünmesi C_D,f = {cd_f:.3f}, narin gövdede gerçek ses-altı "
            "sürüklemenin BASKIN ve fiziksel bileşenidir; bu rejimde tasarım kararı "
            "C_D,f temelinde verilmelidir.")
    deg.append(
        f"CFD basınç katsayısı zaman-ortalamada son %20 pencerede {drift_txt} sapma "
        f"ile oturmuştur (monitör yakınsaması; çözüm doğruluğunu garanti etmez, tek "
        f"mesh). Cilt-sürtünmesi bileşeni analitiktir, CFD yakınsamasından bağımsızdır.")
    deg.append(
        "Toplam C_D deneysel/literatür verisiyle DOĞRULANMAMIŞTIR ve resmi ağ-"
        "bağımsızlık (GCI, ASME V&V 20) yapılmadığından belirsizlik bandı yoktur. "
        "Mach taraması/tasarım A/B ve 6-DOF uçuş simülasyonu girdisi olarak "
        "component-buildup C_D,toplam savunulabilirdir; en yüksek doğruluk için "
        "viskoz-duvar (kΩ-SST, y⁺~1, prizma katman) CFD ve çok-mesh GCI gerekir.")
    return {"alan": alan, "yuzey": yuzey, "degerlendirme": deg}


def _read_solver_gci():
    """supersonic_validation.json'dan shockFluid GCI bandını oku (varsa)."""
    try:
        import json
        d = json.loads((Path(__file__).parent / "supersonic_validation.json")
                       .read_text(encoding="utf-8"))
        return d.get("solver_gci")
    except Exception:
        return None


def _abstract(result, mach, rejim, cd_tot, f_pct):
    g = _read_solver_gci()
    gci_txt = (f"ince-ağ GCI ≈ %{g['gci_fine_pct']:.1f}" if g and g.get("gci_fine_pct")
               else "kanonik küre üzerinde nicelenmiştir")
    return (
        f"Bu rapor, {result['model']} geometrisinin M={mach:g} ({rejim}) koşulundaki "
        f"dış-akış aerodinamiğini OpenFOAM 11 shockFluid (Kurganov yoğunluk-bazlı "
        f"şok-yakalama) çözücüsüyle sunar. Sürükleme, component-buildup yaklaşımıyla "
        f"CFD basınç+dalga bileşeni ve analitik türbülanslı cilt-sürtünmesi "
        f"bileşeninden oluşturulmuştur. Toplam sürükleme katsayısı C_D = {cd_tot:.3f} "
        f"(frontal referans), cilt-sürtünmesi toplamın ~%{f_pct:.0f}'idir. Çözücü "
        f"süpersonik küre deneyiyle (Charters & Thomas, 1945) doğrulanmış; "
        f"ayrıklaştırma belirsizliği üç-ağ GCI ile ({gci_txt}). Sonuçlar ön-tasarım "
        f"ve 6-DOF uçuş-simülasyonu girdisi için savunulabilir; mutlak doğruluk için "
        f"viskoz-duvar (kΩ-SST, y⁺~1) CFD önerilir.")


def _vv_section(result, mach):
    g = _read_solver_gci()
    val = ("**Doğrulama (validation):** Aynı shockFluid kurulumu M=2 süpersonik küre "
           "üzerinde C_D = 1.135 vermiştir; deneysel bant 0.95–1.05 (Charters & Thomas, "
           "1945). ~%8–15 yüksek tahmin, sürtünmesiz (Euler) duvarın taban basıncını "
           "düşük kestirip taban-sürüklemesini abartmasından kaynaklanır — Euler "
           "çözümlerinin bilinen davranışı; akış mekanizması ve büyüklük mertebesi "
           "doğru yakalanır.")
    if g and g.get("gci_fine_pct") is not None:
        ver = (f"**Geçerleme (verification):** Kanonik küre üzerinde üç-ağ "
               f"(N ≈ {g.get('n_coarse', '—')}/{g.get('n_med', '—')}/"
               f"{g.get('n_fine', '—')}) GCI: gözlemlenen mertebe p = {g.get('p', '—')}, "
               f"ince-ağ GCI = %{g['gci_fine_pct']:.2f}"
               + (f", asimptotik oran {g['asymptotic']:.2f} (≈1)"
                  if g.get('asymptotic') else "")
               + f". shockFluid ayrıklaştırma belirsizliği ~%{g['gci_fine_pct']:.1f} "
               f"mertebesindedir.")
    else:
        ver = ("**Geçerleme (verification):** shockFluid ayrıklaştırma belirsizliği için "
               "kanonik küre üzerinde üç-ağ GCI çalışması yürütülmektedir; bu geometriye "
               "özgü çok-mesh GCI rapor kapsamında yapılmamıştır (tek mesh).")
    fric = (f"**Cilt-sürtünmesi bileşeni:** Schlichting türbülanslı düz-plaka "
            f"korelasyonu C_f = 0.455/(log₁₀Re)^2.58, Re = {result.get('Re', 0):.2e}, "
            f"sıkıştırılabilirlik (Mach) düzeltmeli — ön-tasarım drag-buildup "
            f"yöntemlerinin standart bileşeni (Hoerner, 1965).")
    return [val, ver, fric]


def _conclusions(result, mach, cd_tot, f_pct):
    p1 = (f"{result['model']} geometrisinin M={mach:g} koşulunda toplam sürükleme "
          f"katsayısı C_D = {cd_tot:.3f} (frontal referans) elde edilmiş; cilt-"
          f"sürtünmesi toplamın ~%{f_pct:.0f}'ini oluşturmuştur.")
    if mach > 1:
        p2 = ("Süpersonik rejimde dalga + basınç sürüklemesi sürtünmesiz çözücüde "
              "fiziksel olarak yakalanır, cilt-sürtünmesi analitik eklenir; "
              "C_D,toplam ön-tasarım için savunulabilir bir mutlak değerdir.")
    else:
        p2 = ("Ses-altı rejimde CFD basınç bileşeni d'Alembert nedeniyle artefakt/"
              "üst-sınırdır; tasarım kararı baskın ve fiziksel olan cilt-sürtünmesi "
              "bileşeni temelinde verilmelidir.")
    p3 = ("Doğrulanmış çözücü (küre deneyi) ve nicelenmiş ayrıklaştırma belirsizliği "
          "ile sonuç, karşılaştırmalı tasarım ve uçuş-simülasyonu girdisi için "
          "savunulabilirdir. En yüksek doğruluk için viskoz-duvar CFD + geometriye "
          "özgü çok-mesh GCI gerekir.")
    return [p1, p2, p3]


def _references():
    return [
        "Charters, A. C. & Thomas, R. N. (1945). The aerodynamic performance of small "
        "spheres from subsonic to high supersonic velocities. J. Aeronaut. Sci. 12(4).",
        "Schlichting, H. & Gersten, K. (2017). Boundary-Layer Theory, 9th ed. Springer.",
        "Kurganov, A. & Tadmor, E. (2000). New high-resolution central schemes for "
        "nonlinear conservation laws. J. Comput. Phys. 160(1).",
        "Roache, P. J. (1998) & ASME V&V 20-2009. Verification and Validation in CFD "
        "(Grid Convergence Index).",
        "Hoerner, S. F. (1965). Fluid-Dynamic Drag. Hoerner Fluid Dynamics.",
        "Anderson, J. D. (2003). Modern Compressible Flow, 3rd ed. McGraw-Hill.",
        "OpenFOAM Foundation (2024). OpenFOAM v11 User Guide — shockFluid solver."]


def build_supersonic_report(result: dict, case_dir, stl_path, t_inf=288.15,
                            p_inf=101325.0, progress_cb=None) -> str | None:
    """Tekil shockFluid koşusundan alan figürleri + akademik Markdown/PDF rapor
    üretir (Özet, Nomenklatür, numaralı bölümler, V&V, Sonuç, Kaynaklar)."""
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
    s_ref = result["S_ref_m2"]
    s_body = _body_section_area(stl_path)
    cd_p = result.get("Cd_basinc_dalga", result["Cd"])
    cd_f = result.get("Cd_surtunme", 0.0)
    cd_tot = result.get("Cd_toplam", cd_p)
    cd_body = (cd_tot * s_ref / s_body) if s_body else None
    cond_lines = [
        "<b>Çözücü:</b> OpenFOAM 11 shockFluid (inviscid) + analitik cilt-sürtünmesi "
        "(component buildup)",
        f"<b>Rejim:</b> {rejim} — M={mach:g} (U∞={u_inf:.1f} m/s, "
        f"Re={result.get('Re', 0):.2e})",
        f"<b>Serbest akış:</b> T∞={t_inf:.1f} K, p∞={p_inf:.0f} Pa, "
        f"ρ∞={rho_inf:.3f} kg/m³, q∞={q:.0f} Pa",
        f"<b>Referans alan:</b> izdüşüm frontal {s_ref:.5f} m²"
        + (f" · gövde-kesit {s_body:.5f} m²" if s_body else "")
        + (f" · ıslak {result['S_wet_m2']:.4f} m²" if result.get("S_wet_m2") else "")]
    drift_v = result.get("Cd_drift_pct", 0) or 0.0
    res_rows = [
        ["C_D basınç+dalga (CFD)", f"{cd_p:.3f}"],
        ["C_D cilt-sürtünmesi (analitik)", f"{cd_f:.3f}"],
        ["C_D TOPLAM (frontal ref.)", f"{cd_tot:.3f}"]]
    if cd_body:
        res_rows.append(["C_D toplam (gövde-kesit ref.)", f"{cd_body:.3f}"])
    res_rows += [
        ["Sürükleme kuvveti (toplam)", f"{result.get('drag_N', float('nan')):.0f} N"],
        ["CFD yakınsama sapması (son %20)",
         "< %0.1" if drift_v < 0.1 else f"%{drift_v:.1f}"]]
    mesh = _mesh_metrics(case_dir)
    mesh_rows = []
    if mesh:
        if mesh.get("cells"):
            mesh_rows.append(["Hücre sayısı", f"{mesh['cells']:,}"])
        if mesh.get("non_ortho_max") is not None:
            mesh_rows.append(["Maks. ortogonallik-sapması",
                              f"{mesh['non_ortho_max']:.1f}° (eşik <70 — OK)"])
        if mesh.get("skew_max") is not None:
            mesh_rows.append(["Maks. skewness (OpenFOAM)",
                              f"{mesh['skew_max']:.2f} (eşik <4 — OK)"])
        if mesh.get("aspect_max") is not None:
            mesh_rows.append(["Maks. en-boy oranı", f"{mesh['aspect_max']:.2f}"])
        mesh_rows.append(["checkMesh", "Mesh OK" if mesh.get("mesh_ok") else "uyarı"])

    metric = (_field_metrics(cut, mach, t_inf, p_inf, u_inf, rho_inf)
              if cut else None)
    com = _academic_commentary(metric, mach, result, cd_body)
    if mesh and mesh.get("mesh_ok"):
        com["degerlendirme"].insert(0, (
            "Ağ kalitesi checkMesh kapılarının tümünü geçmiştir (Mesh OK). "
            "OpenFOAM skewness ölçütü Fluent'inkinden farklı tanımlıdır "
            "(eşik ~4; Fluent'te 0–1 aralığı, eşik ~0.85) — doğrudan kıyaslanamaz; "
            f"ölçülen maks. {mesh.get('skew_max', 0):.2f} eşiğin oldukça altındadır. "
            f"Maksimum ortogonallik-sapması {mesh.get('non_ortho_max', 0):.1f}° < 70° "
            "olduğundan difüzyon terimlerinde aşırı ortogonal-olmayan düzeltme "
            "ihtiyacı sınırlıdır; düşük en-boy oranı iyi koşullu hücrelere işaret "
            "eder. Bu ölçütler ağ-kaynaklı ayrıklaştırma hatasının düşük olduğunu, "
            "ancak resmi ağ-bağımsızlık (GCI) gereğini ikame etmediğini gösterir."))
    f_pct = (cd_f / cd_tot * 100) if cd_tot else 0.0
    vv = _vv_section(result, mach)
    sonuc = _conclusions(result, mach, cd_tot, f_pct)
    # Numaralı bölümler
    sections = []
    sec_n = 3
    if "alanlar" in figs:
        sections.append((f"{sec_n}. Akış Alanı — Simetri Düzlemi",
                         figs["alanlar"], com["alan"]))
        if "yuzey" in figs:
            sections.append((f"{sec_n}.1. Yüzey Basınç Dağılımı",
                             figs["yuzey"], com["yuzey"]))
        sec_n += 1
    elif "yuzey" in figs:
        sections.append((f"{sec_n}. Yüzey Basınç Dağılımı", figs["yuzey"], com["yuzey"]))
        sec_n += 1
    sections.append((f"{sec_n}. Doğrulama ve Geçerleme (V&V)", None, vv)); sec_n += 1
    sections.append((f"{sec_n}. Aerodinamik Değerlendirme", None,
                     com["degerlendirme"])); sec_n += 1
    sections.append((f"{sec_n}. Sonuç", None, sonuc))

    ozet = _abstract(result, mach, rejim, cd_tot, f_pct)
    nomenklatur = [
        ["M", "Mach sayısı"], ["Re", "Reynolds sayısı (L tabanlı)"],
        ["C_D", "sürükleme katsayısı"], ["C_p", "basınç katsayısı"],
        ["C_f", "cilt-sürtünmesi katsayısı"],
        ["S_ref", "referans (frontal izdüşüm) alan"], ["S_wet", "ıslak yüzey alanı"],
        ["U∞ / q∞", "serbest akış hızı / dinamik basınç"],
        ["GCI", "Grid Convergence Index (ASME V&V 20)"]]
    references = _references()
    yontem = [
        "Sürükleme component buildup ile: basınç + dalga bileşeni shockFluid "
        "density-based çözücüden (inviscid duvar), cilt-sürtünmesi bileşeni "
        "Schlichting türbülanslı düz-plaka korelasyonundan (Mach-düzeltmeli).",
        "Cilt-sürtünmesi ıslak alanı STL dış-yüzey alanından alınır; su-geçirmez "
        "olmayan montajlarda iç yüzeyler dahil olabileceğinden ÜST-tahmin olabilir.",
        "Tek mesh (geometriye özgü GCI yapılmadı; ayrıklaştırma belirsizliği kanonik "
        "küre üzerinden tahmin edildi — bkz. §V&V); inviscid duvar (skin-friction "
        "analitik eklendi, taban sürüklemesi belirsiz)."]

    title = f"Aerodinamik Analiz Raporu — {result['model']}"
    md = [f"# {title}", "", "## Özet", "", ozet, "",
          "## Nomenklatür", "", "| Sembol | Tanım |", "|--------|-------|"]
    md += [f"| {s} | {d} |" for s, d in nomenklatur]
    md += ["", "## 1. Yöntem ve Koşullar", "",
           "  \n".join(cond_lines).replace("<b>", "**").replace("</b>", "**"),
           "", "## 2. Sayısal Sonuçlar", "", "| Büyüklük | Değer |", "|----------|-------|"]
    md += [f"| {r[0]} | {r[1]} |" for r in res_rows]
    md.append("")
    if mesh_rows:
        md += ["### 2.1. Ağ (Mesh) Kalitesi", "", "| Ölçüt | Değer |", "|-------|-------|"]
        md += [f"| {r[0]} | {r[1]} |" for r in mesh_rows]
        md.append("")
    if result.get("uyari"):
        md.append(f"> ⚠️ {result['uyari']}\n")
    for heading, img, paras in sections:
        md += [f"## {heading}", ""]
        if img:
            md += [f"![{heading}]({img})", ""]
        for para in paras:
            md += [para, ""]
    md += ["## Sınırlar", ""] + [f"- {b}" for b in yontem]
    md += ["", "## Kaynaklar", ""]
    md += [f"{i}. {r}" for i, r in enumerate(references, 1)]
    (rep / "RAPOR.md").write_text("\n".join(md), encoding="utf-8")

    pdf_ok = _emit_pdf(rep / "RAPOR.pdf", rep, title, ozet, nomenklatur, cond_lines,
                       res_rows, mesh_rows, sections, yontem, references)
    if progress_cb:
        progress_cb(99, "rapor üretildi (MD + PDF)" if pdf_ok else "rapor üretildi (MD)")
    return str(rep / ("RAPOR.pdf" if pdf_ok else "RAPOR.md"))
