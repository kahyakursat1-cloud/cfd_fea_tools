# Scan → 3D Model → Sentetik Dataset Workflow

**Tamamen Otomatik Veri Oluşturma Pipeline'ı**

---

## 🎯 Genel Akış

```
Adım 1: Gerçek Araç Tarama
   ↓ (Scanner GUI)
Adım 2: 3D Model Oluşturma (STL)
   ↓
Adım 3: Blender'a İçe Aktarma
   ↓
Adım 4: Sentetik Dataset Oluşturma
   ├─ 8 kamera açısı
   ├─ 4 aydınlatma varyantı
   ├─ 5 doku/renk
   └─ Toplam: 160 görüntü
   ↓
Adım 5: Metadata Oluşturma (JSON)
   ↓
Adım 6: ML Training Dataset Hazırlığı
   ├─ YOLO annotation
   ├─ CFD training data
   └─ Augmentation
```

---

## 📊 Workflow Detayı

### 1️⃣ TARAMA (Scanner GUI)

```
CFD Arayüzü → Scanner Tab
├─ Ayarlar: Kalite = Production
├─ Geri Sayım: 20 görüntü
├─ İşlem: 5-10 dakika
└─ Çıktı: drone.stl ✅
```

**Komut Satırında:**
```bash
python -c "
from photogrammetry_scanner import PhotogrammetryScanner, ScanConfig, MeshQuality
config = ScanConfig(num_images=20, quality=MeshQuality.PRODUCTION)
scanner = PhotogrammetryScanner(config)
success = scanner.run_full_pipeline()
if success:
    scanner.export_mesh('drone.stl')
"
```

### 2️⃣ BLENDER'DA SENTETIK VERİ

```
Blender → Python Script → Render ×160
├─ 8 Kamera Açısı (Dairesel)
├─ 4 Aydınlatma (Studio/3-Light/Low/Backlit)
├─ 5 Doku (Gray/Carbon/Metallic/White/Red)
└─ 5 dakika = 160 görüntü
```

**Komut:**
```bash
blender --python blender_synthetic_generator.py -- drone.stl ./dataset 8
```

### 3️⃣ METADATA OLUŞTURMASı

```json
{
  "mesh_file": "drone.stl",
  "created_date": "2026-04-07",
  "total_renders": 160,
  "renders": [
    {
      "filename": "Studio_1Light_Gray_Matte_View_00.png",
      "camera_view": "View_00",
      "lighting": "Studio_1Light",
      "texture": "Gray_Matte",
      "camera_location": [3.0, 0.0, 2.0],
      "resolution": "1280x720"
    },
    ...
  ]
}
```

---

## 💻 ÖRNEK KODLAR

### Python Workflow (Tüm Adımlar Otomatik)

```python
#!/usr/bin/env python3
"""
Tam Workflow: Scan → Blender → Dataset
"""

import subprocess
from pathlib import Path
from photogrammetry_scanner import PhotogrammetryScanner, ScanConfig, MeshQuality

# 1. SCAN
print("=" * 60)
print("ADIM 1: DRONE TARAMA")
print("=" * 60)

config = ScanConfig(
    num_images=20,
    quality=MeshQuality.PRODUCTION,
    voxel_size=0.008
)

scanner = PhotogrammetryScanner(config)

def progress_callback(value, message):
    print(f"[{value}%] {message}")

success = scanner.run_full_pipeline(progress_callback)

if not success:
    print("❌ Tarama başarısız!")
    exit(1)

# Model kaydet
mesh_path = "drone.stl"
scanner.export_mesh(mesh_path)
print(f"✅ Model kaydedildi: {mesh_path}")

# 2. BLENDER DATASET OLUŞTURMA
print("\n" + "=" * 60)
print("ADIM 2: BLENDER SENTETIK DATASET")
print("=" * 60)

output_dir = "./dataset"
num_views = 8

# Blender script'i çalıştır
cmd = f"blender --background --python blender_synthetic_generator.py -- {mesh_path} {output_dir} {num_views}"
result = subprocess.run(cmd, shell=True)

if result.returncode == 0:
    print(f"✅ Dataset oluşturuldu: {output_dir}/")
    
    # Metadata oku
    import json
    with open(f"{output_dir}/metadata.json") as f:
        metadata = json.load(f)
    
    print(f"   • Toplam görüntü: {len(metadata['renders'])}")
    print(f"   • Çözünürlük: 1280x720")
    print(f"   • Format: PNG RGBA")
else:
    print("❌ Blender render başarısız!")
    exit(1)

# 3. ML TRAINING HAZIRLIĞI
print("\n" + "=" * 60)
print("ADIM 3: ML TRAINING DATASET HAZIRLIĞI")
print("=" * 60)

# YOLO annotation oluştur
print("📝 YOLO annotation oluşturuluyor...")
# ... annotation code ...

# CFD training data oluştur
print("⚙️ CFD training data oluşturuluyor...")
# ... CFD training code ...

print("✅ Tüm workflow tamamlandı!")
print("📊 Dataset konumu:", Path(output_dir).absolute())
```

