# 📚 OpenFOAM + CalculiX Öğrenim Yol Haritası

**Bilsem_beyin CFD/FEA Sistemine Entegre**

**Tarih:** 2026-04-07  
**Hedef:** Açık kaynak simülasyon ortamında uzmanlaşma

---

## 🔵 OpenFOAM (CFD — Computational Fluid Dynamics)

### Temel Seviye

#### 1. **The OpenFOAM Technology Primer**
   - Yazarlar: Tomislav Marić, Jens Höpken, Kyle Mooney
   - **EN İYİ başlangıç kitabı**
   - Kod yapısı, sınıf hiyerarşisi, derleme mantığı
   - Bilsem_beyin mesh_generator + simulation_runner ile paralel git

#### 2. **Mathematics, Numerics, Derivations and OpenFOAM®**
   - Yazar: Tobias Holzmann
   - **ÜCRETSİZ PDF:** holzmann-cfd.com
   - Matematikten → Sayısal yöntemden → OpenFOAM koduna doğru
   - **Başlangıç için mükemmel**

#### 3. **An Introduction to Computational Fluid Dynamics**
   - Yazarlar: Versteeg & Malalasekera
   - OpenFOAM'daki FVM (Finite Volume Method) teorik temeli
   - CFD fundamentals

### Orta Seviye

#### 4. **The Finite Volume Method in CFD**
   - Yazarlar: Moukalled, Mangani & Darwish
   - **OpenFOAM ile paralel gider**
   - Her bölümde OpenFOAM implementasyonuna atıf
   - 900+ sayfa, her satırı altın

#### 5. **Computational Methods for Fluid Dynamics**
   - Yazarlar: Ferziger & Perić
   - SIMPLE, PISO, PIMPLE algoritmalarının temelini öğren
   - **Bilsem_beyin:** Solver seçimi (simpleFoam, pimpleFoam)

### İleri Seviye / Türbülans

#### 6. **Turbulence Modeling for CFD**
   - Yazar: David C. Wilcox
   - k-ε, k-ω, SST, LES, DES
   - **Bilsem_beyin MESH_THEORY_GUIDE:** k-ω SST seçiminin temeli

#### 7. **Turbulent Flows**
   - Yazar: Stephen B. Pope
   - LES / DNS yapacaksan **mutlaka**

### 🌐 Online Kaynaklar (Ücretsiz)

| Kaynak | Açıklama | Bilsem_beyin İlişkisi |
|--------|----------|----------------------|
| **CFD Direct – User Guide** | Resmi OpenFOAM dokümantasyonu | Referans |
| **Wolf Dynamics Tutorials** | Adım adım tutorial'lar, PDF slaytlar | Mesh generator örnekleri |
| **Tobias Holzmann PDF** | holzmann-cfd.com → ÜCRETSİZ | Temel kitap |
| **József Nagy – YouTube** | OpenFOAM tutorial serileri | Video ders |
| **Fluid Mechanics 101 – YouTube** | Akin Peker (Türk!), CFD + OpenFOAM | Türkçe kaynak! |
| **CFD Online Forum** | Hata aldığında ilk bakacağın yer | Community |
| **OpenFOAM Wiki** | Solver seçimi, BC referansları | simulation_runner.py |
| **snappyHexMesh / cfMesh** | Mesh oluşturma rehberleri | mesh_generator.py |

### 🛠️ Praktik Yol Haritası (OpenFOAM)

```
Seviye 1: Temel Akış
└─ cavity tutorial (icoFoam)
   → Laminar incompressible flow
   → Bilsem_beyin: Re < 1000 testleri

Seviye 2: Türbülanslı Akış
└─ pitzDaily (simpleFoam)
   → RANS turbulence modelling
   → Bilsem_beyin: MESH_THEORY_GUIDE (k-ω SST)

Seviye 3: Çok Fazlı Akış
└─ damBreak (interFoam)
   → İki fazlı akış (hava + su)
   → Uçak etrafında çift fazlı etkiler

Seviye 4: Gerçek Geometri
└─ motorBike (snappyHexMesh + simpleFoam)
   → Parametrik geometri meshlemesi
   → Bilsem_beyin: aircraft_geometry.py integration

Seviye 5: Kendi Solver Yaz
└─ C++ + OpenFOAM API
   → İleri araştırma
```

---

## 🟢 CalculiX (FEA — Finite Element Analysis)

### CalculiX Spesifik

