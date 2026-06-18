# Uygulama & Analiz İyileştirme Yol Haritası

**Tarih:** 2026-06-17 · **Kapsam:** Otopilot CFD/FEA araç-analiz uygulaması
**Yöntem:** Bu oturumun somut dersleri + otomatik-CFD literatür best-practice'leri (NASA TMR, ASME V&V 20, Ansys Fluent Aero, OpenFOAMGPT, DrivAerML).

Öncelik: 🔴 yüksek-ROI/düşük-emek · 🟡 orta · 🟢 ileri/düşük-öncelik.
Her madde: **ne / neden / emek**.

> **Durum (2026-06-17):** "Boşa koşuyu önle" sprinti TAMAM — ✅ **1.1 mesh-kalite geçidi**,
> ✅ **1.2 diverjans bekçisi** (NaN/inf → BAŞARISIZ; canlı erken-abort dürüstçe ertelendi),
> ✅ **1.3 orphan-önleme** (WSL-timeout sarma + pkill; ses-altı+süpersonik), ✅ **1.4 süre/maliyet
> bandı**, ✅ **2.3 lift-bilinçli far-field**. Kalan: **çözücü-koşusu/derin** (2.1 validation
> sistematik, 2.2 GCI-oto, 2.4 wake-drag, 2.5 y⁺-oto-düzelt, 3.x bbox-tavanı) — laptopta
> ağır ya da çok-oturumluk; öner-onayla + MEMORY ile yönetilir.

---

## 1. Boşa koşuyu önle — "akıllı kapılar" (en yüksek ROI)

Bu oturumda saatler, **çözmeden önce yakalanabilecek** sorunlara harcandı (nonOrtho-90
diverjans, timeout, orphan süreç). Literatür de aynısını söylüyor: *"skew/AR defektli
mesh'ler refine veya exclude edilir; yakınsama drag-stabilizasyonu + residual ile."*

### 1.1 🔴 Mesh-kalite ÖN-GEÇİDİ (pre-solve gate)
**Ne:** snappyHexMesh/gmsh sonrası, çözücüden ÖNCE `checkMesh` parse et; eşik aşılırsa
(maxNonOrtho>70, maxSkew>4, AR>~5e4, negatif hacim) → (a) otomatik bir kademe kabalaştır
ve yeniden mesh'le, (b) olmuyorsa kullanıcıya net "mesh kalitesiz, çözüm güvenilmez"
de ve KOŞMA. **Neden:** Bu oturumun en büyük zaman kaybı; diverjans hep kötü mesh'tendi.
**Emek:** Düşük-orta. (mesh_quality parse zaten var; gate + auto-coarsen ekle.)

