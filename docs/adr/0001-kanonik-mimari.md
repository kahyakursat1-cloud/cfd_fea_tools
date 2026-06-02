# ADR 0001 — Kanonik Çözücü Mimarisi ve Giriş Noktaları

- **Durum:** Kabul edildi
- **Tarih:** 2026-06-03
- **Bağlam:** Endüstri-seviye refactor (Faz 3)

## Bağlam

Depo organik büyüme sonucu **aynı CFD/FEA yeteneğinin üç ayrı kuşağını** barındırıyor.
Bağımlılık grafiği çıkarıldığında her kuşağın farklı tüketicisi olduğu görüldü:

| Kuşak | Modüller | Tüketici | Son aktivite |
|-------|----------|----------|--------------|
| **#1 — pipeline** | `simulation_runner.py`, `fea_runner.py`, `report_generator.py` (kök) | `pipeline.py`, `app_parametric.py`, `run_aoa_polar.py`, `run_prism_3d.py` | Haz 2026 (aktif) |
| **#2 — solvers/post_processing** | `solvers/`, `post_processing/` | `main.py` (yetim), `test_integration.py`, `full_integration_test.py` | Nis 2026 |
| **#3 — analysis** | `analysis/` (`openfoam_runner`, `calculix_writer`, `ccx_runner`, `tet_mesher`, `frd_parser`) | `test_cfd_pipeline.py`, `test_fea_pipeline.py` | Nis 2026 |

Bunlar satır-satır kopya **değil** — aynı problemi çözen üç jenerasyon. Mekanik
birleştirme, OpenFOAM/CalculiX olmadan doğrulanamayacağı için yüksek riskli.

## Karar

1. **Kanonik giriş noktaları:**
   - `pipeline.py` — headless V&V CLI orkestratörü (otomasyon)
   - `app_parametric.py` — PySide6 GUI (`launcher.py` ve `RUN_SYSTEM.bat` bunu başlatır)

2. **Kanonik çözücü kuşağı = #1.** Yeni geliştirme `simulation_runner` /
   `fea_runner` / kök `report_generator` üzerinden yapılır.

3. **#2 ve #3 deprecated.** `__init__.py`/başlık notlarıyla işaretlendi. Tüketicileri:
   - `main.py` — yetim (sıfır referans), eski CFD-only GUI; `app_parametric.py` halefi.
   - `analysis/` ve `solvers/post_processing/` test'leri — küre doğrulama smoke testleri.

## Sonuç

- **Kısa vade:** Deprecation notları aktif; CI yalnızca kanonik path + karakterizasyon
  testlerini çalıştırır (eski smoke testler `external` gerektirir, atlanır).
- **Bekleyen karar (kullanıcı onayı):** `main.py`, `solvers/`, `post_processing/`,
  `analysis/` ve bağlı smoke testlerin **silinmesi**. ~2000 satır. Silme öncesi
  kullanıcı, bu test/validation kodundan harvest edilecek bir şey kalmadığını teyit
  etmeli. O zamana dek deprecated ama yerinde.

## Notlar

Karakterizasyon testleri (`tests/test_structural_loads.py`, `tests/test_material_database.py`)
kuşak #1'in çekirdek fiziğini dondurur — gelecekteki konsolidasyon için güvenlik ağı.