#### 1. **CalculiX USER'S MANUAL**
   - Yazar: Guido Dhondt
   - **Resmi dokümantasyon, ÜCRETSİZ**
   - http://www.calculix.de
   - Her eleman tipi, her *KEYWORD detaylı
   - **Bilsem_beyin:** fea_runner.py referansı

#### 2. **CalculiX CrunchiX USER'S MANUAL**
   - Solver (CCX) detaylı açıklaması
   - Nonlineer analiz, termal, kontak
   - **Material database** ile kontak!

#### 3. **FEA Tutorial Serisi**
   - Feaforall.com → CalculiX tutorial serileri çok iyi
   - Adım adım örnekler
   - PrePoMax GUI kullanımı

### FEA Teorisi (CalculiX Uyumlu)

#### 4. **Finite Element Procedures**
   - Yazar: Klaus-Jürgen Bathe
   - CalculiX'in solver mantığı Abaqus/NASTRAN benzeri
   - **ÜCRETSİZ PDF:** Bathe MIT sitesinde
   - **Bilsem_beyin:** Material properties → FEA solver

#### 5. **A First Course in FEM**
   - Yazar: Daryl L. Logan
   - Temel FEA matematiği, giriş seviyesi
   - Displacement methods, Galerkin

#### 6. **Nonlinear FE for Continua and Structures**
   - Yazarlar: Belytschko, Liu, Moran
   - Büyük deformasyon, plastiklik, kontak
   - **Bilsem_beyin:** Material nonlinearity

#### 7. **Introduction to the Mechanics of a Continuous Medium**
   - Yazar: Malvern
   - Sürekli ortamlar mekaniği temeli
   - Stress-strain tensör temeleri

### 🌐 Online Kaynaklar (Ücretsiz)

| Kaynak | Açıklama | Bilsem_beyin İlişkisi |
|--------|----------|----------------------|
| **calculix.de** | Resmi site, manual + örnekler | Ana referans |
| **feaforall.com** | CalculiX tutorial'ları, video + yazılı | Uygulamalı ders |
| **bConverged** | YouTube CalculiX + PrePoMax serileri | Video tutorial |
| **PrePoMax** | CalculiX EN İYİ GUI (Abaqus benzeri) | Pre-processing |
| **Mecway** | Alternatif GUI (ücretli ama ucuz) | Option |
| **CGX (CalculiX GraphiX)** | Resmi pre/post processor | Post-processing |
| **FreeCAD FEM Workbench** | FreeCAD içinden CalculiX çalıştırma | CAD integration |
| **GitHub – mkraska** | CalculiX örnek kütüphanesi | Code examples |

### 🛠️ Pratik Yol Haritası (CalculiX)

```
Seviye 1: Lineer Statik
└─ Basit çubuk çekme testi
   → Displacement BC, concentrated loads
   → Bilsem_beyin: material_database → σ_y doğrulama

Seviye 2: Kabuk Elemanlar
└─ Plaka eğilme
   → Bending stress, deflection
   → Aircraft wing analysis

Seviye 3: Termal Analiz
└─ Isı transferi
   → Temperature-dependent properties
   → thermal_conductivity (material_database)

Seviye 4: Kontak Problemi (Nonlineer)
└─ Surface contact, friction
   → Lagrange multiplier method
   → Bilsem_beyin: Contact BC

Seviye 5: Modal Analiz
└─ Doğal frekanslar (eigenvalue problem)
   → Mode shapes, natural frequencies
   → Bilsem_beyin: FEA frequency analysis tab

Seviye 6: Büyük Deformasyon
└─ Geometrik nonlineerlik
   → Nlgeom=YES in CalculiX
   → Bilsem_beyin: Nonlinear FEA runner

Seviye 7: Dinamik Analiz
└─ Transient, time integration
   → Runge-Kutta, Newmark methods
```

---

## 🔥 OpenFOAM + CalculiX Coupling (FSI)

### Fluid-Structure Interaction Gerekirse

#### preCICE Kütüphanesi

| Kaynak | Açıklama |
|--------|----------|
| **precice.org** | Resmi site, tutorial'lar mükemmel |
| **preCICE Tutorials** | OpenFOAM ↔ CalculiX FSI örnekleri hazır |
| **Perpendicular Flap Tutorial** | Başlangıç için ideal FSI problemi |
| **preCICE Discourse Forum** | Topluluk desteği çok aktif |

#### FSI Kitapları

1. **Fluid-Structure Interaction**
   - Yazarlar: Bungartz & Schäfer (Springer)

2. **Computational Methods for FSI**
   - Yazarlar: Bazilevs, Takizawa, Tezduyar

### FSI Uygulamaları (Bilsem_beyin İlişkili)

