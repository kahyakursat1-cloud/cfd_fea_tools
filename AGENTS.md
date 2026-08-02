# AGENTS.md — CFD/FEA Araçları

## Parent
`bilsem_beyin/AGENTS.md` kurallarını devralır. Mod: 🔬 Araştırma

## Proje
OpenFOAM (CFD) + CalculiX (FEA) entegre analiz paketi. Parametrik mesh çalışmaları, V&V (GCI/validation). (Fotogrametri modülü 2026-06-10'da kaldırıldı. Görüntü-işleme/Blender-YOLO sentetik-veri katmanı 2026-06-21'de ayrı kod-tabanına taşındı → `../goruntu_isleme/`.)

## Yapı
Dosyalar şu an kök dizinde flat (paketleme pyproject Faz 4'te). Giriş noktaları:
```
analysis/                   → KANONİK ortak katman (openfoam_runner, ccx_runner,
                              calculix_writer, frd_parser, tet_mesher) — YENİ kod bunu kullanır
pipeline.py / launcher.py   → CLI giriş noktaları
app_analyzer.py             → ana GUI (araç analiz stüdyosu, analysis/ tabanlı)
vehicle_pipeline.py         → headless araç CFD/FEA akışı (analysis/ tabanlı)
materials.json              → malzeme veritabanı (material_database.py okur)
docs/                       → Türkçe rehberler (OpenFOAM, CalculiX)
constants.py                → proje-geneli eşikler (TEK KAYNAK)
```
**İki-hızlı uyarı:** eski `simulation_runner.py`/`app_parametric.py` + standalone V&V
scriptleri `analysis/`'i kullanmaz, kendi iskelesini tekrarlar (refactor ayrı iş).

**DÜZELTME (2026-08-02):** "çalışır" ifadesi `app_parametric.py` için YANLIŞTI —
analiz sekmeleri çözücüyü hiç çağırmıyor, sahte ilerleme çubuğuyla "tamamlandı"
yazıyordu; FEA sekmesi gerilmeyi `yük/100×2.5` ile uydurup "GÜVENLİ" hükmü
veriyordu. Artık gerekçeli ret verip `app_analyzer.py`'ye yönlendiriyorlar.
Motor (`simulation_runner.run_simulation`) gerçek; sahte olan GUI katmanıydı.
Kullanıcıya önerilecek giriş noktası: **`python app_analyzer.py`**.

## Teknik Bağlam
- **CFD:** simpleFoam / icoFoam / shockFluid; mesh bağımsızlık analizi zorunlu; yakınsama: residuals < 1e-4
- **FEA:** CalculiX `.inp` formatı; lineer/nonlineer statik; üretim C3D10 (tet10)
- **Post-processing:** ParaView + Python (vtk kütüphanesi)
- **Donanım:** RTX 4060 — GPU hızlandırma için snappyHexMesh paralel çalıştır

## Kurallar (Bu Projeye Özel)
- Yeni CFD/FEA kodu yazmadan önce `analysis/` (kanonik katman) içinde ne olduğunu kontrol et; case iskelesini tekrar yazma
- `materials.json` dosyasını varsayımla değiştirme — kaynakla birlikte güncelle
- OpenFOAM case yapısını `constant/`, `system/`, `0/` hiyerarşisini bozma
- Mesh kalite metrikleri: maxNonOrthogonality < 70, maxSkewness < 4

## Komutlar
- `/mesh [geometri]` — snappyHexMesh pipeline kurulumu
- `/analiz [tip]` — solver seçimi ve boundary conditions
- `/sonuç [case]` — post-processing ve figür üretimi
- `/malzeme [isim]` — materials.json güncelle
- `/tasarım [gereksinim]` — çok-disiplinli tasarım orkestratörü (tasarim-muhendisi skill'i): disiplin ajanlarını (aero/yapısal-termal/malzeme-imalat/sistem-MDAO) dispatch eder, takas raporu üretir

---
**Oluşturma:** 2026-04-30 | **Versiyon:** 1.0
