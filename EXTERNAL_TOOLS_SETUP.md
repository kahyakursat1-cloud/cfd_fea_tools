# Dış Yazılımlar Kurulum Rehberi

**Sistem:** Windows 11 + bilsem_beyin CFD/FEA/ML  
**Hedef:** OpenFOAM, CalculiX, Blender, GMSH kurulumu  
**Tarih:** 2026-04-07

---

## ⚠️ Başlamadan Önce

Eğer sadece **GUI test** etmek istiyorsan:
```bash
python app_parametric.py
```
Bu çalışır (dış yazılımlar olmadan da GUI açılır).

**Gerçek simülasyon** yapabilmek için şu adımları takip et.

---

## 1️⃣ GMSH (Mesh Generator)

### Windows Kurulumu (EN KOLAY)

**A. İndir ve Kur**
1. https://gmsh.info/bin/Windows/ → `gmsh-4.13.1-Windows64.zip` indir
2. Çıkar: `C:\Program Files\gmsh\`
3. PATH'e ekle:
   ```
   Sistem Özellikleri → Gelişmiş → Çevre Değişkenleri
   → Path → Yeni → C:\Program Files\gmsh\bin
   → OK
   ```

**B. Test**
```bash
gmsh --version
# Output: Gmsh 4.13.1
```

---

## 2️⃣ CalculiX (FEA Solver)

### Windows Kurulumu

**A. İndir**
1. http://www.calculix.de/ → Download → Windows binary
2. İndir: `ccx_2.21.exe` ve `cgx_2.21.exe`

**B. Kur**
```bash
# C:\Program Files\CalculiX\ klasörü oluştur
mkdir "C:\Program Files\CalculiX"

# ccx_2.21.exe ve cgx_2.21.exe taşı
# C:\Program Files\CalculiX\ içine
```

**C. PATH'e Ekle**
```
Çevre Değişkenleri → Path → Yeni → C:\Program Files\CalculiX
```

**D. Test**
```bash
ccx -version
# Output: This is CalculiX ccx version 2.21
```

---

## 3️⃣ OpenFOAM (CFD Simulator)

### Windows Kurulumu (WSL2 GEREKLI)

OpenFOAM sadece Linux'ta doğru çalışır. Windows'ta WSL2 kullan.

**A. WSL2 Kur (Eğer yok ise)**

```powershell
# PowerShell'i Yönetici olarak aç, sonra:
wsl --install Ubuntu-22.04
```

**B. WSL2 İçinde OpenFOAM Kur**

```bash
# WSL2 terminal'i aç
wsl

# Ubuntu içinde:
sudo apt update
sudo apt install -y openfoam11

# Test:
of_alias
# Output: OpenFOAM Aliases
```

**C. Windows'tan WSL2'ye Erişim**

```bash
# Windows CMD/PowerShell'den:
wsl bash -c "cd /mnt/d/bilsem_beyin && ls"
```

**Alternatif:** GitHub Codespaces veya Docker kullan (daha kolay)

---

## 4️⃣ Blender (Rendering Engine)

### Windows Kurulumu

**A. İndir ve Kur**
1. https://www.blender.org/download/ → Blender 4.1.0
2. Windows installer indir
3. Çalıştır ve kur → `C:\Program Files\Blender\blender.exe`

**B. Test**
```bash
blender --version
# Output: Blender 4.1.0

# Python API test:
blender --background --python -c "import bpy; print('Blender OK')"
```

**C. GPU Kur (RTX 4060)**
```
Blender aç → Edit → Preferences → System → Cycles
→ Compute Device: CUDA
→ Devices: RTX 4060 checkbox ✓
```

---

## 5️⃣ Python GPU Support (torch+CUDA)

GPU ile ML training için:

```bash
# RTX 4060 için:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Test:
python -c "import torch; print(torch.cuda.is_available())"
# Output: True
```

---

## 📋 Kurulum Kontrol Listesi

```bash
# Her birini test et:

# GMSH
gmsh --version

# CalculiX
ccx -version

# Blender
blender --version

# OpenFOAM (WSL2'de)
wsl bash -c "foamVersion"

# PyTorch GPU
python -c "import torch; print(f'GPU: {torch.cuda.is_available()}')"
```

---

## ✅ Tüm Kurulumlar Tamam mı?

```bash
# bilsem_beyin test
cd D:\bilsem_beyin\cfd_fea_tools
python full_integration_test.py
```

Eğer hepsi pass ederse: **SISTEM HAZIR** ✓

---

## 🐛 Sorun Giderme

### "gmsh command not found"
```
→ PATH'e C:\Program Files\gmsh\bin ekle
→ PowerShell yeniden başlat
```

### "ccx: command not found"
```
→ PATH'e C:\Program Files\CalculiX ekle
→ CMD yeniden başlat
```

### "OpenFOAM not found" (Windows)
```
→ WSL2'de kur, Windows'tan erişim:
   wsl bash -c "foamVersion"
```

### "Blender Python API error"
```
→ Blender Python 3.9+ gerekli
→ blender --python test.py çalışmalı
```

### "CUDA not available" (torch)
```
→ NVIDIA driver güncel mi? nvidia-smi kontrol et
→ PyTorch CUDA version doğru mu?
   pip list | grep torch
```

---

## 🚀 Sonraki Adım

Tüm kurulumlar tamam ise:

```bash
cd D:\bilsem_beyin\cfd_fea_tools
python app_parametric.py
```

6 tab'ın tümü **tamamen fonksiyonel** olacak:
1. ✅ Konfigürasyon
2. ✅ Mesh (GMSH ile)
3. ✅ CFD (OpenFOAM ile)
4. ✅ FEA (CalculiX ile)
5. ✅ Sonuçlar
6. ~~Scanner (open3d ile)~~ — **KALDIRILDI** (fotogrametri modülü 2026-06-10'da
   çıkarıldı; görüntü-işleme katmanı `../goruntu_isleme/`'ye taşındı)

---

**Kurulum Kontakları:**
- GMSH: https://gmsh.info/
- CalculiX: http://www.calculix.de/
- OpenFOAM: https://www.openfoam.com/
- Blender: https://www.blender.org/
- PyTorch: https://pytorch.org/

**Destek:** Kurulumda sorun varsa, her aracı ayrı test et.

---

**Status:** 🟡 Manuel kurulum gerekli (ama adım-adım rehber var)  
**Tahmini Süre:** 30-60 dakika (internet hızına göre)