```
Flight Dynamics:
  CFD: OpenFOAM (aerodynamic forces)
  ↕ (coupling via preCICE)
  FEA: CalculiX (structural deformations)
  ↕
  → Wing flutter, aeroelasticity
  → Aircraft response to gusts
  
VTOL Rotor FSI:
  CFD: Rotating mesh (MRF in OpenFOAM)
  ↕
  FEA: Blade structural response
  ↕
  → Blade fatigue prediction
  → Stability analysis
```

---

## 📌 SANA ÖZEL YOL HARITASI

### Seviye 1: Temel (1-2 ay)

```
HAFTA 1-2: Giriş
├── Holzmann PDF (holzmann-cfd.com) oku
├── cavity tutorial çalıştır (icoFoam)
│   → D:\bilsem_beyin\...
├── Bathe FEM PDF kısımlarını oku
└── PrePoMax kur

HAFTA 3-4: Uygulama
├── bilsem_beyin mesh_generator.py kodunu anla
├── aircraft_geometry.py öğren
├── FEA: PrePoMax ile simple cantilever beam testi yap
└── Sonuçları material_database.py ile karşılaştır
```

### Seviye 2: Orta (2-3 ay)

```
AYLAR 2-3: İleri Öğrenim
├── CFD:
│   ├── Moukalled kitabı (The Finite Volume Method)
│   ├── motorBike tutorial
│   ├── snappyHexMesh ile mesh oluşturma
│   └── simpleFoam solver seçimi
│
├── FEA:
│   ├── feaforall.com tutorial serileri
│   ├── Nonlineer kontak problemi
│   ├── Termal + mekanik coupling
│   └── Modal analiz
│
└── Bilsem_beyin:
    ├── Mesh sensitivity analizi yap
    ├── Material database genişlet
    ├── Custom materials ekle
    └── ParaView post-processing
```

### Seviye 3: İleri (3-6 ay)

```
AYLAR 4-6: Uzmanlaşma
├── CFD:
│   ├── k-ω SST turbulence modeling derinlemesine
│   ├── Kendi solver yazma (OpenFOAM API)
│   └── LES/DES türbülans modelleri
│
├── FEA:
│   ├── Dinamik analiz (modal dynamics)
│   ├── Büyük deformasyon plastisitesi
│   ├── Kontak ve friction detaylı
│   └── Termal-mekanik coupling
│
└── Integration:
    ├── preCICE ile FSI kuruluşu
    ├── OpenFOAM + CalculiX coupling
    ├── Parametrik çalışma otomasyonu
    └── HPC (paralel hesaplama)
```

### Seviye 4: Uzman (6+ ay)

```
AYLARI 7+: Araştırma Seviyesi
├── Machine Learning:
│   ├── PINN (Physics-Informed NN)
│   ├── ROM (Reduced Order Models)
│   └── Surrogate models
│
├── Optimization:
│   ├── Dakota / OpenMDAO tasarım optimizasyonu
│   ├── Adjoint methods
│   └── Parametrik design automation
│
├── HPC:
│   ├── MPI parallelization
│   ├── GPU acceleration (CUDA)
│   └── Cluster computing
│
└── Publication-Level Research
```

---

## 🎯 BILSEM_BEYIN İNTEGRASYON NOKTALARI

### CFD (OpenFOAM)

**Bilsem_beyin Dosyaları → OpenFOAM Kurulumu:**

```python
# simulation_runner.py
SimulationRunner
  ├── solver_type: ["simpleFoam", "pimpleFoam", "rhoCentralFoam"]
  ├── wind_speed: 15 m/s (Re hesaplaması için)
  └── turbulence_model: "kOmegaSST" (MESH_THEORY_GUIDE referans)

# mesh_generator.py
MeshGenerator
  ├── y⁺ = 27.7 (Holzmann + Wilcox from literature)
  ├── boundary_layer: 10 layers, r=1.2
  └── domain_size: 5L (Moukalled best practice)
```

**Öğrenim → Uygulama:**
1. Holzmann PDF oku (FVM theory)
2. cavity + motorBike tutorial çalıştır
3. Bilsem_beyin mesh parametrelerini anla
4. Kendi geometriler için mesh oluştur

### FEA (CalculiX)

**Bilsem_beyin Dosyaları → CalculiX Kurulumu:**

