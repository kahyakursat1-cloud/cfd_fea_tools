# CLAUDE.md — CFD/FEA Araçları

## Parent
`bilsem_beyin/CLAUDE.md` kurallarını devralır. Mod: 🔬 Araştırma

## Proje
OpenFOAM (CFD) + CalculiX (FEA) entegre analiz paketi. Parametrik mesh çalışmaları, V&V (GCI/validation). (Fotogrametri modülü 2026-06-10'da kaldırıldı. Görüntü-işleme/Blender-YOLO sentetik-veri katmanı 2026-06-21'de ayrı kod-tabanına taşındı → `../goruntu_isleme/`.)

## Yapı
Dosyalar şu an kök dizinde flat (paketleme pyproject Faz 4'te). Mantıksal katmanlar:
```
analysis/         → KANONİK ortak katman: openfoam_runner (CFDCase/build_case/
                    run_cfd/mesh_quality_gate), ccx_runner, calculix_writer,
                    frd_parser, tet_mesher. YENİ CFD/FEA kodu BUNU kullanır.
vehicle_*.py      → modern araç akışı (analysis/ tabanlı): pipeline/fea/polar/topopt/report
app_analyzer.py   → ana GUI (araç analiz stüdyosu, analysis/ tabanlı)
materials.json    → malzeme veritabanı (material_database.py okur)
docs/             → Türkçe rehberler (OpenFOAM, CalculiX)
constants.py      → proje-geneli eşikler (TEK KAYNAK)
```
**İki-hızlı uyarı:** `simulation_runner.py` + `app_parametric.py` (eski Parametrik GUI)
ve standalone V&V scriptleri (`transition_polar`, `cgrid_*`, `rocket_cfd`) `analysis/`'i
KULLANMAZ — kendi case iskelesini tekrarlar. Refactor riskli, ayrı iş.

**DÜZELTME (2026-08-02):** "Çalışıyorlar" ifadesi `app_parametric.py` için YANLIŞTI.
Analiz sekmeleri çözücüyü hiç çağırmıyor, sahte ilerleme çubuğuyla "tamamlandı"
yazıyordu; FEA sekmesi gerilmeyi `yük/100×2.5` ile uydurup ondan "GÜVENLİ" hükmü
veriyordu. O yollar artık gerekçeli ret veriyor ve `app_analyzer.py`'ye yönlendiriyor.
`simulation_runner.run_simulation` motoru GERÇEK; sahte olan yalnız GUI katmanıydı.
Kullanıcıya önerilecek giriş noktası: **`python app_analyzer.py`**.

## Teknik Bağlam
- **CFD:** simpleFoam / icoFoam; mesh bağımsızlık analizi zorunlu; yakınsama: residuals < 1e-4
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

---
**Oluşturma:** 2026-04-30 | **Versiyon:** 1.0
