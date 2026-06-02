# 3D Photogrammetry Scanner — Rehberi

**Versiyon:** 1.0  
**Tarih:** 2026-04-07  
**Teknoloji:** Structure from Motion (SfM), Point Cloud Processing, Mesh Generation

---

## 🎥 Nedir?

**3D Photogrammetry Scanner**, kameradan çekilen görüntülerden otomatik olarak 3D katı model oluşturur:

```
📸 Kamera Görüntüleri
    ↓
🔍 Feature Detection (SIFT/SURF)
    ↓
🔗 Feature Matching (eşleştirme)
    ↓
📐 Structure from Motion (SfM)
    ↓
☁️ Point Cloud (3D noktalar)
    ↓
🧊 Mesh Generation (Poisson/Ball Pivoting)
    ↓
✨ Optimization (Smoothing, Simplification)
    ↓
💾 STL/OBJ/STEP Dosyası
    ↓
🚀 CFD/FEA Simülasyonu
```

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıkları Yükle

```bash
cd cfd_fea_tools
pip install -r scanner_requirements.txt
```

### 2. GUI'den Kullan

**CFD Arayüzünü aç:**
```bash
python app_parametric.py
```

**Scanner Tab → BAŞLAT** (Geri sayımlı tarama)

### 3. Python'da Kullan

```python
from photogrammetry_scanner import PhotogrammetryScanner, ScanConfig, MeshQuality

# Konfigürasyon
config = ScanConfig(
    num_images=15,
    quality=MeshQuality.NORMAL,
    voxel_size=0.01
)

# Scanner
scanner = PhotogrammetryScanner(config)
success = scanner.run_full_pipeline()

# Kaydet
if success:
    scanner.export_mesh("object.stl")
```

---

## 📋 Tarama Adımları

### Adım 1: Nesneyi Hazırla

1. **Aydınlatma:** Yeterli ve eşit ışık (gölge yok)
2. **Arka plan:** Düz, nötr renk (beyaz veya gri)
3. **Nesne:** Sabit, hareket etmiyor
4. **Kamera:** Tripod kullan (stabilite)

### Adım 2: Ayarlar

| Ayar | Değer | Açıklama |
|------|-------|----------|
| **Görüntü Sayısı** | 10-30 | Daha çok = daha iyi (zaman ↑) |
| **Kalite** | Normal | Draft=hızlı, High=detaylı |
| **Voxel Boyutu** | 0.01 m | Küçük = detaylı (zaman ↑) |
| **Gürültü Eşiği** | 2.0 σ | Yüksek = çıkarmak daha çok nokta |

### Adım 3: Tarama Seçeneği

#### A. Webcam (Geri Sayımlı)
```
1. Scanner Tab → BAŞLAT
2. 3 saniyelik geri sayım
3. Her görüntü otomatik yakalanır
4. Nesneyi yavaşça döndür / hareket ettir
```

**Örnek:** 15 görüntü = 45 saniye

#### B. Video Dosyasından
```python
scanner = PhotogrammetryScanner(config, mode=ScannerMode.VIDEO_SEQUENCE)
scanner.extract_frames_from_video("video.mp4", interval=200)  # 200ms ara
```

#### C. Resim Klasöründen
```python
scanner = PhotogrammetryScanner(config, mode=ScannerMode.IMAGE_FOLDER)
scanner.load_images_from_folder("images/")
```

### Adım 4: İşleme

**Otomatik:**
1. **Feature Detection** — Kanat profili, kenarlar tespit
2. **Feature Matching** — Görüntüler arası eşleştirme
3. **SfM** — 3D noktaları hesapla
4. **Point Cloud** — Gürültü kaldır, voxel down-sample
5. **Mesh Oluşturma** — Poisson surface reconstruction
6. **Optimize** — Smooth + Simplify

### Adım 5: Dışa Aktarma

```
Dosya Format:
  • STL (ASCII/Binary) — 3D yazıcı, CFD (yaygın)
  • OBJ — 3D modelleme
  • PLY — Point cloud
  • STEP — CAD (yüksek hassasiyet)
```

**CFD için önerilen:** STL Binary

---

## 🎯 Uygulamalar

