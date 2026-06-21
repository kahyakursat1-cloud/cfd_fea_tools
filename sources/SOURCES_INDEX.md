# Akademik Kaynaklar — Merkezi Rehber

> ℹ️ **Not (2026-06-21):** YOLO/CNN/sentetik-veri (görüntü-işleme) kaynakları artık ayrı kod-tabanına aittir → `../goruntu_isleme/`. Buradaki ML/görü atıfları o depoyla ilgilidir.

**Konumu:** `D:\bilsem_beyin\cfd_fea_tools\sources\`  
**Tarih:** 2026-04-07  
**Durum:** ✅ Merkezileştirilmiş ve organize

---

## 📚 Kaynaklar Özeti

| Kategori | Dosya Sayısı | Toplam Boyut | Başlıklar |
|----------|---|---|---|
| **Yarışma Şartnameleri** | 11 | 23 MB | TEKNOFEST, SDT, İHA, vb. |
| **ArXiv Makaleleri** | 23 | ~430 MB | (raw klasöründe) |
| **FAA Kılavuzları** | 7 | ~600 MB | (raw klasöründe) |
| **Türkçe Bilgiler** | 3 | 15+ MB | Bilsem donanımı, vb. |

---

## 1️⃣ Yarışma Şartnameleri (Resmi)

### TEKNOFEST 2026 — İleri Otonom Sistemler

**Dosya:** `Ileri_Otonom_Sistemler_Tasarım_ve_Operasyon_Yarismasi_TR_Sartname_OWUI0.pdf`

**İçerik:**
- Yarışma hedefleri ve katılım koşulları
- Teknik gereksinimler (IHA, İKA, YKS)
- Jüri kriterleri ve puanlama
- Tarihler: ÖDR (20 Nisan), DDR (15 Temmuz), FDR (21 Eylül)

**Proje Bağlantısı:**
- bilsem_beyin CFD/FEA sistemi, IHA tasarım optimizasyonunda kullanılır
- Parametrik analiz → Aerodynamic tuning → İHA performansı artışı

---

### Diğer Yarışmalar

| Dosya | Amaç |
|-------|------|
| `2026_HAVACILIKTA_YAPAY_ZEKA_TEKNIK_SARTNAME_TR_v1_2026_02_21_W48vr.pdf` | AI in Aviation — YOLOv11 object detection |
| `2026_SAVASAN_İHA_YARISMA_SARTNAMESİ_TR_20_02_V2_0eVi5.pdf` | Autonomous UAV Combat Drone |
| `2026_SAVASAN_IHA_AVCI_DRON_YARISMA_SARTNAMESİ_TR_LndcA.pdf` | Hunter Drone (AI-based tracking) |
| `2026_İHA_Yarışmaları_Şartnamesi_TR_v2_w4Fdp.pdf` | General UAV Competition |
| `2026_İNSANSIZ_SU_ALTI_SİSTEMLERİ_YARIŞMASI_-_TÜRKÇE_Y5D0m.pdf` | Underwater Drone Systems |
| `2026_TARIM__TEKNOLOJİLERİ_YARIŞMASI_ŞARTNAMESİ_TR_V1.3_dvWyA.pdf` | Agricultural Technology |
| `2026_Çelikkubbe_Hava_Savunma_Sistemleri_Yarışması_Şartname_TR_v1.3_4gIOX.pdf` | Air Defense Systems |
| `2025_SDT_SARTNAMESİ_TR_IdNxf.pdf` | 2025 Design & Technology |
| `2026_2204_D_Lise_Öğrencileri_İklim_Değişikliği_Araştırma_Projeleri_Yarışma.pdf` | High School Climate Research |
| `TEKNOFEST_2026_TEKNIK_SARTNAMESI_FPV_DRONE_İZLEME_YARISMASI__SDv30.pdf` | FPV Drone Tracking Competition |

---

## 2️⃣ ArXiv Makaleleri (Başlık Kategorisine Göre)

**Konum:** `D:\bilsem_beyin\raw\`

### A) MiniHawk UAV & Sabit Kanat CFD

| Dosya | Başlık | İlgili Konu |
|-------|--------|-------------|
| `ArXiv_Latest_MiniHawk_UAV_CFD_1_Physics-infused_Learning_for_Aerial_Manipulator_in_Winds_and_Near.pdf` | Physics-infused Learning for Aerial Manipulator in Winds | **CFD** + **ML** |

**Önemli:** Physics-based learning (PINNs) ile CFD sonuçlarını iyileştirme

---

### B) Model Roket Dinamiği

| Dosya | Başlık | İlgili Konu |
|-------|--------|-------------|
| `ArXiv_Latest_Model_Roket_Dinamik_1_Amortized_Inference_for_Model_Rocket_Aerodynamics_Learning_to_Est.pdf` | Amortized Inference for Model Rocket Aerodynamics | **CFD** surrogate model |
| `ArXiv_Latest_Model_Roket_Dinamik_2_Wake_Vectoring_for_Efficient_Morphing_Flight.pdf` | Wake Vectoring for Efficient Morphing Flight | **Parametrik tasarım** |
| `ArXiv_Latest_Model_Roket_Dinamik_3_Aerothermodynamic_Simulators_for_Rocket_Design_using_Neural_Field.pdf` | Aerothermodynamic Simulators for Rocket Design using Neural Fields | **CFD** + **Neural Networks** |

**İlişkiler:**
- Surrogate Model ile CFD hızlandırma
- Wake modeling (uyanış modellemesi)
- Neural field (Physics-Informed Neural Networks)

**Proje Uygulaması:** 
- Roket gövdesinin CFD analizi
- Parametrik optimizasyon (9 konfigürasyon × hız)
- FEA (structural integrity check)

---

### C) Nesne Algılama (YOLO)

| Dosya | Başlık | İlgili Konu |
|-------|--------|-------------|
| `ArXiv_Latest_Nesne_Algilama_YOLO_1_Deep_Neural_Network_Based_Roadwork_Detection_for_Autonomous_Drivi.pdf` | Deep NN-Based Roadwork Detection for Autonomous Driving | **Real-time detection** |
| `ArXiv_Latest_Nesne_Algilama_YOLO_2_A_Robust_Deep_Learning_Framework_for_Bangla_License_Plate_Recogni.pdf` | Robust DL Framework for License Plate Recognition | **Transfer learning** |
| `ArXiv_Latest_Nesne_Algilama_YOLO_3_A_Lightweight_Digital-Twin-Based_Framework_for_Edge-Assisted_Vehi.pdf` | Lightweight Digital-Twin Framework for Edge-Assisted Vehicles | **Edge AI** + **YOLOv11** |

**Proje Uygulaması:**
- YOLOv11 Nano @ 1280×720
- Edge deployment (Jetson Orin, RTX 4060)
- Real-time inference (30-45ms)

---

### D) İHA Sistemleri (Savasan)

| Dosya | Başlık | İlgili Konu |
|-------|--------|-------------|
| `ArXiv_Latest_Savasan_IHA_1_Orientation_Matters_Learning_Radiation_Patterns_of_Multi_Rotor_UA.pdf` | Orientation Matters: Learning Radiation Patterns | **Communication/Control** |
| `ArXiv_Latest_Savasan_IHA_2_Communication-Aware_Multi-Agent_Reinforcement_Learning_for_Decent.pdf` | Communication-Aware Multi-Agent RL | **Otonom Kontrol** |
| `ArXiv_Latest_Savasan_IHA_3_Occupation-Measure_Mean-Field_Control_Optimization_over_Measures.pdf` | Occupation-Measure Mean-Field Control Optimization | **Kontrol Sistemleri** |

---

### E) Gezegen Bilimi & Astronomi

| Dosya | Başlık | İlgili Konu |
|-------|--------|-------------|
| `ArXiv_Latest_Gezegen_Bilimi_Astronomi_1_The_PLATO_Science_Calibration_and_Validation_Plan_Targets_for_the.pdf` | PLATO Calibration & Validation Plan | Space systems |
| `ArXiv_Latest_Gezegen_Bilimi_Astronomi_2_Interaction_between_Winds_from_Weak-lined_T_Tauri_Stars_with_Exop.pdf` | Interaction of Winds & Exoplanets | Astrophysics |
| `ArXiv_Latest_Gezegen_Bilimi_Astronomi_3_Discovery_of_a_Low-Mass_Companion_to_the_Accelerating_Star_HIP_53.pdf` | Discovery of Low-Mass Companion | Astronomy |

---

### F) Uydu Sistemleri & Uzay Mühendisliği

| Dosya | Başlık | İlgili Konu |
|-------|--------|-------------|
| `ArXiv_Latest_Uydu_Sistemleri_Spacecraft_1_Assessing_VBz_variations_during_CME_propagation_a_preparatory_stu.pdf` | VBz Variations During CME Propagation | Space weather |
| `ArXiv_Latest_Uydu_Sistemleri_Spacecraft_2_Calibration_of_key_parameters_during_the_in-orbit_phase_for_the_T.pdf` | In-Orbit Calibration of Spacecraft | Satellite systems |
| `ArXiv_Latest_Uydu_Sistemleri_Spacecraft_3_Route-Phasing-Split-Encoded_Genetic_Algorithm_for_Multi-Satellite.pdf` | Genetic Algorithm for Multi-Satellite Routing | Optimization |

---

### G) Uzay Yörünge Mekaniği

| Dosya | Başlık | İlgili Konu |
|-------|--------|-------------|
| `ArXiv_Latest_Uzay_Yorunge_Mekanigi_1_Closed_Form_Expressions_for_the_Potentials_and_Accelerations_of_G.pdf` | Gravitational Potentials & Accelerations | Orbital Mechanics |
| `ArXiv_Latest_Uzay_Yorunge_Mekanigi_2_TESS_Investigation_--_Demographics_of_Young_Exoplanets_TI-DYE_IV.pdf` | TESS Exoplanet Demographics | Astronomy |
| `ArXiv_Latest_Uzay_Yorunge_Mekanigi_3_On_the_perturbed_harmonic_oscillator_and_celestial_mechanics.pdf` | Perturbed Harmonic Oscillator & Celestial Mechanics | Physics |

---

## 3️⃣ FAA Havacılık Kılavuzları (Temel Bilgi)

**Konum:** `D:\bilsem_beyin\raw\`

### Uçuş Prensiplerine Giriş

| Dosya | İçerik | Sayfa |
|-------|--------|-------|
| `FAA_PHAK_Ch4_Principles_of_Flight.pdf` | **Temel Prensipleri:** Lift, Drag, Thrust, Weight | 100+ |
| `FAA_PHAK_Ch5_Aerodynamics_of_Flight.pdf` | **Aerodinamik Detaylar:** Airfoil, Wing design, Stall | 150+ |
| `FAA_PHAK_Complete.pdf` | **Tam Pilot Kılavuzu:** Tüm havacılık konuları | 500+ |

**Proje İlişkisi:** Temel aerodinamik bilgisi → CFD validation

---

### Uçak Tipi Spesifik Kılavuzlar

| Dosya | Konu | İçerik |
|-------|------|--------|
| `FAA_Airplane_Flying_Handbook_Complete.pdf` | Sabit kanat uçak | Tasarım, Pilot kontrol, Performance |
| `FAA_Glider_Flying_Handbook_Complete.pdf` | Planör | Aerodinamik verimlilik, Termal dynamics |
| `FAA_Helicopter_Flying_Handbook_Complete.pdf` | Helikopter | Rotor aerodinamik, Hover dynamics |

**Uçak Tasarımı:**
- **Fixed-Wing:** FAA_Airplane_Flying_Handbook
- **VTOL:** FAA_Helicopter_Flying_Handbook
- **Flying Wing:** FAA_Glider_Flying_Handbook + efficiency

---

### Insansız Sistemler

| Dosya | Konu |
|-------|------|
| `FAA_Remote_Pilot_sUAS_Study_Guide.pdf` | UAS regulations, Safe operation, Airspace |

---

## 4️⃣ Türkçe Kaynaklar (Bilsem Seçimi)

**Konum:** `D:\bilsem_beyin\raw\`

| Dosya | İçerik | İlişki |
|-------|--------|--------|
| `bilsem_program.docx` | Bilsem eğitim programı | Ders müfredatı |
| `bilsem donanım.csv` | Mevcut donanım envanteri | RTX 4060, GPU specs |
| `bilsem donanım r1.csv` | Donanım R1 revizyon | Güncelleme |

---

## 🔗 Kaynaklar Arası Bağlantılar

### CFD (OpenFOAM)
```
ArXiv: Model Roket Aerodinamik (1, 2, 3)
FAA: Ch4-Ch5 (Principles of Flight)
Proje: simulation_runner.py, PARAMETRIK_ANALIZ_REHBERI.md
```

### FEA (CalculiX)
```
Proje: fea_runner.py, CALCULIX_REHBERI.md
Ders: Makine Dinamiği, Sayısal Yöntemler
```

### ML (YOLOv11)
```
ArXiv: Nesne Algılama (1, 2, 3)
Proje: ml_training_integration.py, blender_synthetic_generator_v2.py
Ders: Makine Öğrenmesi, Bilgisayar Vizyonu
```

### Parametrik Tasarım
```
ArXiv: Model Roket Dinamik 2 (Wake Vectoring)
Proje: aircraft_geometry.py
Ders: Tasarım Optimizasyonu
```

### İHA Tasarımı
```
FAA: Airplane/Helicopter Flying Handbook
ArXiv: MiniHawk UAV CFD, Savasan IHA
Proje: Tüm sistem
```

---

## 📖 Ders Müfredatı Haritası

| Ders | Kaynaklar | Proje Modülleri |
|------|-----------|-----------------|
| **Aerodinamik** | FAA Ch4-5, ArXiv (Roket) | CFD (OpenFOAM) |
| **Sayısal Yöntemler** | ACADEMIC_REFERENCES.md | FVM/FEM |
| **Makine Dinamiği** | ACADEMIC_REFERENCES.md | FEA (CalculiX) |
| **Kontrol Sistemleri** | ArXiv (Savasan IHA) | Autopilot tuning |
| **Makine Öğrenmesi** | ArXiv (YOLO), FAA sUAS | YOLOv11 training |
| **Bilgisayar Vizyonu** | ACADEMIC_REFERENCES.md | SfM, photogrammetry |
| **Tasarım Optimizasyonu** | ArXiv (Wake Vectoring) | Parametric studies |
| **Yazılım Mühendisliği** | - | GUI, Testing, Modularity |

---

## 🎓 Okuma Önerileri (Sıra)

### Başlangıç (Haftalar 1-2)
1. ✅ FAA_PHAK_Ch4 — Temel uçuş prensiplerine giriş
2. ✅ FAA_PHAK_Ch5 — Aerodinamik detaylar
3. ✅ ACADEMIC_REFERENCES.md (CFD bölümü)

### Orta Seviye (Haftalar 3-4)
4. ✅ ArXiv_Model_Roket_Dinamik_2 (Wake Vectoring) — Tasarım optimizasyonu
5. ✅ ArXiv_Latest_Nesne_Algilama_YOLO_3 — Edge AI
6. ✅ ACADEMIC_REFERENCES.md (FEA, ML bölümleri)

### İleri Seviye (Haftalar 5+)
7. ✅ FAA_Airplane_Flying_Handbook — Detaylı tasarım
8. ✅ ArXiv (MiniHawk, Savasan) — Advanced applications
9. ✅ ACADEMIC_REFERENCES.md (Fotogrametri, Optimizasyon)

---

## 📂 Dosya Organizasyonu

```
D:\bilsem_beyin\
├── cfd_fea_tools/
│   ├── sources/                          ← BURASI
│   │   ├── SOURCES_INDEX.md             ← Bu dosya
│   │   ├── 2026_*.pdf                   ← Yarışma şartnameleri (11)
│   │   └── [ArXiv & FAA ek olacak]
│   ├── ACADEMIC_REFERENCES.md           ← Teori + kitap/makale kaynakları
│   ├── README_TR.md
│   ├── SYSTEM_STATUS.md
│   └── [diğer belgeler...]
│
└── raw/                                  ← Orijinal kaynaklar (geçmiş)
    ├── ArXiv*.pdf                       ← 23 makale
    └── FAA*.pdf                         ← 7 kılavuz
