# ✅ Malzeme Sistemi — Kurulum Tamamlandı

**Tarih:** 2026-04-07  
**Status:** 🟢 **PRODUCTION READY**  
**Version:** 2.0

---

## 📋 SISTEM ÖZET

Bilsem_beyin CFD/FEA/ML parametrik analiz aracına tam entegre bir malzeme kütüphanesi sistemi kuruldu.

| Bileşen | Durum | Detay |
|---------|-------|--------|
| **Material Database Core** | ✅ | 470+ satır, 10 pre-loaded malzeme |
| **Material GUI Editor** | ✅ | 400+ satır, interactive UI |
| **Automatic Calculations** | ✅ | 6 mühendislik parametresi otomatik |
| **User Material Addition** | ✅ | Manuel malzeme ekleme/düzenleme |
| **App Integration** | ✅ | MaterialManagerTab + FEA combo sync |
| **Testing** | ✅ | 7/7 test adımı başarılı |

---

## 🔬 KÖK TEKNOLOJI

### 1. Material Properties (material_database.py)

**Giriş Parametreleri (manuel):**
```
- name: str                          — Malzeme adı
- material_type: MaterialType        — Enum: METAL, ALUMINUM, COMPOSITE, vb.
- density: float                     — kg/m³
- youngs_modulus: float              — GPa
- poisson_ratio: float               — 0-0.5 arasında
- yield_strength: float              — MPa
- tensile_strength: float            — MPa
- (Optional) compressive_strength   — MPa
- (Optional) thermal_conductivity   — W/(m·K)
- (Optional) thermal_expansion      — 1/K (×10⁻⁶)
- (Optional) melting_point          — °C
- (Optional) cost_per_kg            — USD/kg
- (Optional) recyclable             — bool
```

**Hesaplanan Özellikler (otomatik):**
```
1. Shear Modulus (G):
   G = E / (2(1+ν))

2. Bulk Modulus (K):
   K = E / (3(1-2ν))

3. Lamé Constant (λ):
   λ = E·ν / ((1+ν)(1-2ν))

4. Safety Factor:
   SF = σ_y / σ_tensile

5. Strength-to-Weight Ratio:
   S/W = σ_y / ρ  [Pa / (kg/m³)]

6. Stiffness-to-Weight Ratio:
   E/W = E / ρ    [Pa / (kg/m³)]
```

### 2. Pre-loaded Material Library

```
1.  Aluminum 6061       — E=69 GPa,   σ_y=275 MPa   (standart uçak)
2.  Aluminum 7075       — E=72 GPa,   σ_y=505 MPa   (yüksek mukavemetli)
3.  Steel S355          — E=210 GPa,  σ_y=355 MPa   (yapısal)
4.  Steel Stainless 316 — E=193 GPa,  σ_y=170 MPa   (paslanmaz)
5.  Carbon Fiber        — E=230 GPa,  σ_y=1200 MPa  (komposit)
6.  Titanium Grade 5    — E=103 GPa,  σ_y=880 MPa   (hafif, güçlü)
7.  Balsa Wood          — E=13 GPa,   σ_y=40 MPa    (ultra hafif)
8.  Glass Fiber         — E=73 GPa,   σ_y=500 MPa   (GRP)
9.  Magnesium AZ91D     — E=45 GPa,   σ_y=160 MPa   (çok hafif)
10. Kevlar              — E=131 GPa,  σ_y=3600 MPa  (aramid)
```

---

## 🎛️ GUI EDITOR (material_editor_gui.py)

### MaterialEditorDialog
**İşlev:** Yeni malzeme ekle veya mevcut olanı düzenle

**Alanlar:**
- Temel Bilgiler: Ad, Tür, Yoğunluk
- Mekanik Özellikler: E, ν, σ_y, σ_max, σ_c
- Termal: İletkenlik, Genleşme, Erime Noktası
- Diğer: Maliyet, Geri Dönüştürme, Uygulamalar

**Doğrulama:**
```
✓ E > 0
✓ 0 ≤ ν ≤ 0.5
✓ σ_y, σ_max > 0
✓ ρ > 0
→ Geçersiz değerler → ValueError
```

### MaterialManagerTab
**İşlev:** Kütüphane taraması, yönetimi, dışa aktarma