### 1. Drone Tasarımı

**Senaryo:** El yapımı drone'un aerodinamik analizi

```
1. Drone prototipini kameraya tut
2. 20 görüntü yakala (30 saniye)
3. Mesh oluştur (2 dakika)
4. CFD simülasyonu başlat
5. Tasarımı optimize et
```

### 2. Roket Ateş Sonrası Analiz

**Senaryo:** Başarısız roketin hasarı incelemek

```
1. Roket enkazını tarayıp 3D model oluştur
2. Başarısız kısımları analiz et
3. Yeni tasarımda iyileştir
```

### 3. Uçak Model Tasarımı

**Senaryo:** Balsa uçağın gerçek ölçümü

```
1. Tasarımlanmış uçağı tarayıp doğruluğu kontrol et
2. CAD vs. gerçeklik karşılaştırması
3. CFD ile aerodinamik test
```

### 4. Artefakt Belgeleme

**Senaryo:** Tarihsel İHA benzeri modeli belgelemek

```
1. Tarama ve 3D modeli oluştur
2. Virtual müze için paylaş
3. Eğitim materyali olarak kullan
```

---

## 📊 Kalite Kıyaslaması

| Seviye | Element | Zaman | Kullanım | Seçenek |
|--------|---------|-------|----------|---------|
| **Draft** | 5-20K | 30s | Hızlı test | Prototip |
| **Normal** | 50-100K | 2-3m | Dengeli | **Önerilen** |
| **High** | 100-500K | 5-10m | Detaylı | Yayın |
| **Production** | 500K+ | 15-30m | CFD hazır | En iyi |

**Öneriler:**
- Tarama başlangıcı: **Draft** (hızlı geri bildirim)
- Tasarım: **Normal** (dengeli)
- Son CFD: **Production** (yüksek doğruluk)

---

## 🔧 İleri Ayarlar

### Point Cloud Ön İşleme

```python
from photogrammetry_scanner import PointCloudProcessor
import open3d as o3d

processor = PointCloudProcessor()

# PCD yükle
pcd = o3d.io.read_point_cloud("cloud.ply")

# Outlier kaldır
pcd_clean = processor.remove_outliers(pcd, nb_neighbors=30, std_ratio=3.0)

# Downsample
pcd_small = processor.downsample(pcd_clean, voxel_size=0.02)

# Normal hesapla
pcd_normal = processor.estimate_normals(pcd_small)

# Kaydet
o3d.io.write_point_cloud("cloud_processed.ply", pcd_normal)
```

### Mesh Oluşturma Seçenekleri

```python
# Poisson Surface Reconstruction
mesh = processor.poisson_mesh(pcd, depth=9)  # depth: 7-11

# Ball Pivoting Algorithm (alternatif)
mesh = processor.ball_pivoting_mesh(pcd, radii=[0.005, 0.01, 0.02])
```

### Mesh Optimizasyonu

```python
from photogrammetry_scanner import MeshOptimizer

optimizer = MeshOptimizer()

# Sadeleştir
mesh_simple = optimizer.simplify_mesh(mesh, target_count=50000)

# Düzleştir
mesh_smooth = optimizer.smooth_mesh(mesh_simple, iterations=3)

# Kalite kontrol
metrics = optimizer.check_mesh_quality(mesh_smooth)
print(f"Watertight: {metrics['is_watertight']}")
```

---

## 🐛 Sorun Giderme

### Problem 1: Kamera çalışmıyor

```python
import cv2

# Kamera listesi
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Kamera {i} bulundu ✓")
        cap.release()
```

**Çözüm:** Doğru kamera numarasını seç (genelde 0 veya 1)

### Problem 2: Çok az feature eşleştirmesi

**Neden:** Zayıf aydınlatma, düz yüzeyler, hızlı hareket

**Çözüm:**
- Işığı artır (güneş, lamba)
- Nesneyi yavaşça dönüştür
- Ek tekstür ekle (sticker, işaretleme)

### Problem 3: Mesh bozuk (delik, boşluk)

**Neden:** Yeterli görüntü yok, kötü feature matching