```python
# fea_runner.py
FEASimulationRunner
  ├── material: MATERIAL_LIBRARY (material_database.py)
  ├── analysis_type: ["STATIC", "FREQUENCY", "BUCKLING"]
  ├── youngs_modulus: E (GPa)
  ├── poisson_ratio: ν
  └── yield_strength: σ_y

# material_database.py
MaterialProperties
  ├── E → K = E/(3(1-2ν))  [Bathe FEM]
  ├── ν → G = E/(2(1+ν))   [Continuum mechanics]
  └── σ_y → Safety Factor  [Material strength]
```

**Öğrenim → Uygulama:**
1. Bathe PDF oku (FEM theory)
2. PrePoMax ile basit testler yap
3. Material properties ile FEA çalıştır
4. Bilsem_beyin material database genişlet

### Entegrasyon: Mesh Parametreleri

**MESH_THEORY_GUIDE.md ↔ OpenFOAM Dokümantasyonu:**

```
y⁺ = 27.7
  ← Wilcox "Turbulence Modeling for CFD"
  → OpenFOAM snappyHexMesh BoundaryLayer field
  → Bilsem_beyin mesh_generator.py: hwall_n = 0.001

Re = 6×10⁵
  ← Ferziger & Perić SIMPLE/PISO algorithms
  → OpenFOAM solver seçimi (simpleFoam uyumlu)
  → Bilsem_beyin simulation_runner.py turbulence_model

Domain = 5L
  ← Moukalled "Finite Volume Method in CFD"
  → OpenFOAM createPatchDict configuration
  → Bilsem_beyin mesh_generator.py domain_size
```

---

## 📊 KAYNAK ÖZETİ

### Kitaplar (İndirme Linkeri)

| Kitap | Link | Durum |
|-------|------|-------|
| Holzmann PDF | holzmann-cfd.com | ✅ ÜCRETSİZ |
| Bathe PDF | mit.edu (yazar sitesi) | ✅ ÜCRETSİZ |
| Wilcox Turbulence | Springer / Amazon | 💰 Ücretli (~$150) |
| Moukalled FVM | Springer | 💰 Ücretli (~$180) |
| Logan FEM | Cengage | 💰 Ücretli (~$100) |

### Online Kurslar

| Platform | Kurs | Dil |
|----------|------|-----|
| YouTube (József Nagy) | OpenFOAM Tutorials | EN |
| YouTube (Fluid Mechanics 101) | CFD + OpenFOAM | EN |
| YouTube (bConverged) | PrePoMax + CalculiX | EN |
| Udemy | OpenFOAM kursları | EN |
| CFD Online | Forum + discussions | EN |

### Komunite & Forum

```
CFD Online Forum → www.cfd-online.com
  Hata aldığında ilk bakacağın yer
  OpenFOAM + CalculiX soruları yanıtlanır

preCICE Discourse → precice.org/community
  FSI coupling sorularına yanıt verir

OpenFOAM Wiki → openfoamwiki.net
  Solver seçimi, boundary conditions

CalculiX Forum → calculix.de (community bölümü)
  CalculiX specific sorunları
```

---

## ✅ CHECKLIST: İlk 2 Hafta

```
HAFTA 1:
 [ ] Holzmann PDF indir ve bölüm 1-3 oku
 [ ] OpenFOAM 11 kur (EXTERNAL_TOOLS_SETUP.md)
 [ ] cavity tutorial çalıştır
 [ ] Bathe FEM PDF bölüm 1 oku
 [ ] PrePoMax kur

HAFTA 2:
 [ ] cavity sonuçlarını anla (SIMPLE algorithm)
 [ ] mesh_generator.py kodunu oku
 [ ] MESH_THEORY_GUIDE.md oku
 [ ] PrePoMax: basit cantilever beam mesh + solve
 [ ] material_database.py kodunu oku
```

---

## 🎓 SONUÇ

Bu yol haritası **bilsem_beyin sistem tasarımcısı** olmanı hedefler:

- **Mesh oluşturma:** Teorik + pratik
- **CFD simülasyon:** OpenFOAM master
- **FEA analizi:** CalculiX + material database
- **Coupling:** preCICE FSI
- **Optimization:** Design automation
- **Publication:** Araştırma kalitesi

**Tahmini zaman:** 6-12 ay yoğun çalışma
**Hedef seviye:** İleri CFD/FEA mühendisliği

---

**Başlangıç:** Holzmann PDF (holzmann-cfd.com)  
**Paralel:** Bathe PDF + cavity tutorial  
**Bilsem_beyin:** mesh_generator.py + material_database.py öğren

**Başarılar!** 🚀

---

**Versiyon:** 1.0  
**Tarih:** 2026-04-07  
**Proje:** bilsem_beyin CFD/FEA/ML v2.0
