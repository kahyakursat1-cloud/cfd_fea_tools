# 🚀 Malzeme Sistemi — Hızlı Başlangıç

**5 dakika cinsinden başla!**

---

## 1️⃣ GUI'yi Aç

```bash
cd D:\bilsem_beyin\cfd_fea_tools
python app_parametric.py
```

→ "🧪 Malzemeler" sekmesine tıkla

---

## 2️⃣ Mevcut Malzemeleri Gözat

Tablo 10 malzemeyi gösterir:
- Aluminum 6061, 7075
- Steel S355, Stainless 316
- Carbon Fiber, Titanium, Balsa, Glass Fiber, Magnesium, Kevlar

**Sütunlar:**
| Adı | Tür | Yoğunluk | E | σ_y | σ_max | S/W | Maliyet |

---

## 3️⃣ Yeni Malzeme Ekle

**Buton:** "+ Malzeme Ekle"

**Forma gir:**
```
Adı:                "Duraluminum"
Tür:                [aluminum]
Yoğunluk:           2780 kg/m³
Young Modülü (E):   72 GPa
Poisson Oranı (ν):  0.33
Akma (σ_y):         450 MPa
Çekme (σ_max):      505 MPa
(Diğer opsiyonel)
```

**Kaydet** → Otomatik:
- G = 27.1 GPa (hesaplanır)
- K = 70.6 GPa (hesaplanır)
- λ = 52.8 GPa (hesaplanır)

---

## 4️⃣ Malzeme Düzenle

1. Tablodan bir malzemeyi seç
2. "✎ Düzenle" butonu
3. Değerleri değiştir
4. "Kaydet"

---

## 5️⃣ Malzeme Sil

1. Seç
2. "✕ Sil"
3. Onayla

---

## 6️⃣ CSV'ye Dışa Aktar

Buton: "📊 CSV'ye Dışa Aktar"

→ `materials_export.csv` oluşturulur
→ Spreadsheet'te açılabilir

---

## 7️⃣ FEA'da Malzemeyi Kullan

Malzeme ekledikten sonra "⚙️ FEA" sekmesine git

Combo box otomatik güncellenir! Seç ve çalıştır.

---

## 💻 Python API

```python
from material_database import MATERIAL_LIBRARY, MaterialProperties, MaterialType

# Malzeme getir
titanium = MATERIAL_LIBRARY.get_material("Titanium Grade 5")
print(f"E = {titanium.youngs_modulus} GPa")
print(f"G = {titanium.shear_modulus:.1f} GPa")  # Otomatik!
print(f"S/W = {titanium.strength_to_weight/1e6:.2f}")

# Yeni ekle
my_mat = MaterialProperties(
    name="MyAlloy",
    material_type=MaterialType.ALUMINUM,
    density=2700,
    youngs_modulus=70,
    poisson_ratio=0.33,
    yield_strength=400,
    tensile_strength=450
)
MATERIAL_LIBRARY.add_material(my_mat)
MATERIAL_LIBRARY.save_to_file()

# Ara
strong = MATERIAL_LIBRARY.search_by_property("yield_strength", 400, 10000)
for name in strong:
    print(name)
```

---

## 🔧 Formüller

Girdiler: **E** (Young) + **ν** (Poisson)

```
G = E / (2(1+ν))      Kayma modülü
K = E / (3(1-2ν))     Hacim modülü
λ = E·ν / ((1+ν)(1-2ν))  Lamé
```

---

## ✅ Doğrulama

Sistem otomatik kontrol eder:
- E > 0 ✓
- 0 ≤ ν ≤ 0.5 ✓
- σ_y, σ_max > 0 ✓
- ρ > 0 ✓

Hata → Uyarı mesajı

---

## 📚 Daha Fazla Bilgi

- `MATERIAL_SYSTEM_GUIDE.md` — Detaylı rehber
- `MATERIAL_SYSTEM_STATUS.md` — Teknik durum raporu
- `MESH_THEORY_GUIDE.md` — Mesh teorisi

---

**Hazırsan başla!** 🎯
