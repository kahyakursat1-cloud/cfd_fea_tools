# CLAUDE.md — CFD/FEA Araçları

## Parent
`bilsem_beyin/CLAUDE.md` kurallarını devralır. Mod: 🔬 Araştırma

## Proje
OpenFOAM (CFD) + CalculiX (FEA) entegre analiz paketi. Blender ile sentetik veri üretimi, parametrik mesh çalışmaları. (Fotogrametri modülü 2026-06-10 itibarıyla kaldırıldı.)

## Yapı
```
src/              → Python otomasyon ve post-processing
mesh/             → Mesh üretim scriptleri
materials/        → materials.json — malzeme veritabanı
docs/             → Türkçe rehberler (OpenFOAM, CalculiX, Blender)
```

## Teknik Bağlam
- **CFD:** simpleFoam / icoFoam; mesh bağımsızlık analizi zorunlu; yakınsama: residuals < 1e-4
- **FEA:** CalculiX `.inp` formatı; lineer/nonlineer statik; mesh tipi C3D8R varsayılan
- **Blender:** Python API ile sentetik arka plan; HDRI aydınlatma
- **Post-processing:** ParaView + Python (vtk kütüphanesi)
- **Donanım:** RTX 4060 — GPU hızlandırma için snappyHexMesh paralel çalıştır

## Kurallar (Bu Projeye Özel)
- Yeni solver önermeden önce mevcut `src/` içinde ne olduğunu kontrol et
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
