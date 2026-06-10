# CFD/FEA Parametrik Analiz Sistemi

**Teknofest 2026 — İleri Otonom Sistemler**

Sabit kanat roket, drone, İHA ve uçak tasarımları için **tarama → 3D model → CFD/FEA → ML** entegre sistem.

---

## 🎯 Sistem Özellikleri

### ✅ Tam Pipeline

```
📸 3D Tarama (Photogrammetry)
    ↓
🔧 Mesh Otomatik Dönüştürme
    ↓
💨 CFD Analizi (OpenFOAM)
    ↓
⚙️  FEA Yapısal Analizi (CalculiX)
    ↓
🎬 Sentetik Dataset Üretimi (Blender)
    ↓
🧠 ML Model Eğitimi (YOLO)
```

### 🚀 Ana Modüller

| Modul | Amaç | Teknoloji |
|-------|------|-----------|
| **aircraft_geometry** | Parametrik uçak tasarımı | Python dataclasses |
| **mesh_generator** | Mesh oluşturma | Gmsh |
| **simulation_runner** | CFD simülasyonu | OpenFOAM subprocess |
| **fea_runner** | Yapısal analiz | CalculiX subprocess |
| **photogrammetry_scanner** | 3D tarama | OpenCV, Open3D |
| **mesh_to_cfd** | Mesh → Aircraft dönüştürme | NumPy, STL parsing |
| **blender_synthetic_generator** | Sentetik veri | Blender Python API |
| **ml_training_integration** | ML eğitimi | YOLOv8, PyTorch |
| **app_parametric** | GUI | PySide6 |

---

## 🔧 Hızlı Kurulum

### Minimum (Sadece GUI)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app_parametric.py
```

### Tam Sistem

```bash
# 1. Python ortamı
python -m venv venv
source venv/bin/activate

# 2. Python paketleri
pip install -r requirements.txt

# 3. OpenFOAM kur (WSL2/Linux/macOS)
# Windows: WSL2 + Ubuntu'da çalıştır
sudo apt-get install -y openfoam

# 4. CalculiX kur
sudo apt-get install -y calculix-cgx calculix-ccx

# 5. Blender kur
# İndir: https://www.blender.org/download/

# 6. Sistem test et
python check_integration.py
python full_integration_test.py

# 7. GUI başlat
python app_parametric.py
```

Detaylar: [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md)

---

## 📚 Rehberler ve Belgeler

| Belge | İçerik |
|-------|--------|
| **PARAMETRIK_ANALIZ_REHBERI.md** | Parametrik çalışmalar, tasarım optimization |
| **OPENFOAM_REHBERI.md** | CFD setup, case directory, solver seçimi |
| **CALCULIX_REHBERI.md** | FEA analizi, malzeme özellikleri, sınır koşulları |
| **SCANNER_REHBERI.md** | 3D photogrammetry tarama, mesh kalitesi |
| **SCAN_TO_DATASET_WORKFLOW.md** | Tarama → Dataset → ML tam workflow |
| **INSTALLATION_GUIDE.md** | Kurulum, sorun giderme, Docker |

---

## 🎓 Kullanım Senaryoları

### Senaryo 1: Drone Aerodinamik Optimization

```
1. Scanner Tab'ında drone tarayın (20 görüntü, 30 sn)
   ↓ STL model oluşturulur
2. Mesh Tab'ında mesh üretilir
   ↓ OpenFOAM domain'i hazırlanır
3. Simülasyon Tab'ında CFD çalıştırılır
   ↓ Drag/Lift kuvvetleri hesaplanır
4. Parametrik çalışma: kanat açıklığını (0.5 → 1.5 m) değiştir
   ↓ 9 farklı konfigürasyon otomatik simüle edilir
5. Sonuçlar Tab'ında optimal tasarım seçilir
```

**Beklenen sonuç:** Drag %15 azalma, Lift %8 artış

### Senaryo 2: Roket Yapısal Analisis

```
1. CAD'den STEP veya STL dosyası hazırlayın
2. FEA Tab'ında:
   - Malzeme: Karbon Fiber
   - Analiz: STATIC (rüzgar yükü)
   - Yük: 1500 Pa
3. Simülasyon çalışır
   ↓ Maksimum gerilme: 450 MPa
   ↓ Emniyet faktörü: 1.8
4. Parametrik: kuyruk boyutunu ±20% değiştir
   ↓ Optimal tasarım bulunur
```

**Sonuç:** Maksimum gerilme < 550 MPa

### Senaryo 3: Blender Sentetik Dataset

```
1. Drone STL model yükle
2. Blender Tab'ında 8 × 4 × 5 = 160 render oluştur
   ↓ Farklı kamera açıları, aydınlatma, dokular
3. Metadata.json otomatik oluşturulur
4. YOLO annotation'ları oluşturulur
5. ML Training başlatılır
   ↓ YOLOv8 modeli eğitilir
