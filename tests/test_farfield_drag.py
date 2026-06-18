"""Far-field iz-momentum sürükleme — Gaussian-iz analitik doğrulama (CFD'siz)."""
import numpy as np

from farfield_drag import wake_momentum_drag


def test_gaussian_wake_matches_analytic():
    # Gaussian iz: u_x = U(1 - A·exp(-r²/2σ²)). Kapalı-form:
    # D = ρU²·∫u_x(U-u_x)dA = ρU²·π·σ²·A(2-A)  (uzak-iz, p=0)
    U, rho, A, sigma = 30.0, 1.225, 0.3, 0.05
    n, half = 500, 0.6
    xs = np.linspace(-half, half, n)
    X, Y = np.meshgrid(xs, xs)
    da = (2 * half / n) ** 2
    ux = U * (1 - A * np.exp(-(X ** 2 + Y ** 2) / (2 * sigma ** 2)))
    res = wake_momentum_drag(ux.ravel(), np.full(ux.size, da), U_inf=U, rho=rho,
                             deficit_thresh_frac=0.0)        # saf integral (maske yok)
    D_an = rho * U ** 2 * np.pi * sigma ** 2 * A * (2 - A)
    assert abs(res["drag_N"] - D_an) / D_an < 0.02       # %2 (ayrıklaştırma)
    assert res["pres_term_N"] == 0.0                      # p verilmedi → 0


def test_wake_mask_rejects_freestream_noise():
    # Gerçek-CFD durumu: küçük iz + geniş serbest-akış'ta gürültü. Maske, gürültüyü
    # atıp izi yakalar (maske YOKsa gürültü gerçek açığı boğar).
    U, rho, sigma, A = 30.0, 1.225, 0.05, 0.3
    n, half = 400, 0.6
    xs = np.linspace(-half, half, n)
    X, Y = np.meshgrid(xs, xs)
    da = (2 * half / n) ** 2
    ux = U * (1 - A * np.exp(-(X ** 2 + Y ** 2) / (2 * sigma ** 2)))
    rng = np.random.default_rng(0)
    ux_noisy = ux + rng.normal(0, 0.02, ux.shape)            # serbest-akışta ±0.02 gürültü
    D_an = rho * U ** 2 * np.pi * sigma ** 2 * A * (2 - A)
    masked = wake_momentum_drag(ux_noisy.ravel(), np.full(ux.size, da), U_inf=U, rho=rho)
    nomask = wake_momentum_drag(ux_noisy.ravel(), np.full(ux.size, da), U_inf=U, rho=rho,
                                deficit_thresh_frac=0.0)
    assert abs(masked["drag_N"] - D_an) / D_an < 0.05        # maske: izi doğru yakalar
    # maske, serbest-akış gürültüsünü atarak maskesizden DAHA DOĞRU
    assert abs(masked["drag_N"] - D_an) < abs(nomask["drag_N"] - D_an)


def test_no_deficit_zero_drag():
    # Üniform akış (iz yok) → momentum açığı 0 → sürükleme 0
    U = 25.0
    res = wake_momentum_drag(np.full(100, U), np.full(100, 1e-4), U_inf=U)
    assert abs(res["drag_N"]) < 1e-9


def test_pressure_term_and_cd():
    # İz bölgesinde (hız açığı VAR) basınç terimi + Cd normalizasyonu. Maske hız-tabanlı:
    # açık olan hücrelerde hem mom hem pres katkı verir.
    U, rho, Aref = 20.0, 1.225, 0.01
    ux = np.full(50, U * 0.9)                            # %10 açık → tüm hücreler izde
    pk = np.full(50, -5.0)                                # p<0 → ρ∫(p∞-p)dA>0 (sürükleme +)
    area = np.full(50, 2e-4)
    res = wake_momentum_drag(ux, area, p_kin=pk, U_inf=U, rho=rho, A_ref=Aref)
    assert res["pres_term_N"] > 0 and res["mom_term_N"] > 0
    assert res["Cd"] == res["drag_N"] / (0.5 * rho * U ** 2 * Aref)