### Bash Komut Dosyası

```bash
#!/bin/bash
# scan_to_dataset.sh

MESH_FILE="drone.stl"
DATASET_DIR="./dataset"
NUM_VIEWS=8

echo "🚀 SCAN TO DATASET WORKFLOW"
echo "============================"

# 1. Tarama
echo "📸 Adım 1: Tarama başlıyor..."
python3 -c "
from photogrammetry_scanner import PhotogrammetryScanner, ScanConfig, MeshQuality
config = ScanConfig(num_images=20, quality=MeshQuality.PRODUCTION)
scanner = PhotogrammetryScanner(config)
success = scanner.run_full_pipeline()
if success:
    scanner.export_mesh('$MESH_FILE')
    print('✅ Model oluşturuldu')
"

if [ ! -f "$MESH_FILE" ]; then
    echo "❌ Model oluşturulamadı"
    exit 1
fi

# 2. Blender
echo "🎬 Adım 2: Blender render başlıyor..."
blender --background --python blender_synthetic_generator.py -- \
    "$MESH_FILE" "$DATASET_DIR" "$NUM_VIEWS"

if [ $? -eq 0 ]; then
    echo "✅ Dataset oluşturuldu: $DATASET_DIR"
else
    echo "❌ Blender render başarısız"
    exit 1
fi

# 3. Özet
echo ""
echo "📊 ÖZET"
echo "======="
echo "• Mesh: $MESH_FILE"
echo "• Dataset: $DATASET_DIR"
echo "• Toplam görüntü: $(ls $DATASET_DIR/*.png | wc -l)"
echo ""
echo "✅ Hazır! Training başlayabilirsiniz."
```

---

## 🎥 SENTETIK VERİ TÜRLERİ

### A. Kamera Açıları (8)

```
Dairesel hareket, sabit yükseklik
└─ 360° / 8 = 45° aralıklar

    ↑ (View 0)
    
View7 ←   → View1

View6 ←   → View2
    
    ↓ (View 4)
```

### B. Aydınlatma Varyantları (4)

```
1. Studio (1 Sun)      → Profesyonel
2. 3-Light Setup       → Atölye
3. Low Light           → Dış ortam
4. Backlit             → Kontrast
```

### C. Doku/Renk Varyantları (5)

```
1. Gray Matte          → Basit
2. Carbon Fiber        → Teknik
3. Metallic Blue       → Parlak
4. White Plastic       → Varsayılan
5. Red Glossy          → Renkli
```

### D. Toplam Kombinasyonlar

```
8 (kamera) × 4 (ışık) × 5 (doku) = 160 görüntü
≈ 5 dakika render
≈ 200 MB depolama
```

---

## 🧠 ML TRAINING İÇİN HAZIRLIK

### Örnek: YOLO Annotation

```python
import json
from pathlib import Path

# Metadata yükle
with open("dataset/metadata.json") as f:
    metadata = json.load(f)

# YOLO format (xmin, ymin, xmax, ymax, class)
for render in metadata["renders"]:
    filename = render["filename"]
    
    # Bounding box otomatik oluştur
    # (Blender'da render sırasında depth map da oluşturabiliriz)
    bbox = {
        "xmin": 100,  # örnek
        "ymin": 100,
        "xmax": 900,
        "ymax": 600,
        "class": "drone"  # veya aircraft type
    }
    
    # YOLO .txt dosyası
    txt_path = f"dataset/{Path(filename).stem}.txt"
    with open(txt_path, "w") as f:
        f.write(f"0 {bbox['xmin']} {bbox['ymin']} {bbox['xmax']} {bbox['ymax']}\n")

print("✅ YOLO annotations oluşturuldu")
```

