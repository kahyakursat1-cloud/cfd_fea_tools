# Yapısal (FEA) & Topoloji Optimizasyonu — İyileştirme Yol Haritası

**Tarih:** 2026-06-17 · **Kapsam:** CalculiX FEA + SIMP topoloji optimizasyonu (vehicle_fea, vehicle_topopt, fea_runner)
**Yöntem:** Proje durumu + FEA/TO literatür best-practice'leri. CFD yol haritasının ([[iyilestirme_yol_haritasi]]) yapısal karşılığı.

Öncelik: 🔴 yüksek-ROI · 🟡 orta · 🟢 ileri. **Not:** BİLSEM 3D-baskı yaptığından, TO-üretilebilirlik ve gerçek-yük maddeleri CFD'den bile doğrudan değerli.

> **Durum (2026-06-17):** ✅ **1.1 gerilme-tekilliği bekçisi** (`_stress_assessment`,
> kabuk+dolu-katı+TO-final, tekillik-robust SF; verdict muhafazakâr tepe-SF →
> gerçek konsantrasyonda sahte-güvenli vermez). ✅ **4.2 FEA validation suite (3 kanonik vaka)**:
> ankastre kiriş (sehim %1, gerilme %3.9; kuvvet-yolu) + **delikli-plaka Kt≈3.14 (%1.7;
> kuvvet-yolu + tekillik-ayrımı)** + **basınçlı silindir hoop-Lamé (%7.2; BASINÇ-yolu)**.
> Son ikisi ÜRETİM hattını koşturur (gmsh C3D10 node-ordering → write_inp → ccx → frd);
> silindir özellikle **`PressureLoad`→nodal dönüşümünü** doğrular — CFD-basınç→FEA
> kuplajının dayandığı kod. Delik, bekçinin gerçek-konsantrasyonu-tekillikten-ayırmasını
> da kanıtlar (tepe/temsili=1.49×, bayrak YOK). ✅ **1.2 gerilme mesh-GCI** (delik tepe-vM
> yakınsadı, %0.34 yayılım). ✅ **2.1 üretilebilirlik değerlendirmesi** (`manufacturability.py`:
> overhang+yön+min-üye). ✅ **3.1 manevra g-yükü** (`GravityLoad`→*DLOAD GRAV, öz-ağırlık %4.8
> doğrulandı → yük üçlüsü: kuvvet+basınç+gövde). ◐ **4.1** mevcut verdict'le karşılandı.
> Kontrol kazanımı: 2.2 SIMP filtresi + 1.3 C3D10 + 2.3 TO-reanaliz ZATEN var. Kalan: **derin/
> çok-oturumluk** (2.4 gerilme/frekans-kısıtlı TO, 3.2 iteratif FSI, 3.3 yorulma/kompozit) —
> araştırma-düzeyi.

---

## 1. Sonuç DOĞRULUĞU — her SF iddiasını savunulabilir yap (en kritik)

### 1.1 🔴 Gerilme tekilliği (reentrant corner) bekçisi
**Sorun:** Sivri iç köşede gerilme **sonsuza ıraksar** (mesh inceldikçe artar). "Max von
Mises"i körlemesine okumak → tekillik-artefaktı → **yanlış SF / yanlış 'güvensiz' verdicti.**
**Ne:** (a) Tekil bölgeleri tespit et (mesh-refine ile yakınsamayan tepe → bayrakla);
(b) tepe-değer yerine **ortalama-nodal gerilme / gerilme-lineerizasyonu** kullan; (c) sivri
köşe için "fillet ekle" öner. **Neden:** Her yapısal verdictin dürüstlüğü buna bağlı.
**Emek:** Orta. **Bu, yapısal tarafın 'mutlak Cd' dürüstlük-meselesidir.**