**Özellikler:**
- Tablo: Tüm malzemeleri listelemek (8 sütun)
- Butonlar: Ekle / Düzenle / Sil / CSV Dışa Aktar
- Detay Paneli: Seçili malzemenin tüm özellikleri
- Signal: `materials_changed` → FEA combo box senkronizasyonu

---

## 🔗 APP INTEGRATION

### app_parametric.py Değişiklikleri

```python
# Import eklendi:
from material_editor_gui import MaterialManagerTab

# Tab eklendi (6. sekmede):
self.materials_tab = MaterialManagerTab(MATERIAL_LIBRARY)
self.materials_tab.materials_changed.connect(self._on_materials_updated)
tabs.addTab(self.materials_tab, "🧪 Malzemeler")

# Signal handler eklendi:
def _on_materials_updated(self):
    """FEA combo box'ı güncelle"""
    current = self.fea_material_combo.currentText()
    self.fea_material_combo.clear()
    self.fea_material_combo.addItems(
        list(MATERIAL_LIBRARY.materials.keys())
    )
    # Önceki seçimi koru
    index = self.fea_material_combo.findText(current)
    if index >= 0:
        self.fea_material_combo.setCurrentIndex(index)
```

### Tab Yapısı

```
┌─────────────────────────────────────────────────┐
│ Parametric Analysis Tool                        │
├─────────────────────────────────────────────────┤
│ [Konfigürasyon] [Mesh] [Simülasyon] [Sonuçlar] │
│ [Scanner] [🧪 Malzemeler] [⚙️ FEA]             │ ← NEW!
├─────────────────────────────────────────────────┤
│                                                 │
│  + Malzeme Ekle  | ✎ Düzenle  | ✕ Sil        │
│  📊 CSV'ye Dışa Aktar                          │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ Name | Type | Density | E | σy | S/W .. │  │
│  ├──────────────────────────────────────────┤  │
│  │ Aluminum 6061 | aluminum | 2700 | 69.. │  │
│  │ Steel S355    | metal    | 7850 | 210. │  │
│  │ ...                                      │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ SEÇILEN MALZEME DETAYLARI                │  │
│  │                                          │  │
│  │ Aluminum 6061                           │  │
│  │ E: 69.0 GPa                             │  │
│  │ G: 25.9 GPa (hesaplanmış)               │  │
│  │ K: 67.6 GPa (hesaplanmış)               │  │
│  │ ν: 0.330                                │  │
│  │ σ_y: 275.0 MPa                          │  │
│  │ ...                                      │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## ✅ TEST SONUÇLARI

```
[TEST 1] Modülleri yükle
  ✓ material_database yüklendi
  ✓ material_editor_gui yüklendi

[TEST 2] MaterialLibrary oluştur
  ✓ 10 malzeme yüklendi

[TEST 3] Otomatik hesaplamalar
  Aluminum 6061:
  ✓ E:  69.0 GPa
  ✓ G:  25.9 GPa (=69/(2*1.33))
  ✓ K:  67.6 GPa (=69/(3*0.34))
  ✓ λ:  50.4 GPa
  ✓ S/W: 0.10 m/s²
  ✓ E/W: 25.56 m/s²

[TEST 4] Yeni malzeme ekleme
  ✓ Custom Material oluşturuldu
  ✓ Otomatik hesaplamalar doğru
  ✓ Kütüphaneye eklendi

[TEST 5] Arama fonksiyonu
  ✓ Yield > 400 MPa: 5 malzeme bulundu
    - Aluminum 7075: 505 MPa
    - Carbon Fiber: 1200 MPa
    - Titanium: 880 MPa
    - Glass Fiber: 500 MPa
    - Kevlar: 3600 MPa

[TEST 6] CSV Dışa Aktarma
  ✓ CSV dosyası oluşturuldu
  ✓ 12 satır (header + 11 malzeme)

[TEST 7] Doğrulama
  ✓ Geçersiz E değeri yakalaması
  ✓ Error handling çalışıyor

═════════════════════════════════════════════════
✅ TÜM TESTLER BAŞARILI (7/7)
═════════════════════════════════════════════════
```

---

## 📊 KULLANIM ÖRNEKLERİ

### Python API

```python
from material_database import MATERIAL_LIBRARY, MaterialProperties, MaterialType

# Tüm malzemeleri listele
for name in MATERIAL_LIBRARY.materials.keys():
    print(name)

