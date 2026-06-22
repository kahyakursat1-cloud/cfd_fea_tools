# 📇 Wiki Index — bilsem_beyin Knowledge Base

**Last Updated:** 2026-06-22  
**Total Pages:** 18  
**Status:** ✅ Production Ready

---

## 📚 Kategoriler

### System & Architecture
- [SYSTEM_STATUS.md](SYSTEM_STATUS.md) — Production status, module checklist, performance metrics (tek güncel durum kaynağı)
- [docs/adr/0001-kanonik-mimari.md](docs/adr/0001-kanonik-mimari.md) — Katman mimarisi kararı
- Tarihsel anlık görüntüler (SYSTEM_COMPLETE, SYSTEM_READY, SETUP_COMPLETE, IMPLEMENTATION_*) → [docs/archive/](docs/archive/)

### Akademik Kaynaklar & Teori
- [ACADEMIC_REFERENCES.md](ACADEMIC_REFERENCES.md) — Theory foundations + course curriculum mapping
- [sources/SOURCES_INDEX.md](sources/SOURCES_INDEX.md) — Source catalog (ArXiv, FAA, TEKNOFEST)

### Teknik Rehberler (How-To)
- [README_TR.md](README_TR.md) — Turkish quick-start guide
- [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) — Setup instructions (all platforms)
- [PARAMETRIK_ANALIZ_REHBERI.md](PARAMETRIK_ANALIZ_REHBERI.md) — CFD parametric studies
- [OPENFOAM_REHBERI.md](OPENFOAM_REHBERI.md) — OpenFOAM setup & usage
- [CALCULIX_REHBERI.md](CALCULIX_REHBERI.md) — CalculiX FEA guide

### Görüntü-işleme (AYRILDI)
Blender sentetik-veri + YOLO eğitimi + RTX4060/Blender GPU rehberleri **2026-06-21'de
ayrı kod-tabanına taşındı** → `../goruntu_isleme/` (BLENDER_BACKGROUNDS, ADVANCED_DATASET,
YOLO_RTX4060_MEMORY, RTX4060_OPTIMIZATION).

---

## 🔗 Cross-References

**CFD Workflow:**
```
PARAMETRIK_ANALIZ_REHBERI 
  ↓ (uses OpenFOAM)
OPENFOAM_REHBERI
```

**ML/Görüntü-işleme Pipeline:** → ayrı kod-tabanı `../goruntu_isleme/` (bkz. README).

**Setup:**
```
INSTALLATION_GUIDE
  ↓ (explains modules in)
SYSTEM_STATUS
  ↓ (theory from)
ACADEMIC_REFERENCES
  ↓ (references sourced from)
sources/SOURCES_INDEX
```

---

## 📊 Page Metadata

| Page | Type | Last Updated | Sources | Size |
|------|------|---|---|---|
| SYSTEM_STATUS.md | Architecture | 2026-04-07 | 5 | 15 KB |
| ACADEMIC_REFERENCES.md | Reference | 2026-04-07 | 12+ | 45 KB |
| OPENFOAM_REHBERI.md | How-To | 2026-03-15 | 3 | 12 KB |
| CALCULIX_REHBERI.md | How-To | 2026-03-15 | 2 | 10 KB |
| PARAMETRIK_ANALIZ_REHBERI.md | How-To | 2026-03-10 | 2 | 8 KB |
| docs/archive/IMPLEMENTATION_SUMMARY.md | Overview (arşiv) | 2026-04-01 | - | 20 KB |
| README_TR.md | Quick-Start | 2026-03-01 | 1 | 6 KB |
| INSTALLATION_GUIDE.md | Setup | 2026-03-05 | 2 | 11 KB |

---

## 🔍 Search by Topic

### CFD (Computational Fluid Dynamics)
- [PARAMETRIK_ANALIZ_REHBERI.md](PARAMETRIK_ANALIZ_REHBERI.md) — Design optimization
- [OPENFOAM_REHBERI.md](OPENFOAM_REHBERI.md) — Solver setup
- [ACADEMIC_REFERENCES.md](ACADEMIC_REFERENCES.md#1-cfd-analizi) — Theory (Navier-Stokes, RANS)

### FEA (Finite Element Analysis)
- [CALCULIX_REHBERI.md](CALCULIX_REHBERI.md) — Solver guide
- [ACADEMIC_REFERENCES.md](ACADEMIC_REFERENCES.md#2-fea-analizi) — Theory (Elasticity, Galerkin)

### ML / Görüntü-işleme (YOLOv11 + Blender) — AYRILDI
→ Ayrı kod-tabanı `../goruntu_isleme/` (2026-06-21). Teori: ACADEMIC_REFERENCES.md#4.

### Parametric Design
- [PARAMETRIK_ANALIZ_REHBERI.md](PARAMETRIK_ANALIZ_REHBERI.md) — Optimization studies
- [ACADEMIC_REFERENCES.md](ACADEMIC_REFERENCES.md#6-parametrik-tasarım-ve-optimizasyon) — Theory

### Ders Müfredatı (Curriculum)
- [ACADEMIC_REFERENCES.md](ACADEMIC_REFERENCES.md#7-ders-müfredatı-bağlantıları) — Course mapping

---

## 📖 Reading Paths

### For Beginners
1. [README_TR.md](README_TR.md) — Overview (5 min)
2. [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) — Setup (15 min)
3. [SYSTEM_STATUS.md](SYSTEM_STATUS.md) — Architecture (10 min)

### For CFD Engineers
1. [OPENFOAM_REHBERI.md](OPENFOAM_REHBERI.md) — Solver setup
2. [PARAMETRIK_ANALIZ_REHBERI.md](PARAMETRIK_ANALIZ_REHBERI.md) — Optimization
3. [ACADEMIC_REFERENCES.md#1-cfd-analizi](ACADEMIC_REFERENCES.md) — Theory

### For ML Practitioners (Görüntü-işleme)
→ Ayrı kod-tabanı `../goruntu_isleme/` (Blender sentetik-veri → YOLO; bkz. README).

### For Researchers
1. [ACADEMIC_REFERENCES.md](ACADEMIC_REFERENCES.md) — Theory & citations (start here)
2. [sources/SOURCES_INDEX.md](sources/SOURCES_INDEX.md) — Source catalog
3. [docs/archive/IMPLEMENTATION_SUMMARY.md](docs/archive/IMPLEMENTATION_SUMMARY.md) — What was built (arşiv)

---

## ✅ Maintenance Checklist

- [ ] Run lint pass (check for orphaned pages)
- [ ] Update this INDEX.md
- [ ] Check cross-references are valid
- [ ] Review log.md for recent changes
- [ ] Update SYSTEM_STATUS metrics

---

**Next Steps:**
- Create `log.md` for chronological changelog
- Add YAML frontmatter to all pages
- Set up Obsidian vault (optional)
- Schedule regular lint passes
