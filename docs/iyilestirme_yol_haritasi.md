# Uygulama & Analiz İyileştirme Yol Haritası

**Tarih:** 2026-06-17 · **Kapsam:** Otopilot CFD/FEA araç-analiz uygulaması
**Yöntem:** Bu oturumun somut dersleri + otomatik-CFD literatür best-practice'leri (NASA TMR, ASME V&V 20, Ansys Fluent Aero, OpenFOAMGPT, DrivAerML).

Öncelik: 🔴 yüksek-ROI/düşük-emek · 🟡 orta · 🟢 ileri/düşük-öncelik.
Her madde: **ne / neden / emek**.

> **Durum (2026-06-17):** ✅ **1.1 mesh-kalite ön-geçidi** (`mesh_quality_gate`,
> süpersonik+ses-altı yola bağlı), ✅ **1.4 süre/maliyet bandı** (`_runtime_band`)
> tamamlandı. Kalan maddeler ya **çözücü-koşusu** ister (2.1 validation suite,
> 2.2 GCI — makine dinleniyor) ya da **derin özellik** (2.3/2.4 far-field, mesh-adapt).

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

### 1.2 🔴 Erken-abort + yakınsama bazlı durdurma
**Ne:** Solver loglarını canlı izle; NaN/negatif-T/diverjans görülürse **anında durdur**
(7200s timeout'u bekleme). Yakınsamayı residual<1e-4 + Cd-drift<%0.5 ile tespit edip
erken bitir (sabit iterasyona kadar koşma). **Neden:** rocket_tvc 2 saat NaN'a koştu;
clean_rocket gereğinden çok iterasyon. **Emek:** Düşük. (`_cd_converged` çekirdeği var.)

### 1.3 ✅ Süreç-yaşamdöngüsü sağlamlığı — `_wrap_timeout` + `_wsl_kill`
**Yapıldı:** Uzun OF adımları (foamRun/snappy/mpirun…) **WSL-içi GNU `timeout -k 10 -s TERM`**
ile sarılır → süre aşımında WSL kendi süreç ağacını öldürür (Windows-tarafı wsl.exe öldürmek
WSL-içi ağacı bırakıyordu → orphan, 50× yavaşlama). Ayrıca Windows-tarafı `TimeoutExpired`'da
`_wsl_kill` ilgili binary'leri `pkill -9 -f` ile temizler (kemer+askı). Birim-testli
(`test_openfoam_runner`). **Not:** süpersonik yol (`supersonic_cfd`) benzer korumayı ister
(ayrı kontrol).

### 1.4 🟡 Maliyet/süre tahmini + ön-uyarı
**Ne:** Mesh boyutu + rejim + çözücüden tahmini wall-time hesapla; "bu koşu ~X saat,
gece-boyu/HPC öner" de (süpersonik için kısmen var → genelleştir). **Neden:** Öner-onayla
felsefesiyle uyumlu; kullanıcı pahalı koşuyu bilerek başlatır. **Emek:** Düşük.

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

### 2.4 🟢 Drag-çıkarımı: far-field/iz momentum-açığı (yüzey-entegrasyona ek)
**Ne:** Yüzey-entegrasyon drag'i ~1.5 mertebe + TE-duyarlı; far-field/iz yöntemi 2.
mertebe. İkisini de raporla. **Neden:** GCI'a asimptotik girmenin doğrudan yolu. **Emek:** Orta.

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
