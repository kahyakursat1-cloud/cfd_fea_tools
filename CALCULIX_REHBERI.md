# CalculiX Rehberi — TEKNOFEST 2026

## Kurulum

### Ubuntu 22.04

```bash
sudo apt-get install -y calculix-cgx calculix-ccx

# Kontrol
ccx -v
cgx -v
```

### macOS

```bash
brew install calculix-cgx
```

### Windows

Önerilen: WSL2 + Ubuntu üzerinde veya CCX binary indirme.

---

## Temel Kavramlar

### 1. FEA (Finite Element Analysis) Nedir?

Yapı (kubbe, roket, İHA) mekanik dayanıklılığını sayısal olarak hesaplar.

**Çelik Kubbe örneği:**
- Materyal: Alüminyum
- Rüzgar basıncı: 1200 Pa (40 m/s)
- Hedef: Maksimum gerilme < 290 MPa (yield)

### 2. CAE İş Akışı

```
[CAD Model] → [Mesh] → [Sınır Koşulları] → [Çöz] → [Sonuç]
  (STEP)      (NGX)      (INP file)      (CCX)    (Görselleştir)
```

### 3. Malzeme Özellikleri

| Malzeme | E (MPa) | ν | ρ (kg/m³) | σ_y (MPa) |
|---------|---------|---|----------|-----------|
| Alüminyum 6061 | 69,000 | 0.33 | 2,700 | 290 |
| Çelik S355 | 210,000 | 0.30 | 7,850 | 355 |
| Karbon Fiber | 140,000 | 0.30 | 1,600 | 800 |

**Burada:**
- **E** = Elastiklik modülü (katılık)
- **ν** = Poisson oranı (yanal daralma)
- **ρ** = Yoğunluk
- **σ_y** = Akma gerilmesi (başarısızlık)

---

## Adım Adım: Çelik Kubbe Yapısal Analiz

### Adım 1: CAD Modeli Hazırla

**FreeCAD veya Fusion 360 ile:**

1. Kubbe geometrisi oluştur (örn: 2m çapında yarım küre)
2. Montaj noktaları tanımla (konektör)
3. STEP formatında kaydet: `kubbe.step`

### Adım 2: Mesh Oluştur

**Salome veya Gmsh:**

```bash
# Gmsh ile mesh oluştur
gmsh -2d -format msh2 kubbe.step
# veya CCX tarafından yapılabilir (netgen)
```

### Adım 3: CalculiX Input Dosyası (INP)

Temel template (statik analiz):

```
*HEADING
CELIK KUBBE YAPISAL ANALIZI
*INCLUDE, INPUT=kubbe.msh
*MATERIAL, NAME=ALUMINUM
*ELASTIC
69000, 0.33
*DENSITY
2700
*SECTION, ELSET=KUBBEYI, MATERIAL=ALUMINUM
0.01
*BOUNDARY
FIXED, 1, 6, 0.0
*LOAD
KUBBE_PRESSURE, P, 1200
*STEP
*STATIC
1.0, 1.0
*OUTPUT, FREQUENCY=1
*NODE PRINT, NSET=ALL
U
*ELEMENT PRINT, ELSET=KUBBEYI
S, E
*END STEP
*END
```

**Açıklama:**
- `*MATERIAL` — Malzeme tanımı
- `*ELASTIC` — E (Young modülü), ν (Poisson)
- `*BOUNDARY` — Sınır koşulu (FIXED = 0 yer değiştirme)
- `*LOAD` — Dış kuvvet (P = basınç)
- `*STEP` — Analiz adımı

### Adım 4: Mesh Dosyası Oluştur (Gmsh format)

```
$MeshFormat
2.2 0 8
$EndMeshFormat
$Nodes
4
1 0 0 0
2 1 0 0
3 0.5 1 0
4 0.5 0.5 0.5
$EndNodes
$Elements
2
1 2 2 1 1 1 2 3
2 2 2 1 1 1 2 4
$EndElements
```

### Adım 5: CalculiX ile Çöz

```bash
ccx kubbe.inp

# Sonuçlar kubbe.frd dosyasında
# Loglama: kubbe.sta
```

### Adım 6: Sonuç Görselleştir

**CGX (Grafik arayüzü):**

```bash
cgx kubbe.frd

# Komutlar:
# - "def" = deformed shape göster
# - "max" = maksimum gerilme noktası
# - "sxx, syy, szz" = gerilme bileşenleri
# - "frf" = frequency response
```

**VTK ile ParaView:**

```bash
# İlk olarak FRD'yi VTK'ya dönüştür
# (CalculiX→Gmsh→ParaView workflow)

paraview kubbe_results.vtu
```

