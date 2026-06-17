# Yapısal (FEA) & Topoloji Optimizasyonu — İyileştirme Yol Haritası

**Tarih:** 2026-06-17 · **Kapsam:** CalculiX FEA + SIMP topoloji optimizasyonu (vehicle_fea, vehicle_topopt, fea_runner)
**Yöntem:** Proje durumu + FEA/TO literatür best-practice'leri. CFD yol haritasının ([[iyilestirme_yol_haritasi]]) yapısal karşılığı.

Öncelik: 🔴 yüksek-ROI · 🟡 orta · 🟢 ileri. **Not:** BİLSEM 3D-baskı yaptığından, TO-üretilebilirlik ve gerçek-yük maddeleri CFD'den bile doğrudan değerli.

> **Durum (2026-06-17):** ✅ **1.1 gerilme-tekilliği bekçisi** (`_stress_assessment`,
> kabuk+dolu-katı+TO-final, tekillik-robust SF; verdict muhafazakâr tepe-SF →
> gerçek konsantrasyonda sahte-güvenli vermez). ✅ **4.2 FEA validation suite**:
> ankastre kiriş (sehim %1, gerilme %3.9) + **delikli-plaka Kt≈3.14 (gerilme %1.7)**
> — ikincisi ÜRETİM hattını (gmsh C3D10 node-ordering → write_inp → ccx → frd) ve
> bekçinin gerçek-konsantrasyonu-tekillikten-ayırmasını (tepe/temsili=1.49×, bayrak
> YOK) doğrular. Kontrol kazanımı: **2.2 SIMP filtresi zaten var** (`_sens_filter`),
> **1.3 eleman C3D10** (hourglass yok → moot), **2.3 TO yeniden-analizi zaten var**.
> Kalan: ya **çözücü-koşusu** (1.2 gerilme mesh-yakınsama) ya da **derin özellik**
> (2.1 overhang/üretilebilirlik kısıtı, FSI).

---

## 1. Sonuç DOĞRULUĞU — her SF iddiasını savunulabilir yap (en kritik)

### 1.1 🔴 Gerilme tekilliği (reentrant corner) bekçisi
**Sorun:** Sivri iç köşede gerilme **sonsuza ıraksar** (mesh inceldikçe artar). "Max von
Mises"i körlemesine okumak → tekillik-artefaktı → **yanlış SF / yanlış 'güvensiz' verdicti.**
**Ne:** (a) Tekil bölgeleri tespit et (mesh-refine ile yakınsamayan tepe → bayrakla);
(b) tepe-değer yerine **ortalama-nodal gerilme / gerilme-lineerizasyonu** kullan; (c) sivri
köşe için "fillet ekle" öner. **Neden:** Her yapısal verdictin dürüstlüğü buna bağlı.
**Emek:** Orta. **Bu, yapısal tarafın 'mutlak Cd' dürüstlük-meselesidir.**

### 1.2 🔴 Gerilme mesh-bağımsızlığı (FEA "GCI"si)
**Ne:** CFD-GCI'nin yapısal karşılığı — gerilme en mesh-duyarlı niceliktir (integrasyon
noktalarında doğru, konsantrasyonda küçük eleman ister). ≥3 mesh seviyesinde max-gerilme
yakınsamasını raporla; yakınsamayan tekillik (1.1) ile ayır. **Neden:** SF ancak mesh-bağımsızsa
savunulabilir. **Emek:** Orta. (`compute_gci` çekirdeği gerilmeye de uygulanabilir.)

### 1.3 🟡 Eleman tipi/kalitesi — C3D8R hourglass riski
**Sorun:** Varsayılan **C3D8R** (reduced-integration) hourglass (sıfır-enerji modu) üretir →
nonfiziksel deformasyon/yanlış gerilme. **Ne:** Gerilme-kritik analizde **C3D20R (kuadratik)**
veya C3D10 öner; hourglass-kontrolü; bozuk-eleman (Jacobian/açı) kapısı. **Neden:** Doğru
gerilme. **Emek:** Düşük-orta.

