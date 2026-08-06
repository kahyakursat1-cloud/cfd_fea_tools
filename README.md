# CFD/FEA V&V Pipeline

[![CI](https://github.com/kahyakursat/cfdfea-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/kahyakursat/cfdfea-tools/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)

OpenFOAM (CFD) + CalculiX (FEA) tabanlı, **ASME V&V 20 / FAR-CS-23** uyumlu
endüstri ön-tasarım analiz hattı. Doğrulanmış (validated) çözücü, mesh
bağımsızlık (GCI), yük zarfı (V-n), CFD→FEA coupling ve otomatik raporlama.

Giriş noktaları:

| Ne yapmak istiyorsun | Komut |
|---|---|
| **Önce ortamı doğrula** | `python pipeline.py doctor` |
| Sertifikasyon zinciri (yük → FEA → rapor) | `python pipeline.py all` |
| Tek geometrinin araç analizi (headless) | `python vehicle_pipeline.py <STL>` |
| Etkileşimli analiz stüdyosu (GUI) | `python launcher.py` → **Araç Analizi** (`app_analyzer.py`) |
| Eski parametrik GUI | `python launcher.py` → Parametrik (`app_parametric.py`) |

## Kurulum

Bağımlılıklar ağır ML/GUI yığınından ayrıştırılmıştır — yalnızca gerekeni kur:

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate

pip install -e .                  # çekirdek: headless CFD/FEA pipeline
pip install -e ".[gui]"           # + PySide6 arayüzleri (launcher.py)
pip install -e ".[gui,viz]"       # tam sistem (görüntü-işleme/YOLO → ../goruntu_isleme/)
```

`pip install -e .` bağımlılıkları ve **kanonik `analysis` katmanını** kurar — dışarıdaki
bir script'ten `from analysis.openfoam_runner import run_cfd` çalışır. Kök dizindeki flat
modüller (`pipeline`, `vehicle_pipeline`, `constants`, …) bilerek kurulmaz: bu kadar genel
adlar site-packages'ta başka paketleri gölgeler. **Komutları repo kökünde koş** (src/
layout'a taşınması Faz 4).

**Harici araçlar** (Python paketi değil): OpenFOAM 11 (CFD), CalculiX `ccx` (FEA;
doğrulandığı sürüm 2.17), opsiyonel OpenVSP 3.50 (`openvsp` conda env) ve OpenRocket
(`orenv`, JVM). Hangisinin kurulu olduğunu `python pipeline.py doctor` söyler — çözücünün
gerçekten kullandığı arka uçtan (`CFD_BACKEND=wsl|docker`) sınar. Bkz.
[Donanım Notu](#donanım-notu).



## Çalışma Zarfı (Geçerlilik Sınırları)

Tablo elle yazılmaz — `python zarf.py --yaz` ile kök dizindeki V&V kanıt JSON'larından
üretilir; verdiktler kanonik `report_generator.gci_verdict` ile hesaplanır. Kanıt dosyası
olmayan satır "beyan" olarak işaretlenir.

<!-- ZARF:BASLANGIC — `python zarf.py --yaz` uretir, elle duzenleme -->
| Koşul | Güvenilirlik | Kanıt |
|-------|--------------|-------|
| Bağlı akış, 2D airfoil mutlak $C_d$ (M<0.3) | ✅ Yüksek | NASA TMR NACA0012 α=0°: GCI %1.7 (p=0.666), TMR sapması %4.9 |
| Bağlı akış, 2D airfoil taşıma $C_l$ (α=8°) | ⚠️ Bantlı | NASA TMR NACA0012 α=8°: en ince grid (917,504 hücre) Cl=0.8556 vs TMR 0.862 → sapma %0.7; ancak 3-grid serisi ıraksıyor (p=-2.463) → sayısal belirsizlik Richardson ile ölçülemedi |
| 3D araç mesh yakınsama (snappyHexMesh) | ⚠️ Gösterilemedi | MiniHawk 3D snappyHexMesh: GCI %0.12, p=3.898 (asimptotik aralık DIŞI) — TARİHSEL veri (2026-06-03, eski boru hattı; yeniden üretilemez, bkz. mesh_independence.json/_uretilemez) |
| 3D ince-kanatlı İHA — araç hattı GCI | ⚠️ Bant yok | MiniHawk (güncel koşu): Cd=0.0192, Cl=0.0915, gövde yüzeyi 24,477 yüz ile çözüldü, ref_bump=3. Mesh bağımsızlık BANDI YOK — mesh-bağımsızlık ÇALIŞMASI YAPILMADI — ince seviye YAKINSAMADI: rezidueller PLATOYA OTURDU (limit cevrimi) {'Ux': '2.91e-06', 'Uy': '6.30e-04', 'Uz': '2.26e-05', 'p': '2.18e-04'} —. Ölçülen y⁺ ort **129** — duvar-fonksiyonu bandı (30-300) İÇİNDE. Cl=0.0915 oysa NACA2412 α=0'da ~0.25 — kamburluk hâlâ çözülmüyor; sınır ince-özellik (firar kenarı) çözünürlüğünde |
| 3D İHA, gerçek NACA kanat (ilk doğru geometri) | ⚠️ Yalnız eğilim | MiniHawk gerçek NACA2412 kanatla (ilk kez): Cd=0.0191 ± %54 (2 seviye vekil bant; 'orta' seviye mesh kapısında reddedildi). Kutu-kanat hatası Cd'yi %30 yüksek, y⁺'yi 8× büyük gösteriyordu (y⁺ 4114→524). Cl=0.0074 oysa NACA2412 α=0'da ~0.25 — kamburluk ÇÖZÜLMÜYOR: en ince boyut yüzey hücresinin 0.6 katı (hedef ≥6) |
| 3D künt cisim — araç hattı GCI + literatür | ⚠️ Bantlı | Küp (Hoerner 1.05): Cd=1.113 → sapma %6.03, Richardson GCI %3.1 (p=2.386, asimptotik); ancak 4-seviye LSR U=%58 (asimptotik-altı) |
| 3D araç $C_d$ — V&V/UQ bandı | ⚠️ Bantlı | Ölçülen validasyon bandı — bluff %6.0 |
| Cilt sürtünmesi $C_f$ — y⁺ duyarlılığı (2D düz levha) | ✅ Yüksek | Düz levha $C_f$ ↔ Schlichting 1/7-kuvvet: ilk hücre ≤δ99 iken hata ≤%8 (7 seviye); ilk hücre 3.0·δ99 olunca (y⁺≈864) hata %-40 |
| Araç tipi sınıflandırma (geometri → analiz ayarı) | ✅ Yüksek | TAM KÖR üçüncü NX ailesi (27 geometri): analiz ayarını belirleyen preset doğruluğu %96, ince tip %74, kural tek başına %70 — öğrenilen kNN taşıyor (ilk ayrık sette preset %100, ama o set son turda hata analizine konu oldu) |
| Yapısal — lineer statik (kiriş) | ✅ Çok yüksek | Ankastre kiriş ↔ Euler-Bernoulli: sehim %1.0, gerilme %3.9 |
| Yapısal — gerilme konsantrasyonu ($K_t$) | ✅ Yüksek | Delikli plaka Kt ↔ Heywood: tepe gerilme %1.7 (C3D10, 6637 eleman) |
| Stall / $C_{L,max}$ | ⚠️ ±2-3°, ±%15 (RANS) | beyan — kanıt dosyası yok |
| Ayrılmış akış — yeniden-yapışma uzunluğu (2D basamak) | ⚠️ Yalnız eğilim | Geriye-basamaklı akış ↔ Driver & Seegmiller 1985 (Re_H=37500): yeniden-yapışma kOmegaSST ile Xr/H=5.54 vs deney 6.26 → %-12; kEpsilon bu kurulumda sabit noktaya OTURMUYOR (20000 iterasyon, rezidüeller platoda) |
| y⁺<1 transition (duvar-çözünür) | ❌ Kapsam dışı | beyan — kanıt dosyası yok; C-grid / DES gerekir |
<!-- ZARF:SON -->

## Hızlı Başlangıç

```bash
# 0) Ortam kontrolü — saatlik koşuyu başlatmadan önce
python pipeline.py doctor

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

**Araç akışı (modern, `analysis/` tabanlı) ve güven katmanı:**

| Dosya | Sorumluluk |
|-------|------------|
| `analysis/` | KANONİK CFD/FEA katmanı — case kurulumu, mesh kalite kapısı, ccx, frd okuma |
| `vehicle_pipeline.py` | Headless araç CFD/FEA akışı — otomatik V&V/UQ bandı üretir |
| `app_analyzer.py` | Analiz stüdyosu GUI — sonuç rozeti fizik kapısından geçer |
| `validity_envelope.py` | **Güven kapıları:** kurulum (ölçek/eksen/A_ref) + fiziksel kabul-edilebilirlik + geçerlilik-zarfı sınıfı |
| `zarf.py` | Yukarıdaki çalışma-zarfı tablosunu kanıt JSON'larından üretir |
| `kanit.py` | Kanıt manifesti — hangi dosya kanıt, hangisi artefakt, hükmü ne |
| `on_kontrol.py` | Ön-kontrol (`pipeline.py doctor`) — ortam gerçekten koşabilir mi |
| `regresyon.py` | Gerçek-çözücü regresyonu + JSON verdikt (gecelik cron) |

**"Bu araç neyi doğrulanmış biliyor?"** — kökteki 50+ JSON'un hangisi gerçek V&V kanıtı
olduğu isimden anlaşılmıyor. Manifest bunu sınıflar ve hükümleriyle listeler:

```bash
python kanit.py            # kanıt tablosu (vaka + ✅/⚠️/❌ hüküm)
python kanit.py --eksik    # hükmü olmayan veya eskimiş kanıtlar
python kanit.py --json     # kanit_manifest.json
```

## Sonuca Güven: Üç Kapı

Bir sayı mühendislik kararına girmeden önce üç bağımsız kapıdan geçer:

0. **Kurulum kapısı** (`validity_envelope.geometry_sanity`) — çözücüden **önce**, saatlik
   koşuyu boşa harcamamak için. Yanlış kurulmuş bir analiz fiziksel olarak makul bir sayı
   üretir (Cd pozitif, mesh temiz, iterasyon yakınsamış) — hiçbir sonuç kontrolü yakalayamaz
   çünkü sayı doğrudur, sadece *başka bir problemin* cevabıdır. Yakaladıkları:
   - **Ölçek:** mm cinsinden ihraç edilmiş STL (Reynolds ve Cd tamamen kayar)
   - **Eksen:** dikey modellenmiş roket/uçak (frontal izdüşüm en büyükse akış ekseni yanlış)
   - **Referans alan:** `--tip ucak` planform alanı alır; geometri kanat benzeri değilse Cd
     doğrudan alan oranı kadar yanlış olur
   - **Pürüzsüz gövde:** keskin-kenar oranı < 0.02 (küre/kapsül) ise ayrılma geçiş-güdümlüdür
     ve duvar-fonksiyonlu RANS **sistematik** şaşırır → sonuç yalnız EĞİLİM düzeyinde
   Uyarılar raporun **en üstünde** durur; kurulum hatası altındaki her bölümü geçersizler.

1. **Fizik kapısı** (`validity_envelope.force_admissibility`) — negatif/sıfır sürükleme,
   makul olmayan Cd/Cl mertebesi, hücum açısıyla ters işaretli taşıma. Sayısal yakınsama
   bunu kurtaramaz: yakınsamış ama fizik-dışı koşu **ZARF-DIŞI**'na indirilir, rapor
   banner'ı ve GUI rozeti "tasarımda kullanılmaz" der.
   Cd üst sınırı geometri sınıfına bağlıdır — evrensel `2.5` (künt cisim: küp ≈1.05,
   levha ≈1.98), akış-yönlü geometri bilindiğinde çağıran `CD_MAX_STREAMLINED = 0.5`
   geçirir. Tek eşik künt-cisim analizini haksız yere reddeder (gerçek-çözücü
   regresyonunda ölçüldü).
2. **Geçerlilik zarfı** (`classify_cfd`) — DOĞRULANMIŞ / YALNIZ-EĞİLİM / ZARF-DIŞI sınıfı,
   3-mesh GCI bandının varlığına ve α/Mach rejimine göre.

Mesh kalite kapısı (`analysis/openfoam_runner.mesh_quality_gate`) bunlardan önce, çözücü
başlamadan çalışır; eşikler `analysis/thresholds.py`'de tek kaynaktır.

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

**Doğrulama betikleri** (hepsi GERÇEK çözücü koşar, mock yok):

| Betik | Ne doğrular |
|---|---|
| `python pipeline.py doctor` | ortam: arka uç, OpenFOAM, ccx, disk |
| `python regresyon.py` | hat regresyonu: kiriş ↔ Euler-Bernoulli, küp Cd ↔ Hoerner |
| `check_cfd_pipeline.py` | küre STL → snappyHexMesh → foamRun → Cd/Cl |
| `check_fea_pipeline.py` | küre → tet mesh → ccx → sonuç okuma |
| `check_vehicle_validation.py` | keskin kenarlı küp Cd ≈ 1.05 (Hoerner 1965) çapası |
| `validate_pipeline.py` | ölçülen validasyon bandı → `validation_band.json` |
| `verify_system.py` | bağımlılık + modül envanteri |
| `check_integration.py` | ⚠️ yalnız HAT DUMAN TESTİ — sayıları analiz sonucu değildir |

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

## Geliştirme

```bash
pip install -e ".[dev]"
pre-commit install                 # her commit'te ruff + hijyen kontrolü

ruff check .                       # lint (yazarın kompakt stili korunur, format yok)
pytest -m "not external"           # harici araç gerektirmeyen testler (CI bunu koşar)
pytest --cov                       # kapsam raporu

pytest -m external                 # GERÇEK çözücü: ccx + OpenFOAM uçtan uca
python regresyon.py                # aynısı + JSON verdikt (gecelik cron için)
python regresyon.py --hizli        # yalnız FEA zinciri (~5 s)
```

**Gerçek-çözücü regresyonu.** Birim testlerin tamamı mock; case yazımını, WSL/docker arka
ucunu veya `.frd` okumayı bozan bir değişiklik onları yeşil bırakır. `external` işaretli iki
test bu zinciri analitik referansa karşı koşturur (ankastre kiriş ↔ Euler-Bernoulli; küp Cd
↔ bluff-body mertebesi + fizik kapısı). CI'da OpenFOAM/ccx olmadığı için orada atlanır —
`regresyon.py` gecelik görev olarak çalıştırılmalıdır.

CI (`.github/workflows/ci.yml`) Python 3.11/3.12'de ruff + pytest çalıştırır.
`external` / `slow` / `gui` işaretli testler (OpenFOAM, CalculiX, conda env veya
PySide6 gerektirenler) CI'da atlanır.

**Üretilen artefaktlar** (`aoa_polar/`, `mesh_independence/`, `test_*_run/` ve kök
seviye sonuç JSON'ları) `.gitignore`'dadır (~6 GB). Kaynak girdiler
(`materials.json`, `config.yaml`) izlenir.