### 1.2 ✅ Gerilme mesh-bağımsızlığı (FEA "GCI"si) — `experiments/fea_stress_gci.py`
**Yapıldı:** Delikli-plaka tepe von Mises'i 3 mesh (h=R/{4,6,9}, sabit r=1.5) üzerinde
`compute_gci` ile. Sonuç: tepe 6× düğümde **<%0.34 yayılım**, GCI_ince **%0.32**, Richardson
158.99 MPa (Heywood'dan **%1.3**) → tepe YAKINSADI = **gerçek konsantrasyon, tekillik DEĞİL**
(tekillik ıraksardı). Strict-GCI 'salınımlı' diyor (değer gürültü-tabanında) → `fiziksel_sonuc`
ile dürüstçe ayrıldı; mesh'i 'yeşil GCI' için ayarlamadık (airfoil-GCI dersi). 1.1 ile birlikte
**her SF iddiası artık mesh-bağımsızlığıyla savunulabilir.** Kayıt: `fea_stress_gci.json`.

### 1.3 🟡 Eleman tipi/kalitesi — C3D8R hourglass riski
**Sorun:** Varsayılan **C3D8R** (reduced-integration) hourglass (sıfır-enerji modu) üretir →
nonfiziksel deformasyon/yanlış gerilme. **Ne:** Gerilme-kritik analizde **C3D20R (kuadratik)**
veya C3D10 öner; hourglass-kontrolü; bozuk-eleman (Jacobian/açı) kapısı. **Neden:** Doğru
gerilme. **Emek:** Düşük-orta.

---

## 2. Topoloji optimizasyonu — üretilebilir + güvenli sonuç

### 2.1 ✅ Üretilebilirlik DEĞERLENDİRMESİ (3D-baskı) — `manufacturability.py`
**Yapıldı (değerlendirme+danışman):** TO sonucu STL'i için (a) **overhang alanı** (45° kriteri,
build-plakası hariç), (b) **build-yönü önerisi** (6 eksenden overhang'i en azaltan), (c) **min-üye**
(filtre yarıçapı rmin vs nozzle×2 basılabilir eşik). `run_topopt` çıktısına `uretilebilirlik`
alanı eklendi; verdict ✅/⚠️/❌. Saf-geometri, koşusuz, birim-testli. **Kapsam-dürüstlüğü:**
bu ENFORCE değil DEĞERLENDİRİR (mesh_quality_gate felsefesi) — pratik değerin çoğunu verir
(öğrenci destek/yönelim ihtiyacını görür). **Kalan (derin):** in-loop Langelaar AM-filtresi
(tet-mesh'te kırılgan, ayrı doğrulama ister) — gerçek kısıt-enforce isteyince.

### 2.2 🔴 SIMP filtresi (checkerboard + mesh-bağımlılık)
**Sorun:** Ham SIMP checkerboard + mesh-bağımlı + blurry sınır üretir. **Ne:** **Yoğunluk/
duyarlılık filtresi** (standart çare) + projeksiyon (keskin 0/1 sınır). **Neden:** Fiziksel,
mesh-bağımsız, yorumlanabilir tasarım. **Emek:** Orta. (vehicle_topopt'ta filtre var mı kontrol et; yoksa ekle.)

### 2.3 🔴 TO sonucu DOĞRULAMA döngüsü
**Sorun:** SIMP yoğunluk-alanı bulanık; "optimize edildi" demek güvenli demek DEĞİL. **Ne:**
yoğunluk → eşikle temiz geometri çıkar → yeniden-mesh → **yeniden FEA** → gerçek basılacak
parçada SF'yi doğrula (1.1/1.2 ile). **Neden:** Doğrulanmamış TO = güvensiz. **Emek:** Orta.

### 2.4 ◐ TO objektif/kısıt genişletme — gerilme-temelli TO ✅ (`stress_topopt2d.py`)
**Yapıldı (gerilme-temelli):** Kendi-içinde 2D plane-stress stress-aware TO — P-norm von
Mises agregasyonu, **qp-relaksasyon** (tekillik önleme), **adjoint duyarlılık**. İki katmanlı
doğrulama: (1) **adjoint gradyanı sonlu-farkla ~1e-7 uyumlu** (gerilme-TO'nun en kritik
doğrulaması; `test_stress_topopt2d`), (2) **L-bracket benchmark**: gerilme-min tepe von
Mises'i kompliyans-min'e göre **%7.3 düşürdü** (reentrant köşe yuvarlandı — literatür sonucu;
`stress_topopt_lbracket.json`). ccx/CFD YOK → hızlı, kendi-içinde, eğitsel. **Kapsam:** demonstratör/
çekirdek (mevcut ccx-tabanlı `vehicle_topopt`'a adjoint-stress bağlamak ayrı iş — ccx kara-kutu
adjoint zor). **Kalan:** frekans-kısıtlı TO (modal var → kısıt bağla), termal+yapısal çok-fizik.

---

## 3. Yükler & kapsam — gerçekçi yapısal senaryo

### 3.1 🟡 Aero-ötesi yükler — kısmen ✅ (manevra g-yükü)
**Yapıldı:** **Eylemsizlik gövde-kuvveti** (`GravityLoad` → CalculiX `*DLOAD GRAV`, calculix_writer);
`run_structural_check(g_yuk=n)` ile CFD basıncına ek **n·g manevra yükü** (FlightEnvelope.n_max
besler). Doğrulandı: öz-ağırlık çubuk σ=ρgL %4.8, δ %0.2 (`fea_validation_grav.py`). Yük-uygulama
üçlüsü tamam: kuvvet (kiriş/delik) + basınç (silindir) + **gövde (g-yükü)**. **Kalan:** nokta-yük
(thrust-mount/montaj — `ForceLoad` zaten var, sadece UI-bağlama), termal (*DLOAD/*TEMPERATURE), iniş.
**Sorun (kalan):** çoklu-yük zarfı polar'da var → g-yük durumlarını da zarfa kat.
**Emek:** Orta.

### 3.2 🟡 FSI olgunlaştırma (esnek yapı)
**Ne:** CFD-basınç→FEA tek-yön var; **iteratif FSI** (deformasyon→yeniden-CFD) esnek
kanat/kabukta. Yük-haritalama doğruluğu (konservatif interpolasyon). **Emek:** Yüksek.

### 3.3 🟢 Yorulma (fatigue) + kompozit
**Ne:** Çevrimsel yük → S-N/yorulma ömrü; uçak kabuğu için laminat/kompozit. **Neden:** Aero
yapıları çevrimsel yük + kompozit görür. **Emek:** Yüksek.

---

## 4. FEA otopilotu (CFD otopilotunun yapısal karşılığı)

### 4.1 ◐ FEA auto-config + hakem-kapısı — büyük ölçüde KARŞILANDI
**Mevcut hakem-kapısı:** Yapısal sonuç güveni zaten şartlandırılıyor — `_mechanism_check`
(mesnetsiz mekanizma → `gecersiz`), `_stress_assessment` (tekillik şüphesi → muhafazakâr
tepe-SF + uyarı), 1.2 gerilme-GCI (yakınsama). CFD `referee_gate`'in yapısal eşi: kötü
sonuç güvenilmez işaretlenir. **Fark (CFD'den):** FEA'da öğrenme-döngüsü YOK → "çapa
kaydetme" kavramı uygulanmaz; bu yüzden ayrı bir gate-modülü gereksiz (sadelik). **Kalan
(düşük öncelik):** geometri+rejimden tam auto-config (malzeme/yük/eleman otomatik seçimi) —
şu an kullanıcı `run_structural_check` parametreleriyle seçiyor (öner-onayla yeterli).

### 4.2 🟡 FEA validation suite (commit'li)
**Ne:** Kapalı-form referanslı vakalar: ankastre kiriş (sehim/gerilme), delikli-plaka (Kt
gerilme-konsantrasyonu), basınçlı silindir (hoop). Toleranslı CI kontrolü. **Neden:** CalculiX
kurulumu + eleman davranışı doğrulanır (CFD küre/NACA0012 suite'inin eşi). **Emek:** Orta.

---

## 5. Önerilen sıra (yapısal sprint)

1. **1.1 tekillik bekçisi + 1.2 gerilme mesh-bağımsızlığı** → her SF iddiası **doğru ve savunulabilir** (yapısal dürüstlük çekirdeği).
2. **2.2 SIMP filtresi + 2.1 üretilebilirlik + 2.3 doğrulama döngüsü** → **basılabilir + güvenli** optimize parça (BİLSEM atölye-değeri).
3. **4.2 FEA validation suite** → CalculiX kurulumu ölçülebilir-doğru.

CFD'de "boşa koşuyu önle" neyse, yapısalda **"yanlış SF verme + basılamayan parça üretme"** odur. Bu sıra yapısal tarafı CFD ile aynı olgunluğa taşır.

## Kaynaklar
- *TO for additive manufacturing: length-scale, overhang, build-orientation* (arXiv:2204.07333).
- *TO considering overhang constraint* (Comput. & Struct. 2018).
- *Stress singularities at reentrant corners — fundamental FEA problem* (Fidelis FEA).
- C3D8R hourglass davranışı (Abaqus/CalculiX eleman dökümantasyonu).
- FEA mesh-convergence & singularity (mesh convergence guides).