---

## Analiz Türleri

### 1. Statik Analiz (Static)

Sabit yüke maruz kalma.

```
*STEP
*STATIC
1.0, 1.0
```

**Çelik Kubbe:** Rüzgar basıncı altında yer değiştirme ve gerilme.

### 2. Özdeğer Analizi (Frequency)

Doğal titreşim frekansları.

```
*STEP
*FREQUENCY
10
```

**Çelik Kubbe:** "Kubbe ne kadar hızlı sallanabilir?"  
→ İlk mod ~3.5 Hz (rüzgarın uyarma frekansı <1 Hz, güvenli)

### 3. Burkulma (Buckling)

Yapı ne kadar basınç altında çöker?

```
*STEP
*BUCKLE
5
```

**Çelik Kubbe:** Kritik basınç = ?  
→ Eğer > 2000 Pa (çok rüzgarlı koşullar), emniyetli

### 4. Termal Analiz (Thermal)

Sıcaklık dağılımı ve termal gerilmeler.

```
*STEP
*HEAT TRANSFER
1.0, 1.0
```

---

## Örnek: Çelik Kubbe Statik Çözümü

### INP Dosyası (Detaylı)

```ini
*HEADING
CELIK KUBBE - 40 m/s RUZGAR ANALIZI
*INCLUDE, INPUT=kubbe.msh
*MATERIAL, NAME=AL6061
*ELASTIC
69000, 0.33
*PLASTIC
290, 0.01
250, 0.02
*DENSITY
2700
*SECTION, ELSET=SHELL_ELEMENTS, MATERIAL=AL6061
0.01
*BOUNDARY
MOUNT_POINTS, 1, 6, 0.0
*CLOAD
PRESSURE_FACE, P, 1200
*STEP, INC=50
*STATIC
0.1, 1.0
*OUTPUT, FREQUENCY=1
*NODE PRINT, NSET=ALL
U, S
*ELEMENT PRINT, ELSET=SHELL_ELEMENTS
S, E
*CONTACT PRINT, FREQUENCY=1
CLOAD
*END STEP
*END
```

### Çalışma

```bash
ccx kubbe.inp > kubbe.log

# İlerleme izle
tail -f kubbe.log

# Sonuç kontrol
grep "INCREMENT SIZE" kubbe.log
```

### Sonuç Yorumlama

`kubbe.dat` dosyasından:

```
Node 1: U1=0.123 mm, U2=0.456 mm, U3=-1.234 mm
         S11=45.2 MPa, S22=23.1 MPa, S33=-10.5 MPa
         MISES=52.3 MPa (Safety Factor = 290/52.3 = 5.5) ✅

Node 125: MISES=289.9 MPa (Kritik!) SF = 1.0 ⚠️
```

**Yorum:** 
- Çoğu bölge güvenli (SF > 2)
- Node 125 kritik → tasarım değişim gerekli

---

## Optimizasyon İpuçları

### 1. Mesh Kalitesi
- Aspect ratio < 100 (uzun ince elemanlar kötü)
- Min angle > 30° (ezilmiş elemanlar hata)
- Tool: `checkMesh` (OpenFOAM benzeri)

### 2. Hızı Artır
- Mesh sayısını azalt (coarse → fine)
- Direkt çözücü (SOLVER) seç
- Paralel: `ccx -i kubbe.inp -nprocs 4`

### 3. Yakınsama Sorunu
❌ "NEGATIVE JACOBIAN" → Mesh ters mi?
❌ "NO CONVERGENCE" → Zaman adımı küçült
✅ Energy balance kontrol et

---

## Materiyal Tanımı (Plastisite)

Çelik için (Elastik-Plastik):

```
*MATERIAL, NAME=STEEL
*ELASTIC
210000, 0.30
*PLASTIC
250, 0.0      ! σ_y
280, 0.01
320, 0.05
350, 0.15
```

---

## Ortak Hatalar & Çözümleri

| Hata | Neden | Çözüm |
|------|-------|-------|
| NEGATIVE JACOBIAN | Mesh hatalı | Mesh teftiş, elemanları döndür |
| NO CONVERGENCE | Zaman adımı büyük | deltaT kısalt, NR iterasyon artır |
| File open error | Path yanlış | `*INCLUDE` mutlak path yaz |
| Floating point | Numer. instability | E modülü doğru mu? |

---

## Referanslar

- CalculiX Öğretici: http://www.dhondt.de/
- Examples: `/usr/share/doc/calculix-ccx/examples/`
- Paper: "FEA for Aerospace Structures" — standard literature

---

**Son Güncelleme:** 2026-04-07  
**Sürüm:** CalculiX 2.21
