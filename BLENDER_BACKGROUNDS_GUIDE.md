# Blender Sentetik Dataset — Arka Plan Resimleri Rehberi

## 🎬 Arka Plan Resimleri Kullanımı

Blender synthetic dataset oluştururken, `D:\synthetic_dataset\backgrounds` klasöründe bulunan arka plan resimlerini otomatik olarak kullanabilirsiniz.

---

## 📁 Arka Plan Klasör Yapısı

```
D:\synthetic_dataset\backgrounds\
├── background_01.jpg
├── background_02.jpg
├── background_03.png
├── environment_01.exr
└── ...
```

**Desteklenen formatlar:**
- `.jpg`, `.jpeg`
- `.png`
- `.exr` (Blender EXR format, HDR desteği)

---

## 🚀 Kullanım

### Yöntem 1: Blender GUI'den

1. **Parametrik Analysis Tool'u aç**
   ```bash
   python app_parametric.py
   ```

2. **Blender sekmesini bekleyin** (gelecek versiyon)
   - Arka plan klasörünü seçin: `D:\synthetic_dataset\backgrounds`

### Yöntem 2: Command Line

```bash
# Temel kullanım
blender --background --python blender_synthetic_generator.py -- \
    drone.stl ./dataset 8

# Arka plan resimleri ile
blender --background --python blender_synthetic_generator.py -- \
    drone.stl ./dataset 8 D:\synthetic_dataset\backgrounds
```

### Yöntem 3: Python Script

```python
from blender_synthetic_generator import SyntheticDatasetGenerator, RenderConfig

# Generator oluştur (arka plan klasörü belirt)
generator = SyntheticDatasetGenerator(
    mesh_path="drone.stl",
    output_dir="./dataset",
    background_dir="D:/synthetic_dataset/backgrounds"  # Forward slash kullan
)

# Render config
config = RenderConfig(
    resolution_x=1280,
    resolution_y=720,
    samples=256,
    engine="CYCLES"
)

# Dataset oluştur
metadata = generator.generate_dataset(
    num_views=8,
    render_config=config
)

print(f"✅ {len(metadata['renders'])} render oluşturuldu")
```

---

## 📊 Render Kombinasyonları

Arka plan resimleri ile:

```
8 kamera açısı × 4 aydınlatma × 5 doku × N arka plan = Toplam render

Örnek (5 arka plan):
8 × 4 × 5 × 5 = 800 görüntü (25 dakika render)
```

### Metadata Çıktısı

Her render için metadata'ya arka plan bilgisi eklenir:

```json
{
  "renders": [
    {
      "filename": "Studio_1Light_Gray_Matte_View_00_background_01.png",
      "camera_view": "View_00",
      "lighting": "Studio_1Light",
      "texture": "Gray_Matte",
      "background": "background_01",
      "camera_location": [3.0, 0.0, 2.0],
      "resolution": "1280x720"
    },
    ...
  ]
}
```

---

## 🎨 Arka Plan Seçimi İpuçları

### İyi Arka Planlar
✅ **Çeşitli doku:** Beton, ahşap, metal, kumaş  
✅ **Farklı renkler:** Açık, koyu, renkli  
✅ **Değişen ışık:** Güneş, gölge, iç ortam  
✅ **Farklı ölçekler:** Yakın, uzak, orta mesafe  

### Kötü Arka Planlar
❌ **Tekdüze:** Düz gri, beyaz  
❌ **Fazla parlak:** Gözleri yakıp, objek gözükmez  
❌ **Çok ayrıntılı:** İlgiye başlayan, objeyi gizler  
❌ **Düşük çözünürlük:** Blok ve pixelated  

### İdeal Kurulum
```
Arka plan seçimi:
1. Objenin türüne uygun (drone → dış ortam)
2. Kontrastlı (koyu obje → açık arka plan)
3. Doğal görünüş (yapay değil)
4. 1920×1080 veya daha yüksek çözünürlük
```

---

## 🔧 Gelişmiş Ayarlar

### Arka Plan Döngüsü Denetimi

`blender_synthetic_generator.py` içinde:

```python
# Her render için farklı arka plan kullan
background_idx = len(self.metadata["renders"]) % len(self.backgrounds)

# Veya sabit arka plan kullan
background_idx = 0  # Her zaman ilk arka planı kullan
```

### Arka Plan Yoğunluğu

```python
# Blender arka plan kurulumunda intensity ayarı
# (generate_dataset metodu içinde)

# Proses render'dan hemen önce
self.setup_default_scene(render_config, current_background)

# Burada intensity değişebilir:
# bg.inputs[1].default_value = 1.0  # 0.0 - 2.0 arasında
```