### 1.2 ✅ Erken-abort + yakınsama bazlı durdurma — `divergence_in_log` + `_foam_serial_early_stop`
**Yapıldı:** (a) Diverjans bekçisi `divergence_in_log` — NaN/inf/FPE/Foam::error → BAŞARISIZ
(garbage'ı güvenme). (b) **Cd-YAKINSAMA ERKEN-DURDURMA**: residualControl (1e-4) çoğu kaba
case'de plato → tetiklenmez → solver `end_time`'a kadar boşa koşardı. Artık foamRun arka
planda, `coefficient.dat`'tan **Cd canlı izlenir** (case /mnt/d → Windows'tan); son 50 iterde
Cd-drift <0.003 → solver **orphan-güvenli öldürülür** (1.3'ün `_wsl_kill`'i). OF-sürüm-bağımsız
(OF.org 11'de runTimeControl yok). **Doğrulandı:** clean_rocket hizli 200→120 iter (%40 az),
Cd ÖZDEŞ (0.275→0.2746). **Not:** Paralel (mpirun) yol bu WSL2'de bozuk → seri yolda kazanç.

### 1.2-not 🔴 Parallel CFD (mpirun) — bu WSL2'de BOZUK (config ile çözülemez)
**Bulgu:** `mpirun -np 1 hostname` bile sıfır-çıktıyla asılıyor → Open MPI 4.1.2'nin bu WSL2'de
temel launch arızası. Denenenler (hepsi başarısız): btl transport, oob loopback, plm isolated,
TMPDIR/tmpfs, hwloc-disable, debug. OF11 sistem Open MPI'sine (`openmpi-system`) bağlı; paketli
alternatif yok. **Çözüm flag DEĞİL → invaziv**: MPI reinstall ya da OF'u MPICH'e karşı yeniden
derleme (sudo + çalışan kurulumu riske atar) → **kullanıcı kararı**. Parallel ~4-6× kazanç sunardı.

### 1.3 ✅ Süreç-yaşamdöngüsü sağlamlığı — `_wrap_timeout` + `_wsl_kill`
**Yapıldı:** Uzun OF adımları (foamRun/snappy/mpirun…) **WSL-içi GNU `timeout -k 10 -s TERM`**
ile sarılır → süre aşımında WSL kendi süreç ağacını öldürür (Windows-tarafı wsl.exe öldürmek
WSL-içi ağacı bırakıyordu → orphan, 50× yavaşlama). Ayrıca Windows-tarafı `TimeoutExpired`'da
`_wsl_kill` ilgili binary'leri `pkill -9 -f` ile temizler (kemer+askı). Birim-testli
(`test_openfoam_runner`). **Süpersonik yol da kapsandı** (`supersonic_cfd._shock_solve`:
WSL-içi timeout sarma + Windows-backstop pkill — rocket_tvc 2h timeout'un yaşandığı yer).

### 1.4 ✅ Maliyet/süre tahmini + ön-uyarı — `_runtime_band` (zaten var)
**Mevcut:** `auto_pilot._runtime_band(regime, quality, lmax)` çözücü-öncesi kaba wall-time
bandı verir (ses-altı + süpersonik); `auto_configure` bunu `tahmini_sure` + pahalı-koşu
uyarısı olarak sunar (öner-onayla felsefesi). Birim-testli (`test_runtime_band`). Kontrol-
kazanımı: yeni kod gerekmedi.

---

## 2. Analiz doğruluğu / V&V — "en iyi analiz" çekirdeği

### 2.1 🔴 Doğrulama (validation) regresyon suite'i (commit'li)
**Ne:** Referans-değerli kanonik vakalar: süpersonik küre Cd (Charters&Thomas, var),
NACA0012 ses-altı (Ladson), bilinen roket; her birine **referans + tolerans** + CI'da
çalışan hafif kontrol. **Neden:** "en iyi analiz" ancak ölçülünce iddia edilir; regresyon
yakalar; yayın-kredibilitesi. **Emek:** Orta. (supersonic_validation.json çekirdek; sistematikleştir.)

### 2.2 🟡 Mesh-bağımsızlık (GCI) otomasyonu — robust mesh ile
**Ne:** `compute_gci`/`gci_verdict` var; eksik olan **3 seviyeyi güvenilir üreten** mesh.
Domain/far-field otomatik boyutlama (aşağı) + 1.1 gate ile birlikte GCI'ı otomatik koştur.
**Neden:** ASME V&V 20: discretization belirsizliği adım-adım. **Emek:** Orta-yüksek.
**Not:** Airfoil drag GCI ayrı zor problem ([[airfoil-drag-gci-acik]]); önce 3B araç-Cd GCI'a odaklan.

### 2.3 ✅ Far-field / domain otomatik boyutlama — `farfield_domain()`
**Yapıldı:** Domain çarpanları geometri-bilinçli. **Taşıyıcı (lift_relevant) cisimde** upstream/
lateral büyütülür (5→7), yüksek |α|'da yanal daha da (→9); küt/eksenel değişmez. Sirkülasyon-
kaynaklı basınç alanı yanal yavaş söner → yakın sınır pressure-drag'i bozar (oturum dersi).
Birim-testli. **Dürüstlük:** lifting koşusu ~%50-100 daha çok taban hücre (hacim ∝ up·lat²) —
doğruluk/maliyet takası docstring'de; max_cells + bg_div sınırlar. Mutlak kazanç koşuyla
ölçülmedi (best-practice gerekçeli varsayılan, spekülatif değil).

### 2.4 ✅ Drag-çıkarımı: far-field/iz momentum-açığı — `farfield_drag.py`
**Yapıldı:** İz-momentum drag (D=ρ∫u_x(U−u_x)dA+∫(p∞−p)dA, **iz-maskeli** — serbest-akış
gürültüsü atılır). OF11 cutPlane örnekleme (gövde arkası 2 boy). Gaussian-iz analitik **%1.1**
doğrulandı. `run_vehicle_analysis` artık **Cd_wake**'i de raporlar: yüzey-Cd ile UYUŞMASI
tek-mesh **yakınsama göstergesi** (3-mesh GCI'nin ucuz vekili), >%12 ayrışması az-çözünürlük
uyarısı. **Dürüst not:** clean_rocket kaba-mesh'te %18 ayrık (eşik-duyarlı) → ince roket izi
(%0.7 açık) az-çözünür; far-field DE aynı çözünürlük duvarında. AMA bu ayrışma tam da
çapraz-kontrolün işaretlediği şey (GCI=%103 ile tutarlı). İyi-çözünür case'de 2.-mertebe avantaj.

### 2.5 🟡 Prizma katman + y⁺ otomasyonu olgunlaştır
**Ne:** y⁺-hedefli ilk-hücre + katman sayısı zaten var; **gerçekleşen y⁺'ı ölç, hedef
dışıysa otomatik düzelt** (duvar-fonk vs low-Re seçimi). **Neden:** Sürtünme-drag doğruluğu
y⁺<1 ya da doğru duvar-fonk ister. **Emek:** Orta.

---

## 3. Otopilot zekâsı / öz-öğrenme

### 3.1 🟡 Sınıflandırma: bbox-tavanını aş (seçici)
**Ne:** Gerçek avcı↔lifting-body bbox'ta ayrılmıyor (genelleme 4/7). bbox-üstü hafif
betimleyici (eğrilik histogramı / küçük PointNet) **yalnız belirsiz çiftlerde**. **Neden:**
Gerçek-dünya isabeti. **Emek:** Yüksek (ayrı yöntem). **Alternatif (ucuz):** öner-onayla +
MEMORY zaten kuyruğu kapatıyor — belki yeterli.

### 3.2 🟡 Cd-aykırılık öğrenmesini besle
**Ne:** `cd_outlier` tip başına ≥5 çapa ister; çeşitli geometride (başarılı) koşu biriktir.
**Neden:** Aykırı-sonuç bekçisi ancak dağılım olunca çalışır. **Emek:** Düşük (ama CFD-zamanı).

### 3.3 🟢 Yönelim-kanoniklestirmeyi genişlet
**Ne:** `canonicalize_axial` yalnız eksenel cismi düzeltiyor; kanat/genel için de
güvenli kanoniklestirme (PCA + sınıf-bilinçli). **Neden:** Rastgele yönelimli CAD. **Emek:** Orta.

### 3.4 🟢 Birim-ölçek tespitini iyileştir
**Ne:** >50→mm sezgisi gerçek CAD'de tutarsız (f16 1.5m çıktı). Geometri-tipi + tipik-boy
priori ile daha akıllı. **Neden:** Re/hız/mesh hepsi ölçeğe bağlı. **Emek:** Düşük-orta.

---

## 4. Kapsam / yetenek (orta-uzun vade)

- 🟢 **Mutlak süpersonik Cd:** ince cisimde laptopta pratik değil ([[supersonik-mutlak-cd-intractable]]); HPC/bulut backend opsiyonu ya da düşük-mertebe panel/şok-ilişki yöntemiyle hızlı-mutlak.
- 🟢 **Transonik/geçiş** olgunlaştırma (shockFluid var; doğrulama derinleştir).
- 🟢 **FSI** (aero→yapısal) zaten var; çok-yük-durumu + flutter taramasını otopilota bağla.
- 🟢 **Bulut/HPC dağıtımı:** ağır koşuları (GCI, viskoz, sweep) remote'a gönder; laptop dinlensin.

---

## 5. Önerilen sıra (ilk sprint)

1. **1.1 Mesh-kalite ön-geçidi** + **1.2 erken-abort** + **1.3 süreç yönetimi** → boşa koşu biter (bu oturumun en pahalı dersi).
2. **2.1 Validation suite** → "en iyi analiz" ölçülebilir/savunulabilir olur.
3. **2.3 far-field oto-boyutlama** + **1.4 maliyet uyarısı** → doğruluk + öngörülebilirlik.

Bu 3 adım, uygulamayı "çalışıyor"dan "**güvenilir + verimli**"ye taşır; ağır V&V (GCI,
mutlak Cd) sonra ve gerekirse HPC ile.

## Kaynaklar
- NASA Turbulence Modeling Resource (turbmodels.larc.nasa.gov) — RANS doğrulama, grid aileleri.
- ASME V&V 20-2009 — CFD doğrulama/geçerleme, adım-adım belirsizlik.
- Ansys *Fluent Aero* — otomatik aero iş akışı, koşul-bağımlı best-practice katmanı.
- *OpenFOAMGPT 2.0* (arXiv:2504.19338) — uçtan-uca güvenilir CFD otomasyonu.
- *DrivAerML/DrivAerStar* — mesh-kalite gating + fiziksel-aralık filtreleme.
- *A review of guidelines and best practices for subsonic aerodynamic RANS CFD* (2019).
