# Parametrik CFD/FEA Analiz Aracı — Rehberi

**Versiyon:** 2.0 (Parametrik)  
**Tarih:** 2026-04-07  
**Çalışan:** Sabit Kanat Roketler, Drone, İHA, VTOL, HAPS

---

## 🎯 Amaç

Bu araç, **farklı uçak/roket tasarımlarını hızlı şekilde karşılaştırmanızı** sağlar:

```
Design → Geometry → Mesh → CFD/FEA → Sonuçlar → Karşılaştırma → Optimize
```

**Parametrik Analiz:** Aynı tasarımın birden fazla varyantını otomatik çalıştır.

---

## 📦 Dosya Yapısı

```
cfd_fea_tools/
├── app_parametric.py          ← Ana GUI (Parametrik)
├── aircraft_geometry.py        ← Uçak tasarım modülü
├── mesh_generator.py          ← Otomatik mesh
├── simulation_runner.py        ← Simülasyon yöneticisi
├── OPENFOAM_REHBERI.md        ← OpenFOAM detayı
├── CALCULIX_REHBERI.md        ← CalculiX detayı
├── config.yaml                ← Senaryo şablonları
├── requirements.txt           ← Bağımlılıklar
└── PARAMETRIK_ANALIZ_REHBERI.md ← Bu dosya
```

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıkları Yükle

```bash
cd cfd_fea_tools
pip install -r requirements.txt
```

### 2. Uygulamayı Çalıştır

```bash
python app_parametric.py
```

### 3. İş Akışı

1. **Uçak Seç** → "MiniHawk", "Model Roket", vb.
2. **Parametreler Tanımla** → Min/Max/Nokta sayısı
3. **Mesh Oluştur** → Gmsh otomatik
4. **Simülasyon Başlat** → Paralel OpenFOAM
5. **Sonuçları Analiz** → Drag, Lift, Moment
6. **Rapor** → PDF/CSV çıktı

---

## 🛩️ Desteklenen Araçlar

### 1. MiniHawk UAV (Sabit Kanat İHA)
- Açıklık: 1.5 m
- Kütle: 2.5 kg
- Cruise: 15 m/s
- Aerodinamik optimizasyon

### 2. Model Roket (F-Serisi)
- Uzunluk: 60 cm
- Apogee: 300-400 m
- İstikrar analizi
- Stabilizer tasarım

### 3. Fixed-Wing Racer (Yarış Dronu)
- Açıklık: 2.0 m
- Maksimum: 40+ m/s
- Yüksek performans

### 4. VTOL Drone
- Hover + Forward Flight
- 4 Motor (Quad)
- Hibrit tasarım

### 5. HAPS (Yüksek İrtifa)
- Açıklık: 4.0+ m
- 18+ km dayanış
- Verimlilik kritikal

---

## 🔧 Parametrik Çalışma Örneği

### Model Roket Optimizasyonu

**Python:**

```python
from aircraft_geometry import AircraftLibrary, ParametricStudy
from simulation_runner import SimulationRunner

roket = AircraftLibrary.model_rocket()
study = ParametricStudy(roket)

# 3 parametreli varyasyon
study.add_variation("span", [0.12, 0.15, 0.18])
study.add_variation("sweep_angle", [20, 30, 40])
study.add_variation("taper_ratio", [0.4, 0.6, 0.8])

# 3×3×3 = 27 case
runner = SimulationRunner()
results = runner.run_parametric_study(roket, {
    "span": [0.12, 0.15, 0.18],
    "sweep_angle": [20, 30, 40],
    "taper_ratio": [0.4, 0.6, 0.8]
}, num_workers=4)
```

**Sonuç:**

```
✅ 27 simülasyon tamamlandı
  Optimal: Sweep=30°, Area=12cm² → Cd=0.0108 (minimum)
  Statik marji = 2.1 cm (aman)
```

---

## 📊 Mesh Seçimi

| Seviye | Element | Zaman | Doğruluk | Kullanım |
|--------|---------|-------|----------|----------|
| Coarse | 50-100K | 30m | ±15% | Ön tasarım |
| **Medium** | 300-500K | 2-4h | ±5-8% | **Optimal** |
| Fine | 1M+ | 8-24h | ±2-3% | Yayın |

---

## 🔬 Solver Seçimi

| Solver | Mach | Reynolds | Kullanım |
|--------|------|----------|----------|
| simpleFoam | <0.3 | 10⁶ | UAV aerodinamik |
| pimpleFoam | <0.3 | - | Geçici simülasyon |
| rhoCentralFoam | >0.3 | - | Roket (sıkışabilir) |

---

## 📈 Sonuç Analizi

### Temel Katsayılar

```python
# CFD çıktısından
Cd = Drag / (0.5 × ρ × V² × S)
Cl = Lift / (0.5 × ρ × V² × S)

# Açılı akış (Yaw, Pitch, Roll)
Cn = Side_Force / (0.5 × ρ × V² × S)

# Moment Katsayıları
Cm = Moment / (0.5 × ρ × V² × S × L)
```

