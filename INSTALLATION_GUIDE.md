# Kurulum Rehberi — CFD/FEA Parametrik Analiz Sistemi

> ℹ️ **Görüntü-işleme AYRILDI (2026-06-21):** Blender/YOLO sentetik-veri katmanı → `../goruntu_isleme/`. Bu rehberdeki Blender/ultralytics/YOLO kurulum adımları artık o depoya aittir (orada kendi README'si var); CFD/FEA kurulumu burada geçerli.

**Versiyon:** 1.0  
**Tarih:** 2026-04-07  
**Platform:** Windows, Linux, macOS  
**Python:** 3.9+

---

## 📋 İçerik

1. [Sistem Gereksinimleri](#sistem-gereksinimleri)
2. [Hızlı Başlangıç](#hızlı-başlangıç)
3. [Adım Adım Kurulum](#adım-adım-kurulum)
4. [OpenFOAM Kurulumu](#openfoam-kurulumu)
5. [CalculiX Kurulumu](#calculix-kurulumu)
6. [Blender Kurulumu](#blender-kurulumu)
7. [Sistem Doğrulaması](#sistem-doğrulaması)
8. [Sorun Giderme](#sorun-giderme)

---

## Sistem Gereksinimleri

### Donanım

| Bileşen | Minimum | Önerilen |
|---------|---------|----------|
| **CPU** | 4 core | 8+ core |
| **RAM** | 8 GB | 16+ GB |
| **Disk** | 20 GB | 50+ GB |
| **GPU** | Opsiyonel | NVIDIA CUDA (isteğe bağlı) |

### Yazılım

- **Python:** 3.9, 3.10, 3.11
- **OpenFOAM:** v2112, v2206, v2212 (Windows WSL2 / Linux / macOS)
- **CalculiX:** 2.17+
- **Blender:** 3.6+ (Python API desteğiyle)
- **Git:** (klonlama için)

---

## Hızlı Başlangıç

### 1 Dakikada Başlayın

```bash
# 1. Depoyu klonla
git clone <repo-url> cfd_fea_tools
cd cfd_fea_tools

# 2. Python ortamını kur
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Bağımlılıkları yükle
pip install -e .[gui,viz]

# 4. GUI'yi başlat (analiz stüdyosu — kapılı yol)
python app_analyzer.py
```

> ⚠️ **2026-08-02:** Giriş noktası `app_analyzer.py` olarak değişti. Eski `app_parametric.py`'nin analiz sekmeleri çözücüyü hiç çağırmıyor, sahte ilerleme çubuğuyla "tamamlandı" yazıyordu; FEA sekmesi gerilmeyi `yük/100×2.5` ile uydurup "GÜVENLİ" hükmü veriyordu. O yollar artık gerekçeli ret veriyor. `app_parametric.py` yalnız geometri/malzeme kurulumu için kullanılabilir.


---

## Adım Adım Kurulum

### Adım 1: Python Ortamı Kurulumu

#### Windows

```bash
# Python 3.10+ yükle (https://www.python.org/)
# Komut istemini aç

python --version

# Virtual environment oluştur
python -m venv venv

# Etkinleştir
venv\Scripts\activate

# Kontrol
python -c "import sys; print(sys.version)"
```

#### Linux/macOS

```bash
# Python yüklü olduğundan emin ol
python3 --version

# Virtual environment oluştur
python3 -m venv venv

# Etkinleştir
source venv/bin/activate

# Kontrol
python -c "import sys; print(sys.version)"
```

### Adım 2: Bağımlılık Yüklemesi

```bash
pip install --upgrade pip

# Çekirdek + GUI (headless pipeline için sadece: pip install -e .)
pip install -e .[gui,viz]
```

**Bağımlılık grupları `pyproject.toml`'da tanımlı** (tek doğru kaynak):

| Grup | İçerik | Ne zaman |
|------|--------|----------|
| (çekirdek) | numpy, scipy, matplotlib, pandas, pyyaml, trimesh, gmsh | her zaman |
| `gui` | PySide6 | masaüstü arayüz |
| `ml` | torch, ultralytics, scikit-learn, Pillow | YOLO eğitimi |
| `viz` | seaborn, plotly | gelişmiş grafikler |
| `dev` | ruff, mypy, pytest, pre-commit | geliştirme |

### Adım 3: Sistem Bileşenlerini Kontrol Et

```bash
# Python modüllerini kontrol et
python check_integration.py

# Blender kurulumunu kontrol et
python verify_blender.py

# Tam sistem kontrolü
python full_integration_test.py
```

---

## OpenFOAM Kurulumu

### Windows (WSL2 önerilen)

```bash
# WSL2'yi etkinleştir (Windows Features → Windows Subsystem for Linux)
wsl --install

# Ubuntu 22.04 açın ve:
sudo apt-get update
sudo apt-get install -y openfoam

# Kontrol
source /opt/openfoam9/etc/bashrc
blockMesh -help
```

### Linux (Ubuntu 22.04)

```bash
sudo apt-get update
sudo apt-get install -y openfoam

# Bashrc'ye ekle
echo "source /opt/openfoam9/etc/bashrc" >> ~/.bashrc
source ~/.bashrc

# Kontrol
blockMesh -help
```

### macOS

```bash
# Homebrew ile
brew install openfoam

# Kontrol
of-help
```

---

## CalculiX Kurulumu

### Windows (WSL2)

```bash
wsl

sudo apt-get install -y calculix-cgx calculix-ccx

# Kontrol
ccx -v
cgx -help
```

### Linux

```bash
sudo apt-get install -y calculix-cgx calculix-ccx

# Kontrol
ccx -v
cgx -help
```

### macOS

```bash
brew install calculix-cgx

# CCX ikili dosyasını indir ve kur
# https://www.calculix.de/
```

---

## Blender Kurulumu

### Windows

1. **İndir:** https://www.blender.org/download/
2. **Yükle:** Kurulum sihirbazını takip et
3. **PATH'e Ekle:** (Opsiyonel)
   ```
   C:\Program Files\Blender Foundation\Blender 4.0
   ```
4. **Kontrol:**
   ```bash
   blender --version
   ```

### Linux

```bash
# Snap ile (önerilen)
sudo snap install blender --classic

# Kontrol
blender --version
```

### macOS

```bash
# Homebrew ile
brew install blender

# Kontrol
blender --version
```

### Blender Python API Doğrulama

```bash
python verify_blender.py
```

Çıktı örneği:

```
✅ Blender Bulundu: C:\Program Files\Blender Foundation\Blender 4.0\blender.exe
✅ Versiyon: Blender 4.0.1
✅ Python API Çalışıyor
✅ Synthetic Generator Hazır

🚀 Blender tamamen kurulu ve hazır!
```

---

## Sistem Doğrulaması

### 1. Modül Kontrol

```bash
python check_integration.py
```

Beklenen çıktı:

```
✅ aircraft_geometry         — OK
✅ mesh_generator            — OK
✅ simulation_runner         — OK
✅ fea_runner                — OK
✅ mesh_to_cfd               — OK
✅ blender_synthetic_generator — OK
✅ app_parametric            — OK (yalnız geometri/malzeme; analiz YOK)

SONUÇ: 9 passed, 0 failed
```

### 2. Entegrasyon Testi

```bash
python full_integration_test.py
```

Beklenen çıktı:

```
TEST SUMMARY
=================================
Module Imports              ✅ PASS
Aircraft Creation           ✅ PASS
Simulation Job Creation     ✅ PASS
FEA Job Creation           ✅ PASS
Parametric Study           ✅ PASS
Mesh Analysis              ✅ PASS
Material Library           ✅ PASS
Configuration Save/Load    ✅ PASS

RESULTS: 8/8 tests passed

🚀 Tüm testler başarılı!
```

### 3. GUI Başlatma

```bash
python app_analyzer.py
```

> ⚠️ **2026-08-02:** Giriş noktası `app_analyzer.py` olarak değişti. Eski `app_parametric.py`'nin analiz sekmeleri çözücüyü hiç çağırmıyor, sahte ilerleme çubuğuyla "tamamlandı" yazıyordu; FEA sekmesi gerilmeyi `yük/100×2.5` ile uydurup "GÜVENLİ" hükmü veriyordu. O yollar artık gerekçeli ret veriyor. `app_parametric.py` yalnız geometri/malzeme kurulumu için kullanılabilir.


---

## Sorun Giderme

### Problem: "Module not found: PySide6"

```bash
pip install --upgrade PySide6
```

### Problem: "OpenFOAM not found"

```bash
# Windows (WSL2)
wsl
source /opt/openfoam9/etc/bashrc

# Linux
echo "source /opt/openfoam9/etc/bashrc" >> ~/.bashrc
source ~/.bashrc
```

### Problem: "Blender Python API error"

```bash
# Blender tekrar yükle
# Kurulum sırasında "Python API" seçeneğinin seçildiğinden emin ol

python verify_blender.py
```

### Problem: "Memory allocation error"

Mesh boyutunu azalt:
- `mesh_size`: 0.01 → 0.02 (daha büyük = daha hızlı)
- Render çözünürlüğü azalt
- `samples` parametresini düşür

---

## Konfigürasyon Dosyaları

### `config.json` (Opsiyonel)

```json
{
  "cfd": {
    "base_path": "./cfd_cases",
    "default_solver": "simpleFoam",
    "default_processors": 4
  },
  "fea": {
    "base_path": "./fea_cases",
    "default_material": "aluminum_6061"
  },
  "blender": {
    "resolution_x": 1280,
    "resolution_y": 720,
    "samples": 128,
    "num_views": 8
  }
}
```

---

## Ortam Değişkenleri (Opsiyonel)

```bash
# Linux/macOS
export OPENFOAM_HOME=/opt/openfoam9
export CFD_BASE_PATH=$HOME/cfd_cases
export FEA_BASE_PATH=$HOME/fea_cases

# Windows (PowerShell)
$env:OPENFOAM_HOME="C:\OpenFOAM"
$env:CFD_BASE_PATH="$env:USERPROFILE\cfd_cases"
```

---

## Docker (İsteğe Bağlı)

```dockerfile
FROM python:3.10

# Bağımlılıkları yükle
RUN apt-get update && apt-get install -y \
    openfoam \
    calculix-cgx calculix-ccx \
    blender \
    git

WORKDIR /app

# Kod + Python paketleri
COPY . .
RUN pip install -e .[gui,viz]

# GUI port
EXPOSE 5000

CMD ["python", "app_analyzer.py"]
```

**Çalıştır:**

```bash
docker build -t cfd-fea-tool .
docker run -it --rm -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix cfd-fea-tool
```

---

## İlk Kullanım

### 1. GUI'yi Aç

```bash
python app_analyzer.py
```

### 2. Konfigürasyon Sekmesi

- Aircraft tipi seç (MiniHawk UAV, Fixed-Wing, vb.)
- Rüzgar hızı gir: 10-20 m/s
- Mesh boyutu: 0.01-0.02 m

### 4. Simülasyon Sekmesi

- "▶️ Simülasyon Çalıştır" butonuna tıkla
- İlerleme izle
- Sonuçlar "Sonuçlar" sekmesinde görüntülenir

---

## Başarılı Kurulum İşaretleri

✅ Tüm testler pass oldu  
✅ GUI açıldı  
✅ Aircraft seçilebiliyor  
✅ Kamera çalışıyor (opsiyonel)  
✅ OpenFOAM ve CalculiX yüklü  
✅ Blender accessible  

---

## Destek ve Güncellemeler

- **Belgeler:** https://github.com/repo/wiki
- **Sorunlar:** https://github.com/repo/issues
- **Güncellemeler:** `git pull origin main`

---

**Kurulum başarılı! 🚀 Simülasyonlara başlayabilirsiniz.**