```

---

## ✅ Kontrol Listesi — Kaynakları Kullanma

- [ ] ACADEMIC_REFERENCES.md okumak başladı
- [ ] Yarışma şartnamesi incelendi
- [ ] Relevan ArXiv makaleları işaretlendi
- [ ] FAA kılavuzları referans olarak eklenmiş
- [ ] CFD teorisi anlaşıldı (Navier-Stokes, RANS)
- [ ] FEA teorisi anlaşıldı (Elastisite, Galerkin)
- [ ] YOLOv11 mimarisi incelendi
- [ ] SfM algoritması öğrenildi
- [ ] Parametrik tasarım hedefleri belirlendi

---

## 🔍 Arama & Referans

### ArXiv Makalelerinde Arama
```bash
# Örnek: "CFD" anahtar kelimesine göre
grep -i "CFD\|simulation\|aerodynamic" sources/*.pdf

# Örnek: "model roket" konusu
ls sources/*Model_Roket*.pdf
```

### FAA Kılavuzlarında Arama
```bash
# Örnek: "Lift" ve "Drag"
grep -i "lift\|drag" sources/FAA_*.pdf
```

---

## 📝 Atıf Formatı

### ArXiv Makaleleri
```
[1] "Title of Paper", ArXiv Preprint, Date
Source: sources/ArXiv_Latest_Category_N_filename.pdf
```

### FAA Kılavuzları
```
[2] FAA Pilot's Handbook of Aeronautical Knowledge (PHAK)
Source: sources/FAA_PHAK_Chapter_N.pdf
```

### Yarışma Şartnameleri
```
[3] TEKNOFEST 2026 Teknik Şartnamesi — İleri Otonom Sistemler
Source: sources/Ileri_Otonom_Sistemler_Tasarım_ve_Operasyon_Yarismasi_TR_Sartname_OWUI0.pdf
```

---

## 🚀 Sonraki Adımlar

1. ✅ Kaynakları merkezi konuma taşıdı
2. ⏳ ArXiv & FAA PDFlerini sources/ klasörüne kopyalamak (opsiyonel)
3. ⏳ Makale özetleri eklemek (executive summaries)
4. ⏳ CrossRef ve DOI linklerini ekleme
5. ⏳ Interactive PDF indexing (ElasticSearch vb.)

---

**Durum:** ✅ Merkezileştirilmiş kaynaklar sistemi hazır  
**Son Güncelleme:** 2026-04-07  
**Versiyon:** 1.0