---

## 2. Topoloji optimizasyonu — üretilebilir + güvenli sonuç

### 2.1 🔴 Üretilebilirlik kısıtları (3D-baskı) — BİLSEM için doğrudan değer
**Sorun:** Optimize parça basılamıyorsa işe yaramaz. **Ne:** TO formülasyonuna (a)
**overhang açısı** kısıtı (destek-yapısız basılabilirlik), (b) **min üye boyutu** (ince-duvar
basılamaz), (c) **build-orientation** + simetri. **Neden:** Atölyede gerçekten basılabilen
optimize parça. **Emek:** Orta-yüksek. **Kullanım-değeri en yüksek madde.**

### 2.2 🔴 SIMP filtresi (checkerboard + mesh-bağımlılık)
**Sorun:** Ham SIMP checkerboard + mesh-bağımlı + blurry sınır üretir. **Ne:** **Yoğunluk/
duyarlılık filtresi** (standart çare) + projeksiyon (keskin 0/1 sınır). **Neden:** Fiziksel,
mesh-bağımsız, yorumlanabilir tasarım. **Emek:** Orta. (vehicle_topopt'ta filtre var mı kontrol et; yoksa ekle.)

### 2.3 🔴 TO sonucu DOĞRULAMA döngüsü
**Sorun:** SIMP yoğunluk-alanı bulanık; "optimize edildi" demek güvenli demek DEĞİL. **Ne:**
yoğunluk → eşikle temiz geometri çıkar → yeniden-mesh → **yeniden FEA** → gerçek basılacak
parçada SF'yi doğrula (1.1/1.2 ile). **Neden:** Doğrulanmamış TO = güvensiz. **Emek:** Orta.

### 2.4 🟡 TO objektif/kısıt genişletme
**Ne:** Frekans-kısıtlı TO (flutter/rezonans kaçınma — modal zaten var), termal+yapısal
çok-fizik, gerilme-kısıtlı TO (sadece compliance değil). **Neden:** Gerçek tasarım hedefleri.
**Emek:** Yüksek.

---

## 3. Yükler & kapsam — gerçekçi yapısal senaryo

### 3.1 🟡 Aero-ötesi yükler
**Sorun:** Şu an yük ~CFD basıncı. Gerçek yapı: **manevra g-yükü, kalkış/iniş, nokta-yük
(montaj), termal, atalet**. **Ne:** Yük-durumu kütüphanesi (g-load, landing, thrust-mount) +
çoklu-yük zarfı (polar çoklu-yük var → genişlet). **Neden:** Aero-basınç tek başına yetersiz.
**Emek:** Orta.

### 3.2 🟡 FSI olgunlaştırma (esnek yapı)
**Ne:** CFD-basınç→FEA tek-yön var; **iteratif FSI** (deformasyon→yeniden-CFD) esnek
kanat/kabukta. Yük-haritalama doğruluğu (konservatif interpolasyon). **Emek:** Yüksek.

### 3.3 🟢 Yorulma (fatigue) + kompozit
**Ne:** Çevrimsel yük → S-N/yorulma ömrü; uçak kabuğu için laminat/kompozit. **Neden:** Aero
yapıları çevrimsel yük + kompozit görür. **Emek:** Yüksek.

---

## 4. FEA otopilotu (CFD otopilotunun yapısal karşılığı)

### 4.1 🟡 FEA auto-config + hakem-kapısı
**Ne:** Geometri+rejimden otomatik: malzeme (materials.json), yük-durumu, eleman tipi/mesh,
SF/burkulma verdicti. **FEA referee gate:** gerilme yakınsadı mı / tekillik-artefaktı mı →
sonucu şartlandır (CFD `referee_gate`'in eşi). **Neden:** Tek-tık güvenilir yapısal analiz +
"kötü sonuç öğrenilmez" tutarlılığı. **Emek:** Orta. (CFD otopilot mimarisi yeniden-kullanılır.)

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
