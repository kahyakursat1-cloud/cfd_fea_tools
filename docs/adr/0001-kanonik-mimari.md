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

## REVİZYON 2 (2026-06-18) — ARAÇ STACK'İ (4. katman) eklendi

ADR 2026-06-03'te yazıldı; o tarihten sonra **birincil kullanıcı-yüzü katman** inşa edildi
ve bu ADR'de yoktu. Güncel kanonik durum:

| Katman | Modüller | Rol |
|--------|----------|-----|
| **#4 — araç (BİRİNCİL, kullanıcı-yüzü)** | `vehicle_pipeline.py`, `auto_pilot.py`, `vehicle_fea.py`, `vehicle_topopt.py`, `supersonic_cfd.py`, `vehicle_polar.py`, `app_analyzer.py` (GUI), `farfield_drag.py`, `manufacturability.py` | Keyfi STL → otopilot sınıflandırma+öğrenme → mesh → CFD/FEA → rapor. **#3 `analysis/` motorunu kullanır.** |
| #3 — analysis (genel motor) | `analysis/` | #4'ün altyapısı; doğrudan da kullanılır |
| #1 — pipeline (uçak 2D V&V) | `simulation_runner`, `fea_runner`, kök `report_generator`, `pipeline.py`, `app_parametric.py` | Airfoil/küre V&V, GCI kampanyaları (ayrı değer) |
| #2 — solvers/post_processing | `solvers/`, `post_processing/` | İkincil wrapper + PDF rapor |

**Güncel karar:** Yeni araç-analizi geliştirmesi **#4 üzerinden** (bu seansın tüm işi:
gerilme-TO, FSI, far-field, parallel-CFD fix, batch-öğrenme orada). #1 2D-V&V için korunur
(airfoil GCI suite). #2/#3 değişmedi. **Mass-deletion hâlâ İPTAL** (REVİZYON-1 gerekçesi geçerli).

**Giriş noktaları (güncel):** `app_analyzer.py` (araç GUI, #4) + `app_parametric.py` (2D V&V GUI, #1)
+ `pipeline.py` (V&V CLI) + `experiments/batch_learn.py` (toplu öğrenme).

## REVİZYON 3 (2026-07-26) — #2 silinmedi, DÜRÜSTLEŞTİRİLDİ

Silme adayı olarak yeniden incelendi (yalnız `check_integration.py` tüketiyor). REVİZYON-1/2
kararı korundu — **silinmedi** — ama silme tartışmasında asıl sorun ortaya çıktı: sorun ölü
kod değil, **provenance yıkaması**.

Zincir şuydu: `solvers/openfoam_wrapper._run_mock_simulation()` çözücü yokken SABİT bir
katsayı dosyası yazıyor (Cd=0.1452, Cl=0.521) → `post_processing.read_force_coefficients()`
onu diskten okuyup `source='openfoam'` etiketliyor → `CFDResult` bu etiketi hiç taşımıyor →
`check_integration.py` `[OK] Cd=0.1452` ve `[SUCCESS] END-TO-END WORKFLOW TAMAMLANDI!`
basıyor. Uydurma sayı bir dosyadan geçerek "çözücü çıktısı"na dönüşüyordu.

Yapılan (silme yerine):
- Mock koşu ürettiği veriyi kendi işaretler: `postProcessing/.MOCK` + dat başlığında `# MOCK`.
- Okuyucu işaretçiyi tanır → `source='mock'`; `CFDResult.data_source` / `convergence_source`
  alanları eklendi, `olculdu` özelliği YALNIZ gerçek `openfoam` için True.
- Log yokken dönen temsili rezidüel eğrisi `source='placeholder'` ile işaretlenir.
- `check_integration.py` artık "HAT DUMAN TESTİ — ANALİZ SONUCU ÜRETMEZ" başlığıyla koşar,
  sayıları `[TAHMIN]` etiketiyle basar ve gerçek yolları gösterir.
- `tests/test_provenance.py` bu hata sınıfını dondurur.

**Karar:** #2 ikincil katman olarak kalır; ürettiği hiçbir sayı ölçülmüş sonuçtan ayırt
edilemez halde sunulamaz. Aynı ilke tüm katmanlarda geçerli (bkz. `validity_envelope`
fizik kapısı, `zarf.py` kanıt-tabanlı çalışma zarfı).

## Notlar

Karakterizasyon + regresyon testleri (`tests/`) dört katmanın çekirdek fiziğini ve
post-processing matematiğini dondurur — 118 test (golden değerler + araç-stack V&V dahil).
2026-07-26: 290+ teste çıktı; `external` işaretli iki test GERÇEK çözücüyü (ccx + OpenFOAM)
uçtan uca koşturur (`tests/test_cozucu_regresyon.py`).
