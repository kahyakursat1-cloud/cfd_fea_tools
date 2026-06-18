"""Far-field / iz-momentum sürükleme çıkarımı (2. mertebe, mesh-az-duyarlı).

Yüzey-basınç entegrasyonu (~1. mertebe, TE/çözünürlük-duyarlı; GCI=%103'ün kaynağı) yerine
gövde ARKASINDAKİ bir iz-düzleminde momentum-açığı integrali. Kontrol-hacmi momentum
dengesi (sıkışmaz):
    D = ρ ∫∫ u_x (U∞ − u_x) dA  +  ∫∫ (p∞ − p) dA
Uzak izde p→p∞ → basınç terimi sönümlenir; yakın izde de hesaba katılır. OpenFOAM
sıkışmaz p kinematiktir (m²/s²) → statik basınç = ρ·p_kin, p∞=0 referans.

Referans: Betz/Jones iz-integrali (profil sürüklemesi); Anderson, *Fundamentals of
Aerodynamics* (kontrol-hacmi sürükleme). Yüzey-integraline 2. mertebe alternatif.
"""
from __future__ import annotations

import numpy as np


def wake_momentum_drag(ux, area, p_kin=None, U_inf=30.0, rho=1.225, A_ref=None,
                       deficit_thresh_frac=0.002) -> dict:
    """İz-düzlemi örneklerinden momentum-açığı sürüklemesi.

    ux: akış-yönü hız bileşeni (m/s), düzlem hücre/nokta başına
    area: her örneğin alanı (m²) — sampledSurface yüz alanları
    p_kin: kinematik basınç (m²/s²); None ise basınç terimi atlanır (uzak-iz varsayımı)
    U_inf: serbest-akış hızı; A_ref: Cd için referans alan
    deficit_thresh_frac: İZ MASKESİ — açığı (U∞−ux) bu eşiğin (×U∞) altında olan hücreler
      SERBEST-AKIŞ sayılır (integrand teorik olarak 0; pratikte gürültü). Tüm-düzlem
      integrali bunsuz domain-gürültüsüne boğulur (ince cisim, geniş domain). Maske,
      teorik integrali değiştirmez (iz dışı katkı=0), yalnız gürültüyü atar.
    Döner: {drag_N, mom_term_N, pres_term_N, iz_alani_m2, [Cd]}
    """
    ux = np.asarray(ux, float)
    area = np.asarray(area, float)
    wake = (U_inf - ux) > deficit_thresh_frac * U_inf            # iz bölgesi
    mom = rho * float(np.sum(ux[wake] * (U_inf - ux[wake]) * area[wake]))
    if p_kin is not None:
        pk = np.asarray(p_kin, float)
        pres = -rho * float(np.sum(pk[wake] * area[wake]))       # ρ∫(p∞−p)dA, p∞=0
    else:
        pres = 0.0
    D = mom + pres
    out = {"drag_N": D, "mom_term_N": mom, "pres_term_N": pres,
           "iz_alani_m2": float(area[wake].sum())}
    if A_ref:
        out["Cd"] = D / (0.5 * rho * U_inf ** 2 * A_ref)
    return out


def read_sampled_plane_vtk(vtk_path):
    """OpenFOAM sampledSurface (cuttingPlane) VTK'sından nokta+U+p+alan oku.
    Legacy .vtk ve XML .vtp destekler. Döner: (ux[N], p_kin[N]|None, area[N])."""
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    vtk_path = str(vtk_path)
    if vtk_path.lower().endswith(".vtp"):
        rdr = vtk.vtkXMLPolyDataReader()
        rdr.SetFileName(vtk_path); rdr.Update()
    else:
        rdr = vtk.vtkPolyDataReader()
        rdr.SetFileName(vtk_path)
        rdr.ReadAllVectorsOn(); rdr.ReadAllScalarsOn(); rdr.Update()
    poly = rdr.GetOutput()
    pd = poly.GetPointData()
    U = vtk_to_numpy(pd.GetArray("U")) if pd.GetArray("U") is not None else None
    p = vtk_to_numpy(pd.GetArray("p")) if pd.GetArray("p") is not None else None
    if U is None:
        raise ValueError(f"VTK'da U alanı yok: {vtk_path}")
    # hücre alanlarını hesapla, nokta-değerlerini hücre-ortalamasıyla eşle
    from vtk import vtkCellSizeFilter
    cs = vtkCellSizeFilter(); cs.SetInputData(poly)
    cs.ComputeAreaOn(); cs.ComputeVolumeOff(); cs.ComputeLengthOff(); cs.Update()
    areas = vtk_to_numpy(cs.GetOutput().GetCellData().GetArray("Area"))
    # her hücrenin köşe-ort. ux ve p
    ux_cell, p_cell = [], []
    for c in range(poly.GetNumberOfCells()):
        ids = poly.GetCell(c).GetPointIds()
        idx = [ids.GetId(k) for k in range(ids.GetNumberOfIds())]
        ux_cell.append(float(np.mean(U[idx, 0])))
        if p is not None:
            p_cell.append(float(np.mean(p[idx])))
    return (np.array(ux_cell), np.array(p_cell) if p is not None else None, areas)


def compute_case_wake_drag(case_dir, U_inf, A_ref, rho=1.225, use_pressure=True):
    """Çözülmüş case'in postProcessing/wakePlane/*/wake.{vtp,vtk}'sından iz-momentum
    Cd'sini hesaplar (yüzey-integrasyon Cd'sine 2.-mertebe alternatif).
    Döner: {Cd, drag_N, mom_term_N, pres_term_N, vtk} | None."""
    from pathlib import Path
    pp = Path(case_dir) / "postProcessing" / "wakePlane"
    if not pp.exists():
        return None
    hits = sorted(pp.rglob("wake.vtp")) + sorted(pp.rglob("wake.vtk"))
    if not hits:
        hits = sorted(pp.rglob("*.vtp")) + sorted(pp.rglob("*.vtk"))
    if not hits:
        return None
    ux, p_kin, area = read_sampled_plane_vtk(hits[-1])
    res = wake_momentum_drag(ux, area, p_kin=(p_kin if use_pressure else None),
                             U_inf=U_inf, rho=rho, A_ref=A_ref)
    res["vtk"] = str(hits[-1])
    return res