### HDR Arka Planları

`.exr` formatı kullanırken:

```python
# 32-bit float colors
# Otomatik tone mapping
# Gerçekçi aydınlatma
```

---

## 📈 Performans

### Disk Kullanımı

```
Per render: ~1-3 MB (PNG)
160 render: ~160-480 MB
800 render (5 BG): ~800-2400 MB
```

### Render Zamanı

```
Per render: 30-90 saniye (CYCLES, 256 sample)
8 views × 4 lighting × 5 texture = 160 render
Toplam: ~80-240 dakika (1.5-4 saat)

GPU ile (NVIDIA): 10x daha hızlı
```

### Arka Plan Yükleme

```
Background loading: ~100ms per image
Minimum gecikme: yok (pre-loaded)
```

---

## 🐛 Sorun Giderme

### Problem: Arka planlar görünmüyor

```python
# Kontrol et:
1. Klasör yolu doğru mu?
   - Windows: D:\synthetic_dataset\backgrounds
   - Linux: /home/user/synthetic_dataset/backgrounds
   
2. Dosya uzantıları destekleniyor mu?
   - jpg, jpeg, png, exr
   
3. Dosyalara erişim izni var mı?
   - Linux/Mac: chmod 644 *.jpg
```

### Problem: Render çok yavaş

```bash
# GPU acceleration etkinleştir
export BLENDER_CUDA=1
blender --python blender_synthetic_generator.py -- ...

# Veya sample sayısını azalt
RenderConfig(samples=64)  # 256 yerine

# Çözünürlüğü azalt
RenderConfig(resolution_x=640, resolution_y=480)
```

### Problem: Bellek yetmiyor

```python
# Arka planları streaming mode'de yükle
# (Large dataset için)

# Batch processing kullan
num_views = 2  # Adım adım render et
```

---

## 📚 Örnek İş Akışı

### Tam Senaryö: Drone Dataset

```bash
# 1. Drone STL modelini tara (Scanner Tab)
# → drone.stl oluşturulur

# 2. Sentetik veri setini oluştur
blender --background --python blender_synthetic_generator.py -- \
    drone.stl ./drone_dataset 8 D:\synthetic_dataset\backgrounds

# 3. Çıktı kontrol et
ls -lh drone_dataset/
# → 160+ .png dosya
# → metadata.json

# 4. YOLO eğitimine hazırla
python ml_training_integration.py drone_dataset/metadata.json

# 5. Model eğit
# → YOLOv8 otomatik eğitilir
```

---

## 🎓 Öğrenme Noktaları

Bu özellik öğretir:
- ✅ Sentetik veri neden önemli?
- ✅ Çevre haritası (environment mapping) nedir?
- ✅ Background resimleri ışığı nasıl etkiler?
- ✅ Augmentation veri çeşitliliğini artırır
- ✅ ML modeli gerçek koşullardan eğitilir

---

## 📖 Komut Referansı

```bash
# Temel render (arka plan yok)
blender --python blender_synthetic_generator.py -- \
    model.stl output_dir 8

# Arka planlar ile
blender --python blender_synthetic_generator.py -- \
    model.stl output_dir 8 /path/to/backgrounds

# Python ile (Blender context'te)
blender --python -c "
from blender_synthetic_generator import SyntheticDatasetGenerator
gen = SyntheticDatasetGenerator('model.stl', './out', 'D:/bg')
gen.generate_dataset(num_views=8)
"

# Windows batch
set BACKGROUNDS=D:\synthetic_dataset\backgrounds
blender --python script.py -- model.stl output 8 %BACKGROUNDS%
```

---

## 💡 İleri Teknikler

### Custom Arka Plan Haritası

Blender viewport shading'de:
1. Yapın → Shading workspace
2. "World" sekmesini seç
3. Texture node'a arka plan resmi ekle
4. Rotation ve intensity ayarla

### Arka Plan Animasyonu

```python
# Video frame'lerinden arka plan oluştur
# (Gelecek versiyon)
```

### Procedural Arka Planlar

```python
# Blender noise texture (Cycles)
# (Codes bağımlılık olmadan)
```

---

## 📞 Destek

- **Soru:** Belge sayfasında ara
- **Bug:** GitHub Issues'a bildir
- **Örnek:** `examples/` klasöründe bak

---

**Son Güncelleme:** 2026-04-07  
**Versiyon:** 1.0 (Arka Plan Desteği)  
**Durum:** ✅ Hazır

Blender sentetik veri setiniz arka plan resimleri ile başlamaya hazır! 🎬