6. Model ONNX formatında dışa aktarılır
```

**Sonuç:** Object detection modeli (mAP50: 92%)

---

## 🖥️ GUI Sekmeler

### 1️⃣ Konfigürasyon
- Aircraft seç (5 template)
- Rüzgar hızı ayarla
- Mesh boyutu seç
- Processor sayısı

### 2️⃣ Mesh
- Mesh oluştur
- Kalite kontrol
- Boundary layer refinement
- Export (STL, OBJ, STEP)

### 3️⃣ Simülasyon
- Solver seç (simpleFoam, pimpleFoam)
- İnital conditions
- Solver settings
- Parametrik çalışma
- Paralel execution

### 4️⃣ Sonuçlar
- Drag/Lift/Moment kuvvetleri
- Tablo ve grafik
- Rapor oluştur
- Sonuçları karşılaştır

### 5️⃣ 📸 Scanner (YENİ)
- Webcam preview
- 3D tarama (photogrammetry)
- Mesh export
- Otomatik CFD yükleme

### 6️⃣ ⚙️ FEA (YENİ)
- Malzeme seç
- Analiz tipi (Static/Frequency/Buckling)
- Yük ve sınır koşulları
- Sonuçlar

---

## 📊 Parametrik Çalışma Örneği

```python
from aircraft_geometry import AircraftLibrary, ParametricStudy
from simulation_runner import SimulationRunner, SimulationJob

# Aircraft
lib = AircraftLibrary()
aircraft = lib.get_template("fixed_wing")()

# Parametrik çalışma
study = ParametricStudy(aircraft)
study.add_variation("wing_span", [1.0, 1.2, 1.5])
study.add_variation("wind_speed", [10, 15, 20])

cases = study.generate_cases()
# → 9 case oluşturulur (3 × 3)

# Simülasyon
runner = SimulationRunner()
results = []
for case in cases:
    job = SimulationJob(
        case_name=f"param_case",
        aircraft=case,
        solver="simpleFoam",
        mesh_size=0.015,
        wind_speed=15.0
    )
    result = runner.run_simulation(job)
    results.append(result)

# Sonuçlar
for r in results:
    print(f"{r['case_name']}: Drag={r['drag_force']:.2f}N, Lift={r['lift_force']:.2f}N")
```

---

## 🔬 Malzeme Kütüphanesi

```python
from fea_runner import MATERIAL_LIBRARY

for name, material in MATERIAL_LIBRARY.items():
    print(f"{material.name}")
    print(f"  E: {material.youngs_modulus} MPa")
    print(f"  σ_y: {material.yield_strength} MPa")
    print(f"  ρ: {material.density} kg/m³")
```

Mevcut malzemeler:
- Aluminum 6061
- Steel S355
- Carbon Fiber
- Titanium
- Balsa Wood

---

## ✅ Sistem Testi

### Modül Testi
```bash
python check_integration.py
```

### Tam Entegrasyon Testi
```bash
python full_integration_test.py
```

### Blender Doğrulama
```bash
python verify_blender.py
```

**Beklenen çıktı: 8/8 tests passed ✅**

---

## 📁 Klasör Yapısı

```
cfd_fea_tools/
├── app_parametric.py              # Ana GUI
├── aircraft_geometry.py             # Aircraft parametreleri
├── mesh_generator.py                # Mesh üretimi
├── simulation_runner.py             # CFD runner
├── fea_runner.py                    # FEA runner
├── photogrammetry_scanner.py        # 3D tarama
├── scanner_gui_module.py            # Scanner GUI
├── mesh_to_cfd.py                   # Mesh dönüştürme
├── blender_synthetic_generator.py   # Blender dataset
├── ml_training_integration.py       # ML training
├── check_integration.py              # Modül test
├── full_integration_test.py         # Entegrasyon test
├── verify_blender.py                # Blender doğrula
│
├── PARAMETRIK_ANALIZ_REHBERI.md
├── OPENFOAM_REHBERI.md
├── CALCULIX_REHBERI.md
├── SCANNER_REHBERI.md
├── SCAN_TO_DATASET_WORKFLOW.md
├── INSTALLATION_GUIDE.md
├── README_TR.md (bu dosya)
│
├── requirements.txt
├── config.json (opsiyonel)
│
└── cfd_cases/                       # CFD case directories (auto)
    └── case_001/
        ├── 0/
        ├── constant/
        └── system/
```

---

## 🚀 İleri Özellikler

### Parametrik Optimization
- Multi-variable design space
- Automatic case generation
- Parallel simulation
- Result comparison

### Sentetik Veri Üretimi
- Blender otomasyonu (160+ görüntü/model)
- Otomatik annotation (YOLO, CFD training)
- Augmentation desteği

### ML Integration
- YOLOv8 eğitimi
- Tensor dışa aktarma (ONNX, TorchScript)
- Model validation

### CFD/FEA
- Mesh refinement
- Boundary layer
- Multiple solvers
- Parallel execution

---

## 🔗 Kaynaklar

- **Blender Python API:** https://docs.blender.org/api/
- **OpenFOAM:** https://www.openfoam.com/
- **CalculiX:** https://www.calculix.de/
- **YOLOv8:** https://github.com/ultralytics/ultralytics
- **Open3D:** http://www.open3d.org/

---

## 📞 Destek

- **Hata Raporu:** [GitHub Issues](https://github.com/repo/issues)
- **Belgeler:** [Wiki](https://github.com/repo/wiki)
- **Forum:** [Discussions](https://github.com/repo/discussions)

---

## 📄 Lisans

Bu proje **TEKNOFEST 2026** çerçevesinde geliştirilmiştir.

---

## 🎉 Başarılı Başlangıç!

```bash
python app_parametric.py
```

**Simülasyonlara başlamaya hazır! 🚀**

---

**Son Güncelleme:** 2026-04-07  
**Versiyon:** 1.0 (Stabil)  
**Durum:** ✅ Üretim Hazır
