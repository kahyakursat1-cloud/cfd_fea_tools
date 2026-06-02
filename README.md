# CFD/FEA V&V Pipeline

OpenFOAM (CFD) + CalculiX (FEA) tabanlı, **ASME V&V 20 / FAR-CS-23** uyumlu
endüstri ön-tasarım analiz hattı. Doğrulanmış (validated) çözücü, mesh
bağımsızlık (GCI), yük zarfı (V-n), CFD→FEA coupling ve otomatik raporlama.

## Çalışma Zarfı (Geçerlilik Sınırları)

| Koşul | Güvenilirlik | Kanıt |
|-------|--------------|-------|
| Bağlı akış α≤8°, M<0.3 | ✅ Yüksek | NACA0012 α=4°: Cd %2.2 hata |
| Yapısal (lineer statik) | ✅ Çok yüksek | Kiriş analitik %0.05 |
| Mesh yakınsama | ✅ | GCI 0.09% |
| Stall / CLmax | ⚠️ ±2-3°, ±%15 (RANS) | — |
| y⁺<1 transition / ayrılmış akış | ❌ Kapsam dışı | C-grid / DES gerekir |

## Hızlı Başlangıç

```bash
# Compute-hafif tam akış: yük zarfı -> kritik FEA -> rapor
python pipeline.py all

# Tekil aşamalar
python pipeline.py loads          # V-n zarfı + kritik yük durumları
python pipeline.py fea            # kritik gust yükünde kanat FEA
python pipeline.py vspaero 0 4 8 12 16   # OpenVSP VLM hızlı polar (~saniyeler)
python pipeline.py rocket rockets/simple.ork  # OpenRocket uçuş simülasyonu (roket)
python pipeline.py validate-fea   # ankastre kiriş doğrulama
python pipeline.py report         # mevcut JSON'lardan V&V raporu
python pipeline.py coupling <VTK> <STL>   # CFD basınç -> FEA kuvvet
```

## İki-Katmanlı Aerodinamik (Hız vs Fidelite)

| Yöntem | Süre | Verir | Kullanım |
|--------|------|-------|----------|
| **VSPAERO (VLM)** | ~saniyeler | Cl-α eğimi, induced drag | Hızlı tasarım taraması, çapraz-kontrol |
| **OpenFOAM (RANS)** | ~saatler | Viskoz Cd, stall, ayrılma | Final doğrulama |

İki yöntem lift eğiminde **%11 içinde uyumlu** (0.061 vs 0.069/°) — bağımsız doğrulama.

Ağır CFD aşamaları ayrı runner'larla (saatlerce, arka plan):

```bash
python run_aoa_polar.py 0 4 8 12 16      # 3D stall polar (mesh sabit, AoA=hız)
python run_prism_3d.py                    # prism-layer 3D mesh + y+ ölçümü
```

## Modüller

| Dosya | Sorumluluk |
|-------|------------|
| `pipeline.py` | Orkestratör — tek giriş noktası, uçak konfig tek kaynak |
| `aircraft_geometry.py` | Parametrik uçak modeli (Wing/Fuselage/Empennage) |
| `mesh_generator.py` | snappyHexMesh + **y⁺ hedefli prism layer** + STL/OpenVSP |
| `simulation_runner.py` | OpenFOAM case kurulum, çözüm, kuvvet çıkarımı, AoA sweep |
| `fea_runner.py` | CalculiX S3 shell FEA, kanat yapısal değerlendirme |
| `structural_loads.py` | **V-n manevra+gust zarfı (FAR-23)**, kritik yük durumları |
| `coupling_fsi.py` | **1-way FSI**: CFD p-alanı → FEA düğüm kuvveti (korunumlu) |
| `validation_suite.py` | NACA0012 (CFD) + ankastre kiriş (FEA) deneysel doğrulama |
| `transition_polar.py` | kOmegaSSTLM transition (2D O-grid — geometrik limit, bkz. notlar) |
| `openvsp_bridge.py` | **OpenVSP**: parametrik geometri→STL + **VSPAERO VLM** hızlı polar |
| `openrocket_bridge.py` | **OpenRocket** (orhelper/JPype): roket uçuş sim — stabilite, apogee, Cd-Mach |
| `report_generator.py` | ASME V&V 20 raporu + 300 DPI figürler + VLM/RANS çapraz-kontrol |

## Araç Tipleri

| Tip | Hızlı katman | Yüksek-fidelite | Yapısal |
|-----|--------------|-----------------|---------|
| **Sabit-kanat** | VSPAERO (VLM) | OpenFOAM (RANS) | CalculiX (kanat) |
| **Roket** | OpenRocket (Barrowman+6DOF) | OpenFOAM (CFD Cd-Mach) | CalculiX (fin) |

**OpenRocket kurulumu** (orenv conda env): `python 3.11 + orhelper + jpype1 + openjdk=17`,
`JAVA_HOME=<orenv>/Library/lib/jvm`. OpenRocket.jar Java 17 ister.

## Sertifikasyon Zinciri

```
V-n zarfı (structural_loads)
   └─ kritik durum: Vc_gust n=9.5  (hafif İHA'da gust dominant)
        └─ kanat FEA (fea_runner) → SF: limit 2.32, ultimate 1.55 ✅
```

## Doğrulama Yöntemi (V&V)

1. **Verification (sayısal doğruluk):** 3 kademeli mesh + Richardson/GCI
2. **Validation (fiziksel doğruluk):** NASA Ladson NACA0012 + Euler-Bernoulli
3. **Coupling tutarlılığı:** ∑F_CFD = ∑F_FEA (korunum 3.9e-15)

## Bilinen Sınırlar (Dürüst)

- **2D y⁺<1 transition:** tek-blok radyal O-grid non-orthogonality (82°) +
  ince hücre kombinasyonu çözücüyü bozar. Doğru araç: C-grid/eliptik mesh
  generator (ayrı geliştirme).
- **Stall sonrası:** RANS ayrılmış akışta güvenilmez; DES/LES veya tünel.
- **Tam-araç FEA:** gövde rijitliğini abartır; yapısal marj için kanat-only kullan.

## Donanım Notu

- CFD: WSL2 + OpenFOAM 11; MPI WSL bayrakları gerekli
- FEA: WSL CalculiX (ccx)
- Mesh: snappyHexMesh paralel; prism layer first-layer y⁺=1 (~21µm @ V=15)
