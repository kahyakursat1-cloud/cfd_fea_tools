# ADR 0001 — Kanonik Çözücü Mimarisi ve Giriş Noktaları

- **Durum:** Kabul edildi (2026-06-03 doğrulamayla revize — aşağıdaki REVİZYON)
- **Tarih:** 2026-06-03
- **Bağlam:** Endüstri-seviye refactor (Faz 3) + uçtan uca doğrulama

## Bağlam

Depo organik büyüme sonucu **aynı CFD/FEA yeteneğinin üç ayrı kuşağını** barındırıyor.
Bağımlılık grafiği çıkarıldığında her kuşağın farklı tüketicisi olduğu görüldü:

| Kuşak | Modüller | Tüketici | Son aktivite |
|-------|----------|----------|--------------|
| **#1 — pipeline** | `simulation_runner.py`, `fea_runner.py`, `report_generator.py` (kök) | `pipeline.py`, `app_parametric.py`, `run_aoa_polar.py`, `run_prism_3d.py` | Haz 2026 (aktif) |
| **#2 — solvers/post_processing** | `solvers/`, `post_processing/` | `main.py` (yetim), `check_integration.py`, `full_integration_test.py` | Nis 2026 |
| **#3 — analysis** | `analysis/` (`openfoam_runner`, `calculix_writer`, `ccx_runner`, `tet_mesher`, `frd_parser`) | `check_cfd_pipeline.py`, `check_fea_pipeline.py` | Nis 2026 |

Bunlar satır-satır kopya **değil** — aynı problemi çözen üç jenerasyon. Mekanik
birleştirme, OpenFOAM/CalculiX olmadan doğrulanamayacağı için yüksek riskli.

## Karar

1. **Kanonik giriş noktaları:**
   - `pipeline.py` — headless V&V CLI orkestratörü (otomasyon)
   - `app_parametric.py` — PySide6 GUI (`launcher.py` ve `RUN_SYSTEM.bat` bunu başlatır)

2. **Kanonik çözücü kuşağı = #1.** Yeni geliştirme `simulation_runner` /
   `fea_runner` / kök `report_generator` üzerinden yapılır.

3. **#2 ve #3 ikincil/tamamlayıcı — eskimiş DEĞİL.** Yalnızca `main.py` gerçek yetim.

## REVİZYON (2026-06-03) — doğrulamayla düzeltildi

İlk taslak #2/#3'ü "deprecated kuşak" sandı. Uçtan uca canlı doğrulama bunu çürüttü:

- **#3 `analysis/` = çalışan GENEL sıfırdan motor.** Küre ile kanıtlandı:
  CFD `Cd=0.135` (snappyHexMesh→foamRun), FEA `.frd` (gmsh tet→ccx). `pipeline.py`
  (uçağa-özel V&V) ile **tamamlayıcı**; o keyfi STL geometriyi meshleyip çözer.
  Silmek = çalışan yeteneği kaybetmek → **silinmez.**
- **#2 `solvers/` + `post_processing/` = ikincil wrapper + PDF rapor.**
  `check_integration` (mock solver'larla) + `full_integration_test` tüketir. İkincil
  ama işlevsel; kanonik gerçek-solver yolları `pipeline.py` ve `analysis/`.
- **`main.py` = tek gerçek yetim** (sıfır referans, eski CFD-only GUI; halefi
  `app_parametric.py`). Silinmesi tek meşru aday; kullanıcı onayına bağlı.

## Sonuç

- Üç "kuşak" aslında üç **tamamlayıcı katman**: uçak-V&V (pipeline) / genel-motor
  (analysis) / wrapper+rapor (solvers). Mass deletion **iptal** — regresyon olurdu.
- Etiketler düzeltildi (`__init__.py` notları: analysis=genel motor, solvers/pp=ikincil).
- ✅ `main.py` (yetim) **silindi** (2026-06-03). Sıfır fonksiyonel referanstı;
   halefi `app_parametric.py`. Gerekirse git geçmişinden geri alınabilir.

## Notlar

Karakterizasyon + regresyon testleri (`tests/`) üç katmanın çekirdek fiziğini ve
post-processing matematiğini dondurur — 28 test, golden değerler dahil.
