# Süpersonik Sürükleme (Cd) — İnce Cisimde Mutlak Cd: Kök-Neden ve Tractable Çözüm Yolları

**Tarih:** 2026-06-22 · **Vaka:** ince/slender roket (fineness≈10, R/L≈0.05), M=1.5–3 ·
**Önceki hüküm:** [[supersonik-mutlak-cd-intractable]] — 3D explicit shockFluid ile pratik değil

## 1. Problem ve kök-neden (doğrulanmış)

İnce cismin **mutlak** Cd'si 3D `shockFluid` (explicit, OF11 density-based) ile bu donanımda
(RTX 4060 + WSL, 9 GB) intractable. Kök-neden iki katmanlı:

1. **Mesh çapı bağlar, çözünürlük yetmez.** `bg_cell_size = L/div` mesh'i BOYA bağlar; ince
   cismin ilgili ölçeği ÇAP. Hızlı modda yüzey hücresi ~0.039 m, yarıçap ~0.04 m → **çapta
   ~2 hücre → staircase → sahte dalga-sürüklemesi.** clean_rocket M2 → Cd≈1.62 (küre 1.13'ten
   yüksek; doğru sivri-burun roket Cd≈0.066). Bu, model değil **mesh artefaktı**.
2. **Çap-çözümü ⊗ explicit zaman-adımı.** Çapı çözmek için küçük hücre → küçük Δt (CFL) →
   explicit shockFluid **2h+ timeout** (yakınsamadan). Doğru kaldıraç (çap-bilinçli refinement)
   yanlış çözücüde maliyeti patlatıyor.

**Özet:** intractable olan **"3D + explicit + boy-bağlı mesh"** kombinasyonu. Her üçü de
değiştirilebilir; literatür üç tractable yol veriyor.

## 2. Çözüm yolları (öncelik sırasına göre)

