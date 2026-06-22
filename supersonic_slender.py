"""Slender-body (linearize) süpersonik Cd — donanımsız analitik yol.

İnce dönel cisim (roket, fineness≳10 → R/L≲0.05) M≈1.2–3'te: dalga-drag von Kármán
alan-kuralı Fourier yöntemiyle (Sears-Haack kapalı-formuyla DOĞRULANMIŞ), cilt-sürtünmesi
mevcut friction_cd ile, taban-drag ampirik. 3D explicit shockFluid'in intractable olduğu
mutlak Cd'yi bu rejimde verir (docs/supersonic_cd_arastirma.md §2.3).

Geçerlilik: slender (R/L≲0.05), 1.2≲M≲5, küçük α, ayrılma yok. Bozulursa wedge CFD (§2.1).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from supersonic_cfd import MU_AIR, friction_cd

_trapz = getattr(np, "trapezoid", None) or np.trapz   # numpy 2.x: trapz→trapezoid


def _despike(a: np.ndarray, w: int = 5) -> np.ndarray:
    """Rolling-median: tek-istasyon spike'ları (taban-kapağı dilimi vb.) sil.
    Alan-kuralı dalga-drag'i spike'a aşırı duyarlı (delta → yakınsamayan A_n)."""
    h = w // 2
    b = np.pad(a, h, mode="edge")
    return np.array([np.median(b[i:i + w]) for i in range(len(a))])


def area_distribution(stl_path, n: int = 120):
    """STL'i eksen boyunca dilimle → kesit alan dağılımı S(x). Dönüş: x, S, L, s_max,
    s_base, s_wet. Eksen = en uzun bbox boyutu. Yöntem: her istasyonda dilim
    vertex'lerinin centroid'inden medyan yarıçap (dönel cisim; off-axis ve kanatçık
    spike'larına dayanıklı), S=πr². Veri olmayan istasyonlar komşudan interpolasyonla."""
    import trimesh

    mesh = trimesh.load(str(stl_path), force="mesh")
    ext = mesh.bounds[1] - mesh.bounds[0]
    axis = int(np.argmax(ext))
    L = float(ext[axis])
    lo = float(mesh.bounds[0][axis])
    other = [a for a in range(3) if a != axis]
    v = mesh.vertices
    xs = np.linspace(lo + 1e-3 * L, lo + (1 - 1e-3) * L, n)
    S = np.full(n, np.nan)
    for i, x in enumerate(xs):
        for k in (1.0, 2.0, 4.0):              # band yarı-genişliğini gerekirse genişlet
            band = np.abs(v[:, axis] - x) < k * L / n
            if band.sum() >= 3:
                pts = v[band][:, other]
                c = pts.mean(axis=0)            # dilim centroid'i (off-axis gövde için)
                r = np.sqrt(((pts - c) ** 2).sum(axis=1))
                S[i] = math.pi * float(np.median(r)) ** 2
                break
    valid = ~np.isnan(S)
    if valid.sum() < 4:
        raise ValueError(f"alan dağılımı çıkarılamadı ({valid.sum()} geçerli istasyon)")
    S = np.interp(xs, xs[valid], S[valid])      # boşlukları doldur
    S = _despike(S, w=5)                          # taban-kapağı/dilim spike'larını sil
    x_rel = xs - lo
    s_max = float(np.median(np.sort(S)[-5:]))   # gövde (silindir) kesiti, spike-dayanıklı
    s_base = float(np.median(S[-5:]))           # kuyruk kesiti ≈ taban alanı
    s_wet = float(mesh.area)                     # toplam ıslak alan (yaklaşık)
    return x_rel, S, L, s_max, s_base, s_wet


def wave_drag_cd(x: np.ndarray, S: np.ndarray, L: float, s_ref: float,
                 n_modes: int = 24) -> float:
    """von Kármán slender-body dalga-drag C_D (alan-kuralı, Fourier).
    x=(L/2)(1-cosθ) dönüşümü; dS/dx = Σ Aₙ sin(nθ); D=(πq/4)Σ n Aₙ².
    Aₙ=(4/(πL))∫₀^π (dS/dθ)(sin nθ/sinθ)dθ. Sears-Haack ile doğrulanmış (_self_test)."""
    th = np.linspace(0.0, math.pi, 1024)
    xq = 0.5 * L * (1.0 - np.cos(th))
    Sq = np.interp(xq, x, S, left=S[0], right=S[-1])
    dSdth = np.gradient(Sq, th)
    sin_th = np.sin(th)
    cd = 0.0
    for nmode in range(1, n_modes + 1):
        ratio = np.empty_like(th)               # sin(nθ)/sinθ, uçlarda limit
        inner = np.abs(sin_th) > 1e-9
        ratio[inner] = np.sin(nmode * th[inner]) / sin_th[inner]
        ratio[~inner] = nmode * np.cos(nmode * th[~inner]) / np.cos(th[~inner])
        a_n = (4.0 / (math.pi * L)) * _trapz(dSdth * ratio, th)
        cd += nmode * a_n ** 2
    # D=(πq/4)Σn Aₙ²; C_D=D/(q·s_ref)=(π/4)Σn Aₙ²/s_ref
    return (math.pi / 4.0) * cd / s_ref


def base_drag_cd(mach: float, s_base: float, s_ref: float) -> float:
    """Ampirik süpersonik taban-drag (EN ZAYIF bileşen, pluggable). Cpb≈-1/M²
    (Hoerner birinci-mertebe); C_Db=-Cpb·S_base/S_ref. M>1 varsayar."""
    if mach <= 1.0:
        return 0.0
    cpb = -1.0 / mach ** 2
    return -cpb * s_base / s_ref


def slender_body_cd(stl_path, mach: float, velocity: float | None = None,
                    rho_inf: float = 1.225, t_inf: float = 288.0,
                    s_ref: float | None = None, n_modes: int = 24) -> dict:
    """İnce dönel cisim toplam süpersonik Cd = dalga + sürtünme + taban (bileşen-buildup).
    s_ref verilmezse S_max (frontal). velocity verilmezse M·a(t_inf)."""
    x, S, L, s_max, s_base, s_wet = area_distribution(stl_path)
    sref = s_ref if s_ref else s_max
    a_sound = math.sqrt(1.4 * 287.0 * t_inf)
    u = velocity if velocity else mach * a_sound
    cd_wave = wave_drag_cd(x, S, L, sref, n_modes)
    cd_fric = friction_cd(u, L, s_wet, sref, mach, rho_inf, MU_AIR)
    cd_base = base_drag_cd(mach, s_base, sref)
    return {
        "mach": mach, "L": L, "s_ref": sref, "s_max": s_max, "s_base": s_base,
        "s_wet": s_wet, "fineness": L / (2 * math.sqrt(s_max / math.pi)) if s_max > 0 else None,
        "cd_wave": cd_wave, "cd_friction": cd_fric, "cd_base": cd_base,
        "cd_total": cd_wave + cd_fric + cd_base,
        "method": "slender-body (von Kármán alan-kuralı + Van Driest sürtünme + ampirik taban)",
        "validity": "R/L≲0.05, 1.2≲M≲5, küçük α; bozulursa wedge CFD",
    }


def _sears_haack_cd_analytic(r_max: float, L: float) -> float:
    """Sears-Haack kapalı-form dalga-drag C_D (ref S_max=πR²): (9π²/2)(R/L)²."""
    return 4.5 * math.pi ** 2 * (r_max / L) ** 2


def _self_test() -> bool:
    """Fourier yöntemini Sears-Haack analitik kapalı-formuna karşı doğrula."""
    R, L = 0.1, 2.0
    th = np.linspace(0, math.pi, 600)
    x = 0.5 * L * (1 - np.cos(th))
    S = math.pi * R ** 2 * np.sin(th) ** 3      # Sears-Haack: S(θ)=πR²sin³θ
    s_max = math.pi * R ** 2
    cd_num = wave_drag_cd(x, S, L, s_max, n_modes=8)
    cd_ref = _sears_haack_cd_analytic(R, L)
    err = abs(cd_num - cd_ref) / cd_ref * 100
    print(f"Sears-Haack doğrulama: C_Dwave sayısal={cd_num:.6e} analitik={cd_ref:.6e} "
          f"hata=%{err:.2f}")
    return err < 2.0


if __name__ == "__main__":
    import json
    import sys

    ok = _self_test()
    print(f"  → Fourier dalga-drag {'DOĞRULANDI ✅' if ok else 'BAŞARISIZ ❌'}")
    stl = sys.argv[1] if len(sys.argv) > 1 else "rockets/rocket.stl"
    if Path(stl).exists():
        for M in (1.5, 2.0, 3.0):
            res = slender_body_cd(stl, mach=M)
            print(f"\nM={M}: Cd_total={res['cd_total']:.4f} "
                  f"(wave={res['cd_wave']:.4f} fric={res['cd_friction']:.4f} "
                  f"base={res['cd_base']:.4f}) fineness={res['fineness']:.1f}")
        out = Path("supersonic_slender_result.json")
        out.write_text(json.dumps(slender_body_cd(stl, 2.0), indent=2, ensure_ascii=False),
                       encoding="utf-8")
        print(f"\nYAZILDI {out}")
    else:
        print(f"(STL yok: {stl} — sadece self-test koştu)")
