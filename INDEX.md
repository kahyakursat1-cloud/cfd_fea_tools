# 📇 Wiki Index — bilsem_beyin Knowledge Base

**Last Updated:** 2026-04-07  
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

### Workflow Guides
- [BLENDER_BACKGROUNDS_GUIDE.md](BLENDER_BACKGROUNDS_GUIDE.md) — Background image setup
- [ADVANCED_DATASET_WORKFLOW.md](ADVANCED_DATASET_WORKFLOW.md) — Full ML training pipeline

### GPU & Optimization
- [RTX4060_OPTIMIZATION.md](RTX4060_OPTIMIZATION.md) — Blender v2 RTX 4060 settings
- [YOLO_RTX4060_MEMORY.md](YOLO_RTX4060_MEMORY.md) — YOLOv11 memory analysis & tuning

---

## 🔗 Cross-References

**CFD Workflow:**
```
PARAMETRIK_ANALIZ_REHBERI 
  ↓ (uses OpenFOAM)
OPENFOAM_REHBERI
```

**ML Pipeline:**
```
BLENDER_BACKGROUNDS_GUIDE
  ↓ (generates dataset for)
ADVANCED_DATASET_WORKFLOW
  ↓ (trains)
YOLO_RTX4060_MEMORY
  ↓ (optimized with)
RTX4060_OPTIMIZATION
```

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
| RTX4060_OPTIMIZATION.md | Optimization | 2026-03-20 | 2 | 14 KB |
| YOLO_RTX4060_MEMORY.md | Reference | 2026-03-20 | 3 | 16 KB |
| ADVANCED_DATASET_WORKFLOW.md | Workflow | 2026-04-06 | 4 | 18 KB |
| PARAMETRIK_ANALIZ_REHBERI.md | How-To | 2026-03-10 | 2 | 8 KB |
| BLENDER_BACKGROUNDS_GUIDE.md | How-To | 2026-03-18 | 1 | 7 KB |
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

### ML & YOLOv11
- [ADVANCED_DATASET_WORKFLOW.md](ADVANCED_DATASET_WORKFLOW.md) — Full training pipeline
- [YOLO_RTX4060_MEMORY.md](YOLO_RTX4060_MEMORY.md) — Memory optimization
- [ACADEMIC_REFERENCES.md](ACADEMIC_REFERENCES.md#4-yapay-zeka-ve-makine-öğrenmesi) — Theory (CNN, YOLOv11)

### Blender & Synthetic Data
- [BLENDER_BACKGROUNDS_GUIDE.md](BLENDER_BACKGROUNDS_GUIDE.md) — Background setup
- [RTX4060_OPTIMIZATION.md](RTX4060_OPTIMIZATION.md) — GPU optimization
- [ADVANCED_DATASET_WORKFLOW.md](ADVANCED_DATASET_WORKFLOW.md) — Full pipeline

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

### For ML Practitioners
1. [BLENDER_BACKGROUNDS_GUIDE.md](BLENDER_BACKGROUNDS_GUIDE.md) — Data prep
2. [ADVANCED_DATASET_WORKFLOW.md](ADVANCED_DATASET_WORKFLOW.md) — Full pipeline
3. [YOLO_RTX4060_MEMORY.md](YOLO_RTX4060_MEMORY.md) — Hardware optimization

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