# Malzeme getir
aluminum = MATERIAL_LIBRARY.get_material("Aluminum 6061")
print(f"E = {aluminum.youngs_modulus} GPa")
print(f"G = {aluminum.shear_modulus:.1f} GPa")  # Otomatik hesaplanmış

# Yeni malzeme ekle
custom = MaterialProperties(
    name="My Material",
    material_type=MaterialType.ALUMINUM,
    density=2800,
    youngs_modulus=71,
    poisson_ratio=0.33,
    yield_strength=280,
    tensile_strength=320
)
# G, K, λ otomatik hesaplanır
MATERIAL_LIBRARY.add_material(custom)
MATERIAL_LIBRARY.save_to_file()

# Ara
strong = MATERIAL_LIBRARY.search_by_property("yield_strength", 500, 10000)
for mat_name in strong:
    mat = MATERIAL_LIBRARY.get_material(mat_name)
    print(f"{mat_name}: {mat.yield_strength} MPa, S/W={mat.strength_to_weight/1e6:.2f}")

# CSV dışa aktar
MATERIAL_LIBRARY.export_csv(Path("materials.csv"))
```

### GUI Kullanımı

```
1. app_parametric.py çalıştır
2. "🧪 Malzemeler" sekmesine tıkla
3. "+ Malzeme Ekle" → Yeni malzeme formu
4. Özellikler gir (E, ν, σ_y, vb.)
5. "Kaydet" → Otomatik hesaplamalar yapılır
6. "⚙️ FEA" sekmesindeki combo box otomatik güncellenir
```

---

## 🔐 VERI DEPOSU

### materials.json
```json
{
  "Aluminum 6061": {
    "name": "Aluminum 6061",
    "material_type": "aluminum",
    "density": 2700,
    "youngs_modulus": 69,
    "poisson_ratio": 0.33,
    "yield_strength": 275,
    "tensile_strength": 310,
    "...": "..."
  },
  "...": {}
}
```

**Not:** Hesaplanan alanlar (G, K, λ, S/W) JSON'e kaydedilmez. 
Yüklenirken `__post_init__` aracılığıyla otomatik yeniden hesaplanır.

---

## 📁 DOSYA YAPISI

```
cfd_fea_tools/
├── material_database.py          (470 satır)
│   ├── MaterialType (enum)
│   ├── ApplicationField (enum)
│   ├── MaterialProperties (dataclass)
│   │   ├── __post_init__ → _calculate_derived_properties()
│   │   ├── _validate()
│   │   ├── to_dict() / from_dict()
│   │   └── __str__()
│   └── MaterialLibrary
│       ├── add_material()
│       ├── remove_material()
│       ├── get_material()
│       ├── search_by_type()
│       ├── search_by_property()
│       ├── save_to_file()
│       ├── load_from_file()
│       └── export_csv()
│
├── material_editor_gui.py        (400+ satır)
│   ├── MaterialEditorDialog
│   │   ├── _create_ui()
│   │   ├── _load_material_data()
│   │   ├── _save_material()
│   │   └── get_material()
│   └── MaterialManagerTab
│       ├── materials_changed Signal ← NEW!
│       ├── _create_ui()
│       ├── _refresh_table()
│       ├── _on_selection_changed()
│       ├── _add_material()
│       ├── _edit_material()
│       ├── _delete_material()
│       └── _export_csv()
│
├── app_parametric.py             (UPDATED)
│   └── ParametricAnalysisTool
│       ├── materials_tab (Tab 6) ← NEW!
│       ├── _on_materials_updated() ← NEW!
│       └── fea_material_combo ↔ MATERIAL_LIBRARY sync
│
├── materials.json                (otomatik)
│
├── MATERIAL_SYSTEM_GUIDE.md      (referans)
├── MATERIAL_SYSTEM_STATUS.md     (bu dosya)
├── MESH_THEORY_GUIDE.md          (mesh kriteri)
│
└── test_material_system.py       (7 test adımı)
```

---

## 🎓 MÜHENDİSLİK TEMELİ

### Elastiklik Teorisi (Lineer)

```
Stress: σ = F/A  (Pa)
Strain: ε = ΔL/L (boyutsuz)

Hooke's Law:
  σ = E·ε  (1D)
  σ = 2G·ε + λ·tr(ε)  (3D)

E:  Young's Modulus (çekme/basma katılığı)
G:  Shear Modulus (kayma katılığı)
K:  Bulk Modulus (hacim katılığı)
λ:  Lamé Constant (plastiklik)
ν:  Poisson's Ratio (yanal daralmasi)
```

### Güvenlik Faktörü

```
SF = σ_y / σ_max

