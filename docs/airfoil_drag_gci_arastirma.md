# Airfoil Sürükleme (Cd) Mesh-Bağımsızlığı: Kök-Neden Araştırması ve Çözüm Metodolojisi

**Tarih:** 2026-06-16 · **Vaka:** NACA0012, Re=3.4×10⁶, α=4° · **Çözücü:** OpenFOAM 11 simpleFoam, kΩ-SST(-LM)

## 1. Problem

Wake-kümeli C-grid ailesi (task #14) airfoil sürüklemesini fiziksel-olmayan O-grid'den
kurtardı ama **drag GCI hâlâ asimptotik aralıkta değil:**

| Seviye | Hücre | Cd (LM) | Referans (Ladson) |
|--------|-------|---------|-------------------|
| base | 32k | 0.0017 | Cd_turb = 0.0092 |
| mid | 54k | 0.0119 | Cd_free = 0.0064 |
| fine | 92k | **0.0131** | |

Cd referanstan ~%40 yüksek ve **mid→fine artıyor (0.0119→0.0131)** → monoton-yakınsama yok →
gözlemlenen mertebe p anlamsız → GCI **geçersiz** (Celik 2008 asimptotik-aralık koşulu sağlanmıyor).

## 2. Arka plan — airfoil drag'i neden zor?

Toplam Cd ≈ basınç-drag + cilt-sürtünmesi, ~0.006–0.012 mertebesinde; bu **büyük yüzey
kuvvetlerinin küçük farkı**. Küçük bir göreli hata kaynağı (sınır, mesh, TE, geçiş) mutlak
Cd'yi orantısız bozar ve grid-bağımlı hâle getirir → asimptotik aralık zorlaşır.

## 3. Kök-neden analizi (kendi kurulumumuz + literatür)

### 3.1 ⛔ Far-field ÇOK YAKIN — baskın neden
`cgrid_generator.py: R_far=15.0` → far-field **yalnızca ~15 kiriş**. Literatür kesin:
- **500c**: sonlu-sınır etkisi minimal (<%1) — TMR referans kurulumu [1].
- **30c**: drag **~%8 fazla** (hata ağırlıkla **basınç-drag'da**), point-vortex (PV) düzeltmesi yoksa [2,3].
- Dahası: **lift tutarlılığı point-vortex**, **drag tutarlılığı point-SOURCE** gerektirir; yüksek
  drag'da point-source daha kritik [4]. Bizde ne PV ne PS var (düz `freestream`).
- 15c, 30c'den de yakın → grid-bağımlı basınç-drag hatası seviyeler arası değişiyor →
  **Cd'nin monoton yakınsamasını bozan birincil mekanizma budur.**

### 3.2 ⚠ Drag yüzey-entegrasyonla çıkarılıyor (düşük mertebe + TE-duyarlı)
`forceCoeffs` = near-field yüzey-entegrasyonu. Literatür: yüzey-entegrasyon drag'i **~1.5.
mertebe** yakınsar ve **TE tekilliğine** duyarlıdır; far-field/cut-face (CFF, iz momentum-açığı)
yöntemi **2. mertebe** ve TE'den bağımsız [5]. Yavaş + gürültülü yakınsayan niceliği
GCI'a sokmaya çalışıyoruz.

### 3.3 ⚠ Mesh ailesi çok kaba / asimptotik-altı
TMR & resmi OpenFOAM aileleri **449×129 (Family II) → 1793×513** kullanır [1,6]; bizim en incemiz
**340×170 (~58k)**. NACA0012 drag'i için kanonik gereksinim: LE eğriliği + TE + iz + y⁺<1
çözünürlüğü. base=32k asimptotik aralığın **altında** → mid→fine'ın yukarı gitmesi tam bu imzadır
(henüz asimptota girmemiş).

### 3.4 ⚠ Geçiş (LM) grid-duyarlılığı + referans belirsizliği
Re=3.4e6'da **serbest-geçiş Cd≈0.0064 vs tam-türbülans 0.0092** — geçiş konumu çözüme
girer. kΩ-SST-LM (Langtry-Menter γ-Reθ) geçiş başlangıcını yakalamak için akış-yönü
çözünürlüğü ister; grid değişince geçiş noktası kayar → ek monoton-bozma. Tek referansla
kıyas, geçiş kayıyorsa belirsiz [7].

### 3.5 (ikincil) TE işlemi
Sharp-TE tekilliği drag yakınsama mertebesini düşürür [5]. C-grid wake-cut ile bunu doğru ele
alıyor (O-grid'in kapalı-TE skew sorununun aksine) — bu kısım **bizde zaten iyi**.

## 4. Çözüm metodolojisi (öncelik sırasına göre)

1. **Far-field'i aç veya düzelt (en yüksek kaldıraç).**
   (a) Basit ve sağlam: `R_far` ve `wake_len` → **≥100c, tercihen 500c**. C-grid'de dış halka
   hücreleri büyük olduğundan maliyet artışı sınırlı (tanh germe ile birkaç katman).
   (b) İleri: PV + **point-source** far-field BC (küçük domende doğruluk; OpenFOAM `freestream`
   yerine özel BC). Önce (a), GCI'ı asimptota sokar.
2. **Drag'i far-field/iz momentum-açığıyla çıkar** (yüzey-entegrasyona ek). 2. mertebe, TE-bağımsız
   → asimptotik aralığa girmenin en doğrudan yolu. En azından her iki yöntemi raporla.
3. **Mesh ailesini yenile:** geometrik aile (r=√2 veya 2), **en az 4–5 seviye**, en incesi
   ~1000×400+ (≈ TMR finest mertebesi); y⁺<1 (ilk hücre ~1e-6c), LE/TE/iz kümelemesi korunur.
   En **ince 3 seviye** asimptotik aralıkta olacak şekilde seç.
4. **Geçişi kontrol et:** ilk GCI'ı **tam-türbülans SST** ile yap (0.0092'ye karşı; grid-stabil,
   tekrarlanabilir). Geçiş (LM, 0.0064) ayrı bir doğrulama olarak; ikisini karıştırma.
5. **Şemalar:** 2. mertebe `divSchemes` (linearUpwind/linear), tüm seviyelerde tutarlı; residual
   < 1e-6 ve Cd-drift < %0.01.
6. **GCI protokolü (Celik 2008):** asimptotik 3 seviyede p, GCI%, asimptotik-kontrol
   GCI₂₃/(rᵖ·GCI₁₂)≈1. Mertebe drag için ~1.5–2 beklenir.

## 5. Beklenen sonuç ve maliyet

Far-field 500c + far-field-drag + ince aile → Cd'nin **0.0092'ye (tam-türbülans) monoton
yakınsaması** ve geçerli bir GCI bandı beklenir. Maliyet: 4–5 ince 2B mesh × (steady simpleFoam,
2-aşama SST→LM) ≈ saatler (2B olduğu için 3B süpersonikten çok daha ucuz; gece-boyu yeterli).

## 5b. Ampirik kampanya sonucu (2026-06-17) — dürüst kapanış

Far-field hipotezini ampirik doğrulamak için ~3 saat / ~20 deneme yapıldı. **Bir
gerçek kazanım, bir açık blocker:**

**Kazanım — `construct2d_bridge` latent bug'ı düzeltildi (commit'li):** Bridge,
`radi/topo/jmax` parametrelerini **hiç uygulamıyordu** (namelist yanlış dosya adına
yazılıyordu, geçersiz değişkenler içeriyordu, interaktif dizi eksikti). Yani projedeki
TÜM önceki Construct2D çağrıları sessizce default mesh üretmiş. Artık radi=40/200/500
→ far-field 40/200/500c doğru uygulanıyor. Çalışan O-grid→CFD hattı: `experiments/
exp_c2d_run.py` (profesyonel grid + plain freestream + `T.setup`).

**Blocker — mesh kalitesi:** İstenen çözünürlükte (jmax=150) Construct2D O-grid
nonOrtho≈90 üretiyor (elliptic smoothing yakınsamıyor, RMS~0.03) → çözücü diverjyor.
Smoothing/çözünürlük tuning'i her seferinde başka bir duvar açtı. Bespoke C-grid
(`cgrid_elliptic`) ise AR-patlaması/lift-bozulması; OF11 nonuniform-freestream BC
bozuk (PV-BC yolu da kapalı).

**Verdikt:** Airfoil **drag GCI**'ı asimptotik aralığa sokmak, bu donanım+tooling
ile bir araştırma-seviyesi V&V kampanyası (proper grid generator + far-field BC +
ince aile + günler). Teşhis (far-field, literatürle kesin) **deliverable**; ampirik
GCI **gelecek iş**. Lift zaten doğrulanmış (Cl~0.41-0.45, ref 0.44); drag GCI açık.

## 6. Kaynaklar

1. NASA Turbulence Modeling Resource — NACA0012 validation & grid family (turbmodels.larc.nasa.gov).
2. NASA TMR — *Effect of Farfield Boundary* (naca0012_val_ffeffect.html): 30c → ~%8 drag hatası.
3. *Far-field boundary conditions for airfoil simulation…*, Advances in Aerodynamics (Springer, 2025).
4. *Far-field BCs for Airfoil Simulation at High Incidence* (arXiv:2411.13077): drag için point-source.
5. Stanford *In Pursuit of Grid Convergence for 2-D Euler Solutions* — yüzey-entegrasyon drag ~1.5,
   far-field (CFF) 2. mertebe; TE tekilliği etkisi.
6. OpenFOAM resmi NACA0012 doğrulaması — Family II 449×129, Re=6e6, Ladson kıyas.
7. Celik et al. (2008), *Procedure for Estimation and Reporting of Uncertainty Due to Discretization
   in CFD Applications*, J. Fluids Eng. 130(7) — GCI + asimptotik aralık.