**Çözüm:**
- Görüntü sayısını artır (20 → 30)
- Açıdan fotoğraf çek (üst, alt, yan)
- Voxel boyutunu küçült

### Problem 4: Mesh watertight değil

```python
# Düzelt
mesh_fixed = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
    pcd, depth=10)[0]

# Kontrol
print(mesh_fixed.is_watertight())
```

---

## 🔗 CFD İntegrasyonu

### Mesh'i CFD'ye Hazırla

```python
# 1. Scan
scanner = PhotogrammetryScanner(config)
success = scanner.run_full_pipeline()

# 2. Mesh'i al
mesh = scanner.mesh

# 3. STL olarak kaydet
scanner.export_mesh("drone.stl")

# 4. CFD arayüzünde:
#    - "Load Mesh" butonuna tıkla
#    - drone.stl seç
#    - Mesh otomatik domain'e yerleştir
#    - Simülasyonu başlat
```

### Mesh Ölçekleme (gerekirse)

```python
# Çok küçük model (mm cinsinden)?
mesh.scale(0.001)  # mm → m'ye dönüştür
mesh.translate([0, 0, 0])  # Merkezle

scanner.mesh = mesh
scanner.export_mesh("drone_scaled.stl")
```

---

## 📷 Tarama İpuçları

### İyi Tarama İçin

✅ **Aydınlatma**
- Doğal ışık (dış) VEYA
- 2+ Lambası (gölge azaltsın)
- Diffuser kullan (sert gölgeleri yumuşat)

✅ **Kamera Hareketi**
- Dairesel: Nesne sabit, kamera döner (ideal)
- Lineer: Nesneyi kamera etrafında kaydır
- Yavaş: 1-2 saniye/görüntü

✅ **Açı Çeşitliliği**
- Üstten 45°
- Yanlardan (2-4 açı)
- Alttan 45° (gerekirse)

❌ **Kaçınılması Gerekenler**
- Hızlı hareket
- Zayıf aydınlatma
- Düz, tek renk yüzey
- Yansıtıcı/şeffaf malzeme
- Kamerayı çok hızlı döndürme

---

## 📚 Teknik Detaylar

### Structure from Motion (SfM)

```
Görüntü 1 ──┐
            ├─→ Feature Matching ──→ F-Matrix ──→ Pose (R, t) ──→ Triangulation ──→ 3D
Görüntü 2 ──┘
```

### Feature Detectors

| Yöntem | Hız | Doğruluk | Kullanım |
|--------|-----|----------|----------|
| **SIFT** | Yavaş | Yüksek | Önerilen |
| **SURF** | Hızlı | İyi | Hızlı |
| **ORB** | Çok hızlı | Orta | Gerçek-zaman |

### Mesh Yöntemleri

| Yöntem | Kalite | Hız | Özellikleri |
|--------|--------|-----|-----------|
| **Poisson** | Yüksek | Orta | Smooth, watertight |
| **Ball Pivoting** | Çok Yüksek | Yavaş | Detaylı, kenarları iyi |

---

## 🎓 Eğitim Senaryosu

### "Drone Aerodinamik Optimizasyonu"

1. **Senaryo:** Balsa drone prototipini optimize etmek

2. **Adımlar:**
   ```
   Adım 1: Drone'u tara (15 görüntü)
   Adım 2: 3D model oluştur (Normal kalite)
   Adım 3: CFD arayüzüne yükle
   Adım 4: Referans simülasyon çalıştır
   Adım 5: Kanat açıklığını artır (CAD düzenle)
   Adım 6: Tekrar tara
   Adım 7: CFD ile karşılaştır
   Adım 8: Optimal tasarımı seç
   ```

3. **Öğrenme Çıktıları:**
   - 3D tarama nasıl çalışır?
   - CFD neden gerekli?
   - Parametrik optimizasyon yöntemi

---

## 📝 Başvuru

- OpenCV (Feature Detection): https://docs.opencv.org/
- Open3D (Point Cloud): http://www.open3d.org/
- Structure from Motion: https://en.wikipedia.org/wiki/Structure_from_motion
- Photogrammetry: https://www.agisoft.com/

---

**Son Güncelleme:** 2026-04-07  
**Sürüm:** 1.0 (Stabil)