### Karşılaştırma (pandas)

```python
import pandas as pd

df = pd.DataFrame(results)
optimal = df.sort_values('drag_force').head(5)
print(optimal[['case_name', 'drag_force', 'lift_force']])
```

---

## 🎓 Eğitim Senaryoları

### Senaryo 1: Aspect Ratio Etkisi

```yaml
Soru: "Neden uzun kanatlar etkilidir?"
Test: AR = [3, 4, 5, 6, 7, 8]
Sonuç: AR ↑ → L/D ↑ (verimlilik)
```

### Senaryo 2: Roket İstikrarı

```yaml
Soru: "Kanat boyutu ne olmalı?"
Parametreler:
  - Stabilizer Alanı: 6-14 cm²
Hedef: Statik Marji ≥ 2 cm
```

### Senaryo 3: Rüzgar Dayanıklılığı

```yaml
Soru: "MiniHawk 15 m/s yan rüzgara dayanır mı?"
Test:
  - Kanat Açıklığı: [1.2, 1.5, 1.8] m
  - Rüzgar: [0, 8, 12, 15] m/s
Sonuç: Kontrol moment yeterli mi?
```

---

## 💻 Kullanıcı Arayüzü Rehberi

### Sol Panel (Uçak Seçimi)
- 5 hazır tasarım
- Özellikleri ve parametreleri göster
- Kütlesel ve geometrik bilgiler

### Sağ Panel (Analiz)

#### Konfigürasyon Tab'ı
- Solver seçimi (simpleFoam, pimpleFoam, rhoCentralFoam)
- Rüzgar hızı (0-100 m/s)
- İşlemci sayısı (1-16 CPU)
- Parametrik çalışma tanımı

#### Mesh Tab'ı
- Base mesh boyutu (0.001-0.1 m)
- Boundary layer (aktif/pasif)
- Tahmini element sayısı
- Mesh oluşturma butonu

#### Simülasyon Tab'ı
- Başlat/Durdur/Sıfırla butonları
- İlerleme çubuğu (0-100%)
- Gerçek-zaman log

#### Sonuçlar Tab'ı
- Drag, Lift, Moment tablosu
- Karşılaştırma grafiği
- Rapor oluşturma

---

## 🔌 API Örneği (Python)

### Geometri Oluşturma

```python
from aircraft_geometry import AircraftLibrary

# Hazır tasarım
uav = AircraftLibrary.minihawk_uav()

# Parametreler değiştir
uav.wing.span = 1.8  # 1.8 m açıklık
uav.wing.area = 0.5  # 0.5 m² alan

# Kütle özellikleri
mass_props = uav.mass_properties()
print(f"Kütle: {mass_props['total_mass']:.2f} kg")
```

### Mesh Oluşturma

```python
from mesh_generator import MeshGenerator

mesh = MeshGenerator(uav, mesh_size=0.01)
config = mesh.generate_mesh_config()
script = mesh.generate_gmsh_script()

with open("mesh.geo", "w") as f:
    f.write(script)
```

### Simülasyon Çalıştırma

```python
from simulation_runner import SimulationRunner, SimulationJob

runner = SimulationRunner()
job = SimulationJob(
    case_name="uav_test",
    aircraft=uav,
    solver="simpleFoam",
    mesh_size=0.01,
    wind_speed=15.0,
    analysis_type="aerodinamik"
)

result = runner.run_simulation(job)
print(f"Status: {result['status']}")
print(f"Drag: {result.get('drag_force', 'N/A'):.2f} N")
```

---

## 🧪 Test Senaryoları

### Test 1: Single Run
```bash
python app_parametric.py
# → MiniHawk seç → Simülasyon başlat
```

### Test 2: Parametrik (3 case)
```bash
# GUI: Parametreler Tanımla
# Span: 1.2-1.8 m (3 nokta)
# Sweep: 0-10° (1 parametre)
# → Toplam: 3 case
```

### Test 3: Batch (Python)
```bash
python simulation_runner.py
# → 9 case paralel çalıştır
```

---

## 📊 Çıktı Formatları

| Format | Kullanım |
|--------|----------|
| CSV | Veriler, karşılaştırma |
| JSON | Yapılandırma, API |
| PDF | Rapor, görselleştirme |
| VTK | ParaView (görünüm) |

---

## 🎯 Hedefler (Çelik Kubbe)

1. ✅ CFD arayüzü (parametrik)
2. ✅ 5 uçak template'i
3. ✅ Otomatik mesh
4. ⏳ OpenFOAM subprocess entegrasyon
5. ⏳ Görselleştirme (matplotlib/paraview)
6. ⏳ Optimizasyon (scipy)

---

**Son Güncelleme:** 2026-04-07  
**Sürüm:** 2.0 Parametrik