### 2.1 ⭐ Eksenel-simetrik (wedge) indirgeme — kök-nedenin doğrudan çözümü
Roket α=0'da (ve küçük α'da) **dönel-simetrik**. 3D milyon-hücre problemi, 1-hücre kalınlığında
**5° wedge** mesh'e indirgenir: profil (r vs x) tek wedge açısıyla döndürülür, eksende `wedge`
BC çifti + `empty`/axis. Sonuç: **çap tam çözülür AMA toplam hücre ~birkaç bin** (3D'de ~10⁶).

- Çapı boydan ayırır → staircase kök-nedeni biter (artık çapta 50+ hücre ücretsiz).
- Hücre azlığı sayesinde **explicit rhoCentralFoam bile hızlı** (3D maliyet-katili ortadan kalkar);
  implicit gerekmez. İstenirse HiSA/LTS daha da hızlandırır (§2.2).
- Kapsam: tüm gövde + burun + boattail dalga+sürtünme drag'i; taban-drag ayrı eklenir (ampirik).
- Araç: `wedgePlease` benzeri 2D→wedge dönüştürücü veya blockMesh wedge bloğu.
- **Doğrulama hedefi:** dönel ogive/koni-silindir süpersonik Cd literatürde bol (kıyas kolay).

### 2.2 İmplicit density-based çözücü (HiSA) — explicit timeout'un doğrudan çözümü
3D gerekiyorsa (R/L>0.05, kanatçık, açılı uçuş): **HiSA** (OpenFOAM tabanlı, coupled density-based,
AUSM+up, dual/pseudo-time + LTS). Literatür: **steady implicit ~15k iter / ~30 dk, explicit'ten
~5× hızlı**; M≈0.3–5 dış aerodinamik için tasarlanmış. Explicit CFL bariyerini kaldırır.
Kısıt: ayrı derleme (OF eklentisi); kurulu değilse §2.1 veya §2.3 tercih.

### 2.3 Slender-body / linearize süpersonik dalga-drag teorisi (analitik, ~anında)
**Kritik rejim bulgusu:** R/L ≤ 0.05 ve M=1.1–2.0'da düşük-fidelity yöntemler Euler CFD'yi
**~1 drag-count içinde** tutturur; R/L≈0.1'e yaklaşınca >30 drag-count'a sapar [1]. **Bizim
roket fineness≈10 → R/L≈0.05 → tam "analitik doğru" rejiminde.** Yani ince roket için pahalı
CFD GEREKMEZ. Toplam Cd üç ayrı bileşen (missile-DATCOM/aeroprediction yaklaşımı):

- **Dalga-drag (wave):** süpersonik alan-kuralı / Von Kármán ogive / Sears-Haack;
  `C_Dw = −1/(2π)∬ S''(x)S''(ξ) ln|x−ξ| dx dξ` (S(x)=kesit alanı dağılımı). Ogive burun için
  kapalı-form yaklaşımlar mevcut.
- **Sürtünme-drag (skin friction):** sıkıştırılabilir düz-levha (Van Driest II) × ıslak alan.
- **Taban-drag (base):** ampirik (M ve taban-alanı fonksiyonu; Hoerner/MIL-HDBK korelasyonları).

Hız: milisaniye. Doğruluk: belirtilen rejimde drag-count düzeyinde. Sınır: keskin geometri
detayı/ayrılma yok (slender varsayımı bozulursa §2.1/§2.2'ye geç).

## 3. Bu proje için öneri (BİLSEM eğitim + grant + mütevazı donanım)

| Cisim | Rejim | Yöntem | Maliyet | Çıktı sınıfı |
|-------|-------|--------|---------|--------------|
| İnce roket (R/L≤0.05) | M1.1–3 | §2.3 slender-body analitik | ~ms | mutlak, drag-count |
| Genel/küt cisim, α≠0 | M0.3–5 | §2.1 wedge CFD (rhoCentralFoam) | dakikalar | mutlak, mesh-çözülü |
| 3D detay (kanatçık/etkileşim) | süpersonik | §2.2 HiSA implicit | ~30 dk | tasarım-grade |

**Aşamalı plan:**
1. ✅ **§2.3 analitik dalga-drag modülü — YAPILDI (2026-06-22, `supersonic_slender.py`).**
   von Kármán Fourier alan-kuralı `D=(πq/4)Σn Aₙ²`, **Sears-Haack kapalı-formuna karşı %0.00
   doğrulandı**; roket M2 Cd_total=0.485 (wave=0.072 ≈ inviscid CFD 0.066, fric=0.163, base=0.250).
   5 birim test (`tests/test_supersonic_slender.py`). Açık: `validity_envelope`'a slender-body
   bandı bağlamak + otopilot hızlı-yol entegrasyonu (şu an standalone). Taban-drag en zayıf bileşen.
2. **§2.1 wedge CFD pipeline** (orta iş): non-slender / genel dönel cisim için. Mevcut
   `supersonic_cfd.py` 3D yolunun yanına eksenel-simetrik kısa-devre.
3. **§2.2 HiSA** (opsiyonel, kurulum gerekirse): 3D açılı/etkileşimli vakalar.

## 4. Önceki "intractable" hükmünün güncellenmesi

`supersonik-mutlak-cd-intractable` hükmü **dar bağlamda doğru kalır** (3D + explicit + boy-bağlı
mesh). Ancak **mutlak Cd genel olarak intractable DEĞİL**: eksenel-simetri indirgemesi ve
slender-body teorisi ince roket mutlak Cd'sini bu donanımda tractable kılar. Kök-neden 3D
maliyeti olduğundan, problemi 2D'ye/analitiğe indirmek doğru kaldıraçtır.

## 5. Kaynaklar

1. *Multifidelity Comparison of Supersonic Wave Drag Prediction Methods Using Axisymmetric
   Bodies*, Aerospace (MDPI) 11(5):359, 2024 — R/L≤0.05 & M1.1–2 düşük-fidelity ~1 drag-count;
   R/L≈0.1 → >30 drag-count. Eksenel-simetrik grid-yakınsama.
2. HiSA — High-speed Aerodynamic solver (OpenFOAM, coupled density-based, AUSM+up, dual-time/LTS);
   steady implicit ~15k iter/~30dk, explicit'ten ~5× hızlı; M≈0.3–5 dış aerodinamik
   (wiki.chpc.ac.za/howto:openfoam:hisa; PARCFD2020 HiSA drag-prediction validation).
3. `wedgePlease` — 2D mesh → eksenel-simetrik wedge dönüştürücü (github.com/krebeljk/wedgePlease).
4. rhoCentralFoam — density-based shock-capturing (central-upwind), süpersonik dış aero
   (Kurganov-Tadmor); küçük wedge mesh'te explicit yeterli.
5. Hoerner, *Fluid-Dynamic Drag* — taban-drag ve sürtünme korelasyonları (süpersonik bileşenler).