σ_y:   Akma mukavemeti (yield)
σ_max: Çekme mukavemeti (tensile)

SF > 1.5 → GÜVENLI (mühendislik hedefi)
SF < 1.0 → HATA (kırılma riski)
```

### Ağırlık Oranları

```
Strength-to-Weight = σ_y / ρ
  → Yüksek → Hafif ve güçlü (aerospace)
  
Stiffness-to-Weight = E / ρ
  → Yüksek → Hafif ve katı (uçak kanat)

Örn: Titanium vs Aluminum
  Ti:  S/W = 880/4500 = 0.195 (E/W=22.9)
  Al:  S/W = 275/2700 = 0.102 (E/W=25.6)
  → Ti: %91 daha güçlü/ağırlık
  → Al: %7 daha katı/ağırlık
```

---

## 🚀 BAŞLANGIÇ KODU

```bash
cd D:\bilsem_beyin\cfd_fea_tools

# Test çalıştır
python test_material_system.py

# GUI aç
python app_parametric.py
# → "🧪 Malzemeler" sekmesine git
```

---

## ⚠️ BILINEN SINIRLAMA

1. **Sıcaklık bağımlılığı:** E(T) hesaplaması yok
2. **Anizotropi:** 3D tensor modülleri yok (izotropik varsayımı)
3. **Fatigue:** S-N eğrisi modeli yok
4. **Creep:** Zaman-bağımlı deformasyon yok
5. **Plastisitas:** Von Mises akma kriteri sadece linear elastic

→ **Gelecek versiyonlarda eklenebilir**

---

## 📚 KAYNAKLAR

- Popov, E. P. (2007). "Engineering Mechanics of Solids" (Prentice Hall)
- Shames, I. H., Cozzarelli, F. A. (1991). "Elastic and Inelastic Stress Analysis"
- ANSYS Material Library
- MatWeb: matweb.com

---

## ✅ KONTROL LİSTESİ

```
CORE FUNCTIONALITY:
 [x] MaterialProperties dataclass
 [x] Otomatik hesaplamalar (G, K, λ, S/W, E/W)
 [x] 10 pre-loaded malzeme
 [x] Doğrulama (E, ν, σ ranges)
 [x] JSON persistence

GUI COMPONENTS:
 [x] MaterialEditorDialog (form UI)
 [x] MaterialManagerTab (table + buttons)
 [x] signals (materials_changed)
 [x] CSV export

APP INTEGRATION:
 [x] MaterialManagerTab as Tab 6
 [x] FEA combo box sync via signal
 [x] Unicode fix (Windows console)

TESTING:
 [x] Module imports
 [x] Library initialization
 [x] Derived calculations
 [x] New material addition
 [x] Property search
 [x] CSV export
 [x] Validation

DOCUMENTATION:
 [x] MATERIAL_SYSTEM_GUIDE.md
 [x] MATERIAL_SYSTEM_STATUS.md (this)
 [x] Code docstrings
 [x] Usage examples
 [x] Theory foundation

DEPLOYMENT:
 [x] Production-ready code
 [x] Error handling
 [x] Type hints
 [x] Performance OK
```

---

## 📊 İSTATİSTİKLER

| Metrik | Değer |
|--------|-------|
| **Kod satırı (core)** | 470 |
| **Kod satırı (GUI)** | 410 |
| **Pre-loaded malzeme** | 10 |
| **Otomatik parametreler** | 6 |
| **Test adımı** | 7 |
| **Test başarı oranı** | 100% |
| **Doğrulama kuralı** | 5 |
| **Uygulama alanı** | 5+ |

---

## 🎯 SONUÇ

**Bilsem_beyin malzeme sistemi:**
- ✅ **Fonksiyonel:** Tam test edildi ve hazır
- ✅ **Entegre:** App_parametric.py'ye bağlandı
- ✅ **Genişletilebilir:** Yeni malzeme + özellikler kolay
- ✅ **Üretim kalitesi:** Error handling, validation, docs
- ✅ **Teorik tabanlı:** Elastiklik, malzeme bilimi

**Kullanıma hazır!**

---

**Status:** 🟢 **PRODUCTION READY**  
**Date:** 2026-04-07  
**Version:** 2.0  
**Maintainer:** Teknofest bilsem_beyin Project Team