### CFD Training Data

```python
# Her görüntü için simülasyon parametreleri
cfm_training_data = {
    "Studio_1Light_Gray_Matte_View_00.png": {
        "wind_speed": 15.0,      # m/s
        "angle_of_attack": 5.0,  # derece
        "reynolds": 285000,
        "expected_lift": 68.5,   # N
        "expected_drag": 3.4     # N
    },
    ...
}

# JSON kaydı
import json
with open("dataset/cfd_training.json", "w") as f:
    json.dump(cfm_training_data, f, indent=2)
```

---

## 📈 VARYASYON ÖRNEKLERİ

### Temel Varsayılan

```
• 8 kamera açısı
• 4 aydınlatma
• 5 doku
= 160 görüntü (5 dakika)
```

### Detaylı

```
• 16 kamera açısı (22.5° aralıklar)
• 8 aydınlatma varyantı
• 10 doku
= 1,280 görüntü (45 dakika)
```

### Minimal (Hızlı Test)

```
• 4 kamera
• 2 aydınlatma
• 3 doku
= 24 görüntü (1 dakika)
```

---

## 🔧 İLERİ SEÇENEKLER

### Termal Görüntüler

```python
# Blender'da gradient material
generator.generate_thermal_dataset(num_views=8)
# → Blue (soğuk) → Red (sıcak) görüntüler
```

### Hasar Varyantları

```python
# Modifiers: noise, deformation
generator.generate_damage_variants()
# → Hasarlı versiyonlar
# (Roket çökmesi vs. test etmek için)
```

### Wind Tunnel Benzetimi

```python
# Particle system (hava/duman)
# Geometrik distortion
generator.generate_wind_effects()
```

---

## 🚀 GERÇEK HAYAT SENARYOSU

### "Drone Aerodinamik Optimization"

```
1. DRONE TARAMA (5 dakika)
   📸 Kamera ile 20 görüntü yakla
   ✅ drone.stl oluştur

2. BLENDER DATASET (10 dakika)
   🎬 160 render oluştur
   📊 metadata.json oluştur

3. CFD SIMÜLASYON (2 saat)
   ⚙️ Her açı için CFD çalıştır
   📈 Drag/Lift verileri topla

4. ML MODEL (1-2 saat)
   🧠 YOLO model eğit
   📊 Accuracy: 85%+

5. SONUÇ
   ✅ Tarama → Dataset → ML Model
   🚀 Otomatik aerodinamik tahmin
```

---

## 📋 KONTROL LİSTESİ

- [ ] Scanner GUI yüklü ve çalışıyor
- [ ] Blender yüklü (Python API aktif)
- [ ] STL export dosyası hazır
- [ ] Output klasörü oluşturuldu
- [ ] Metadata JSON oluşturuldu
- [ ] Render görüntüleri (160) hazır
- [ ] YOLO annotation oluşturuldu
- [ ] CFD training data hazır
- [ ] ML model eğitime başladı

---

## 💡 İPUÇLARı

✅ **Hızlandırmak için:**
- Render resolution'ı azalt (1280 → 640)
- Sample sayısını azalt (256 → 64)
- Kamera açılarını azalt (8 → 4)

✅ **Kalite artırmak için:**
- Blender CUDA/OptiX GPU kullan
- Noise reduction aktif et
- Doku detaylarını artır

✅ **İçe Aktarma (Blender):**
- STL → OBJ → Blender (daha iyi)
- Skala kontrol et (mm vs. m)
- Normal vektörler düzelt

---

## 📚 REFERANSLAR

- Blender Python API: https://docs.blender.org/api/
- Blender Rendering: https://docs.blender.org/manual/en/latest/render/
- YOLO Format: https://github.com/ultralytics/yolov5
- Synthetic Data: https://research.nvidia.com/publication/2018-06_Playing

---

**Sonuç:** Tamamen otomatik veri oluşturma pipeline'ı ✅

**Zaman:** Tarama (5m) + Render (10m) + CFD (2h) + ML (1h) = **3-4 saat**

**Çıktı:** 160+ görüntü + Dataset + ML Ready ✅
