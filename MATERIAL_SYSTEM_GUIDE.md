# Gelişmiş Malzeme Sistemi Rehberi

**Sistem:** bilsem_beyin Material Database v2.0  
**Tarih:** 2026-04-07  
**Özellikler:** Otomatik mühendislik hesaplamaları, kullanıcı-tanımlı malzemeler, GUI editörü

---

## 📋 Sistemin Özellikleri

### ✅ Neler Otomatik Hesaplanır?

Malzeme eklenirken Young modülü (E) ve Poisson oranı (ν) girildiğinde, sistem otomatik olarak hesaplar:

| Özellik | Formül | Açıklama |
|---------|--------|----------|
| **G (Shear Modulus)** | G = E / (2(1+ν)) | Kayma modülü |
| **K (Bulk Modulus)** | K = E / (3(1-2ν)) | Hacim modülü |
| **λ (Lamé Constant)** | λ = E·ν / ((1+ν)(1-2ν)) | Lamé sabiti |
| **σ_y/σ_max** | Akma / Çekme | Güvenlik faktörü |
| **Strength-to-Weight** | σ_y / ρ | Kuvvet/ağırlık oranı |
| **Stiffness-to-Weight** | E / ρ | Katılık/ağırlık oranı |

### 🎯 Veritabanında 10 Malzeme Önceden Yüklü

```
1. Aluminum 6061      (Standart uçak)
2. Aluminum 7075      (Yüksek mukavemetli)
3. Steel S355         (Yapısal çelik)
4. Steel Stainless 316 (Paslanmaz)
5. Carbon Fiber       (Komposit)
6. Titanium Grade 5   (Ti-6Al-4V)
7. Balsa Wood         (Hafif)
8. Glass Fiber        (GRP)
9. Magnesium AZ91D    (Çok hafif)
10. Kevlar            (Aramid)
```

---

## 🚀 BAŞLAMA

### 1. Malzeme Listesi (Python)

```python
from material_database import MATERIAL_LIBRARY

# Tüm malzemeleri listele
for name in MATERIAL_LIBRARY.list_materials():
    print(name)

# Malzeme getir
aluminum = MATERIAL_LIBRARY.get_material("Aluminum 6061")

# Özellikler
print(f"E: {aluminum.youngs_modulus} GPa")
print(f"σ_y: {aluminum.yield_strength} MPa")
print(f"Strength-to-Weight: {aluminum.strength_to_weight:.2e} m/s²")
```

### 2. Yeni Malzeme Ekle (Python)

```python
from material_database import MaterialLibrary, MaterialProperties, MaterialType

lib = MaterialLibrary()

# Oluştur (hesaplamalar otomatik!)
new_mat = MaterialProperties(
    name="Custom Aluminum",
    material_type=MaterialType.ALUMINUM,
    density=2800,
    youngs_modulus=72,
    poisson_ratio=0.33,
    yield_strength=450,
    tensile_strength=500,
    cost_per_kg=3.5
)

# Otomatik hesaplanan:
print(f"G (Shear): {new_mat.shear_modulus:.1f} GPa ✓")
print(f"K (Bulk): {new_mat.bulk_modulus:.1f} GPa ✓")
print(f"λ (Lamé): {new_mat.lame_constant:.1f} GPa ✓")

# Kaydet
lib.add_material(new_mat)
lib.save_to_file()
```

### 3. GUI ile Ekle (İnteraktif)

```python
from PySide6.QtWidgets import QApplication
from material_editor_gui import MaterialManagerTab
from material_database import MaterialLibrary

app = QApplication([])
lib = MaterialLibrary()
manager = MaterialManagerTab(lib)
manager.show()
app.exec()
```

---

## 🔍 ARAMA VE FİLTRELEME

### Türe Göre

```python
# Tüm alüminyumlar
aluminum = lib.search_by_type(MaterialType.ALUMINUM)
```

### Özelliğe Göre

```python
# Young: 100-200 GPa
materials = lib.search_by_property("youngs_modulus", 100, 200)

# Akma > 800 MPa
strong = lib.search_by_property("yield_strength", 800, 10000)
```

### Strength-to-Weight Sıralaması

```python
sorted_mats = sorted(
    lib.materials.items(),
    key=lambda x: x[1].strength_to_weight,
    reverse=True
)

for name, mat in sorted_mats[:5]:
    print(f"{name}: {mat.strength_to_weight:.2e}")
```

---

## 📊 DIŞA AKTARMA

```python
# CSV'ye aktar
lib.export_csv(Path("materials_report.csv"))

# Veya materials.json'i manuel paylaş
```

---

## 🧮 FORMÜLLER

### Girdiler: E (Young) + ν (Poisson)

**Örnek:** E = 69 GPa, ν = 0.33

```
Shear G = E / (2(1+ν)) = 69 / 2.66 = 25.9 GPa
Bulk K = E / (3(1-2ν)) = 69 / 1.02 = 67.6 GPa
Lamé λ = E·ν / ((1+ν)(1-2ν)) = 22.77 / 0.48 = 47.4 GPa
```

### Performans Metrikleri

```
Strength-to-Weight = σ_y / ρ
  Örn: 275 MPa / 2700 kg/m³ = 1.02×10^5 m/s²

Stiffness-to-Weight = E / ρ
  Örn: 69 GPa / 2700 kg/m³ = 2.55×10^7 m/s²
```

---

## ✅ DOĞRULAMA

Otomatik kontroller:

```
✓ Young modülü > 0
✓ Poisson oranı 0-0.5
✓ Mukavemetler > 0
✓ Yoğunluk > 0
```

Hatalı değer → ValueError

---

## 📁 DOSYALAR

```
material_database.py       ← Core (300+ satır)
material_editor_gui.py     ← GUI (400+ satır)
materials.json            ← Veritabanı (otomatik)
MATERIAL_SYSTEM_GUIDE.md  ← Bu rehber
```

---

## 🎓 KÖK KAYNAKLAR

- AISC Steel Manual
- Roark's Formulas
- MatWeb Material Database
- ASM International

---

**Status:** ✅ Tamamlandı  
**Versiyon:** 2.0  
**Tarih:** 2026-04-07
