# OpenFOAM Rehberi — TEKNOFEST 2026

## Kurulum (Linux)

### Ubuntu 22.04 / 20.04

```bash
# OpenFOAM Foundation sürüm 11 (önerilen)
sudo apt-get update
sudo apt-get install -y openfoam11-default

# Ortam değişkenleri
source /opt/openfoam11/etc/bashrc
```

### Windows (WSL2 üzerinde)
```bash
# WSL2 Ubuntu kurulumu
wsl --install -d Ubuntu-22.04

# Ubuntu terminalde:
sudo apt-get install -y openfoam11-default
source /opt/openfoam11/etc/bashrc
```

---

## Temel Kavramlar

### 1. Domain (Hesaplama Alanı)
Simülasyonun yapılacağı fiziksel alan. 

**Çelik Kubbe örneği:**
- Kubbe çapı: 2 m
- Rüzgar hızı: 20 m/s
- Domain: 10m × 10m × 5m (etrafında 5 kat mesafe)

### 2. Mesh (Kafes)
Domain'i küçük elemanlarla böl. Fine mesh = yüksek doğruluk, yavaş çözüm.

**Benchmark:**
- Coarse: 50K elementi, 30 sn/iterasyon
- Medium: 500K elementi, 5 dakika/iterasyon
- Fine: 2M elementi, 20 dakika/iterasyon

### 3. Boundary Conditions (Sınır Koşulları)

| Koşul | Ne İçin | Örnek |
|-------|---------|-------|
| **Inlet** | Giriş (hava akışı) | U = 20 m/s |
| **Outlet** | Çıkış (basınç) | p = 0 Pa (gauge) |
| **Wall** | Duvar (kubbe) | U = 0 (no-slip) |
| **Symmetry** | Simetri (hesaplama tasarrufu) | Grad(U) = 0 |

### 4. Solver (Çözücü)

| Solver | Kullanım | Ör |
|--------|----------|-----|
| **simpleFoam** | Sabit-hal türbülans (RANS) | Aerodinamik |
| **pimpleFoam** | Geçici (transient) akış | Dinamik |
| **rhoCentralFoam** | Sıkışabilir Euler | Yüksek Mach |

---

## Adım Adım: Çelik Kubbe Aerodinamik Analizi

### Adım 1: Case Klasörü Oluştur

```bash
cd ~/OpenFOAM/runs
cp -r $FOAM_TUTORIALS/incompressible/simpleFoam/motorBike celik_kubbe
cd celik_kubbe
```

### Adım 2: Domain ve Mesh Oluştur (Salome/Gmsh)

**Gmsh ile cube domain:**

```python
import gmsh
gmsh.initialize()
gmsh.model.add("celik_kubbe")

# 10m × 10m × 5m domain
gmsh.model.geo.addPoint(0, 0, 0, 1.0, 1)
gmsh.model.geo.addPoint(10, 0, 0, 1.0, 2)
gmsh.model.geo.addPoint(10, 10, 0, 1.0, 3)
gmsh.model.geo.addPoint(0, 10, 0, 1.0, 4)
# ... (üst yüz noktaları) ...

gmsh.model.geo.synchronize()
gmsh.model.mesh.generate(3)
gmsh.write("mesh.msh")
gmsh.finalize()
```

**Mesh'i OpenFOAM formatına çevir:**
```bash
gmshToFoam mesh.msh -case .
```

### Adım 3: 0/ Klasöründe Sınır Koşulları Kur

**0/U (Hız alanı)**

```
FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    object      U;
}

dimensions      [0 1 -1 0 0 0 0];
internalField   uniform (0 0 0);

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           uniform (20 0 0);  // 20 m/s rüzgar
    }
    outlet
    {
        type            zeroGradient;
    }
    kubbe
    {
        type            noSlip;
    }
    symmetry_left
    {
        type            symmetry;
    }
}
```

**0/p (Basınç)**

```
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      p;
}

dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;

boundaryField
{
    inlet
    {
        type            zeroGradient;
    }
    outlet
    {
        type            fixedValue;
        value           uniform 0;
    }
    kubbe
    {
        type            zeroGradient;
    }
    symmetry_left
    {
        type            symmetry;
    }
}
```

### Adım 4: system/ Dosyalarını Kur

**system/controlDict**

```yaml
application     simpleFoam;
startFrom       startTime;
startTime       0;
endTime         5000;
deltaT          1;
writeInterval   500;
purgeWrite      0;
writeFormat     binary;
timePrecision   6;
runTimeModifiable true;
```

**system/fvSchemes**

```yaml
ddtSchemes
{
    default         steadyState;
}
gradSchemes
{
    default         Gauss linear;
}
convectionScheme
{
    default         bounded Gauss upwind;
}
laplacianSchemes
{
    default         Gauss linear corrected;
}
```

**system/fvSolution**

```yaml
solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-6;
        relTol          0.1;
    }
    U
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-6;
        relTol          0.1;
    }
}
SIMPLE
{
    nNonOrthogonalCorrectors 0;
}
relaxationFactors
{
    p               0.3;
    U               0.7;
    k               0.7;
    epsilon         0.7;
}
```

### Adım 5: Mesh Kontrol

```bash
checkMesh
# Çıktı: Max aspect ratio, non-orthogonality vb.
```

### Adım 6: Çalıştır

```bash
# 4 CPU çekirdeğinde paralel
mpirun -np 4 simpleFoam -parallel -case . > log.simpleFoam &

# İlerlemeyi izle
tail -f log.simpleFoam
```

### Adım 7: Post-Processing (Sonuç)

**ParaView'de görselleştir:**

```bash
# Hasil dosyaları oku
paraFoam -case .
```

**Komut satırında istatistik:**

```bash
# Wall shear stress hesapla
postProcess -func wallShearStress

# Basınç kuvveti hesapla
postProcess -func forces -dict postProcessingDict

# Sonuçları CSV'ye çıkar
foamToEnsight -case .
```

---

## Optimizasyon İpuçları

### 1. Hızı Artır
- **Coarse mesh ile başla** → sonra refine et
- **Paralel çalıştır** → `mpirun -np 8`
- **GPU accelerated** → `Solve with NVIDIA GPU` (nvidia-gko-omapi)

### 2. Doğruluğu Artır
- **Mesh refinement** → wall şekilde fine mesh
- **Turbulence model** → kOmegaSST (daha iyi)
- **Zaman adımı** → Courant number < 1

### 3. Yakınsama (Convergence)
- Residual grafiği düzelse, yakınsadı
- Kuvvetler (force) istikrarlı hale gelirse bitirle

---

## Ortak Hatalar

❌ **"Could not create directory"**
→ `blockMeshDict` kontrol et, noktalar tanımlı mı?

❌ **"k and epsilon not initialized"**
→ 0/k ve 0/epsilon dosyaları oluştur

❌ **"Time step too large"**
→ `Courant number = U*dt/dx > 1` → `deltaT` kısalt

---

## Referanslar

- OpenFOAM User Guide: https://www.openfoam.com/documentation
- CFD Online Forum: https://www.cfd-online.com/
- Paper: "Physics-infused Learning for Aerial Manipulator in Winds" (MiniHawk örneği)

---

**Son Güncelleme:** 2026-04-07  
**Sürüm:** OpenFOAM 11
