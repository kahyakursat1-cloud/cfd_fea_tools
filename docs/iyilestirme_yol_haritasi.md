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

### 1.1 ✅ Mesh-kalite ÖN-GEÇİDİ — `openfoam_runner.mesh_quality_gate`
**Doğrulandı (2026-08-19, kod okundu):** `analysis/openfoam_runner.py:1505` `log.checkMesh`'i okur; `verdict == "reject"` ise çözücüye GÖNDERMEDEN düşer ("Mesh kalitesiz, çözücüye GÖNDERİLMEDİ"). Bölüm başlığı 🔴 kalmıştı ama sayfanın kendi durum bloğu zaten ✅ diyordu — belge kendi içinde çelişiyordu.
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

### 1.2-not ✅ Parallel CFD (mpirun) — ONARILDI (`HWLOC_COMPONENTS=-gl`)
**Kök neden (strace):** `mpirun -np 1` bile `connect(127.0.0.1:6001)`'de asılıyordu — hwloc'un
**GL bileşeni** GPU-topolojisi için X-sunucusuna (DISPLAY=:0 WSLg) bağlanıp süresiz donuyordu.
**Çözüm:** `OF_ENV_PREFIX`'e `export HWLOC_COMPONENTS=-gl` (reinstall GEREKMEDİ). + `_default_processors`
→ fiziksel çekirdek (4; WSL 8-mantıksal/4-fiziksel, OpenMPI fiziksel'i slot sayar) + `--oversubscribe`
+ erken-durdurma parallel'e genellendi. **Doğrulandı:** 4-çekirdek paralel + 129-iter erken-stop,
Cd özdeş. Solver-ağır seviyelerde (standart/hassas) ~3-4× hız.

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

### 2.1 ◐ Doğrulama regresyon suite'i — BÜYÜK ÖLÇÜDE VAR, çapa üretimi eksik
**Yapılan (2026-08-19):** `experiments/dis_korpus.py` referanslı kanonik vakaları ölçülmüş toleranslarla taşıyor ve test paketinde koşuyor; `fea_capa_bagimsiz.py` üç kapalı-form çapası üretiyor (3 ağ seviyesi, u_num ölçülü).
**ÖLÇÜLDÜ (2026-08-19): çapa üretimi YENİDEN KOŞULABİLİR.** `validation_anchors_runs` 2026-08-13'te silinmişti ve değerler arşivden kurtarılmıştı; bu, üretim yolunun kırık olduğu ANLAMINA GELMİYORMUŞ. İki çapa yeniden koşuldu ve İKİ FARKLI SONUÇ verdi: `disk` arşivle birebir üretildi (%3,38 → %3,38), ama `kup` arşivden ÇOK farklı çıktı (hata %6,03 → %0,38, band %58,3 → %2,67) — çünkü arşiv değeri bir yapılandırma düzeltmesinden (hücre tavanı 2,5M→4M) ÖNCEYE aitti ve çapa o düzeltmeden sonra hiç koşulmamıştı. **Tek çapadan 'arşiv güvenilir' genellemesi yanlıştır.**

**ÖNCÜL BAYATMIŞ — ÖLÇÜLDÜ (2026-08-20):** "küp, Ahmed, NACA0012 AR6 hâlâ arşivden" artık
DOĞRU DEĞİL. Beş çapanın da taze koşu çıktısı var (`validation_anchors_runs/_anchor_*/sonuc.json`,
19–20 Ağustos): disk, küre, küp ve Ahmed Cd üretti; arşiv etiketli tek girdi (`küp (arşiv)`)
zaten bayat diye REDDEDİLİYOR. Kanıttaki 12 çapanın hepsi taze koşudan ya da literatürden.

**KALAN — tek çapa: 3B AR6, ve nedeni ÖLÇÜLDÜ.** Koşu `snappyHexMesh` aşamasında **dönüş
kodu 137 (SIGKILL = OOM)** ile 1319 s sonra öldü; log kuyruğu `displacementMedialAxis`,
yani prizma-katman adımı. Bu tam olarak `bellek_kapisi`'nin "ÇÖZÜM aşaması kapsanır,
snappyHexMesh KATMAN adımının tepe belleği ÖLÇÜLMEDİ" diye kapsam dışı bıraktığı yer —
kapının beyanı doğruymuş ve bu, o boşluğun ölçülmüş ilk örneği.

**BOŞLUK KAPANDI (2026-08-20)** — `experiments/snappy_katman_tepe_bellegi.py`. Ahmed
gövdesi, `n_layers=3`, dört kademe, snappyHexMesh `/usr/bin/time -v` altında, tepe RSS:

| hücre | tepe RSS | kB/hücre |
|---|---|---|
| 54.748 | 0,143 GB | 2,61 |
| 142.362 | 0,291 GB | 2,04 |
| 272.756 | 0,509 GB | 1,87 |
| 567.549 | 0,993 GB | 1,75 |

**tepe = 1,656 kB/hücre + 0,055 GB, R² = 0,99996** — çözüm katsayısının (0,779) **2,13
katı**, yani ~0,25M hücreden sonra bağlayıcı aşama meshlemedir. Katman örgüsü teyitli
(log tablosu: gövde yaması 202 yüz, 3/3 katman, %100 kalınlık) — katmansız bir yolu
katmanlı sanıp ölçme riski kapatıldı.

**Geri-tahmin doğrulaması:** katsayı 55k–568k aralığında oturtuldu ve 10× ötelenerek
AR6'nın 6M hücresi için 9,99 GB öngörüyor; o an boş olan 7,9 GB'ın üstünde, yani OOM.
Gözlenen tam buydu. Kapı artık o vakayı REDDEDİYOR (12,99 GB gerekir) ve hükmünde
bağlayıcı aşamayı adıyla yazıyor. Önerilen hücre tavanı da bağlayıcı aşamadan türetiliyor
— çözümden türetmek yine aşılabilir bir tavan önerirdi. Kök neden bellek değil
GEOMETRİ (firar kenarı kirişin %0,24'ü, açıklık 18 m → ~97M hücre); donanım yükseltmesi
işi imkânsızdan makul-ihtimale taşır. `sphere` ve `naca0012_a0` atlama listesinde
(setup-uyumsuz). Ayrıca 2026-08-20'de düzeltildi: toplayıcı düşen koşuyu SESSİZCE
atıyordu (`cd is None → continue`), artık gerekçesi ve log yoluyla kanıta giriyor.
**Ne:** Referans-değerli kanonik vakalar: süpersonik küre Cd (Charters&Thomas, var),
NACA0012 ses-altı (Ladson), bilinen roket; her birine **referans + tolerans** + CI'da
çalışan hafif kontrol. **Neden:** "en iyi analiz" ancak ölçülünce iddia edilir; regresyon
yakalar; yayın-kredibilitesi. **Emek:** Orta. (supersonic_validation.json çekirdek; sistematikleştir.)

### 2.2 ✅ Mesh-bağımsızlık (GCI) otomasyonu — ÖNCÜL BAYATMIŞ, otomasyon çalışıyor
**Ölçüldü (2026-08-19, beş çapa koşusu):** ağ üretimi ÇALIŞIYOR — küp 4 seviye + GCI,
disk 3 seviye + GCI. Madde "eksik olan 3 seviyeyi güvenilir üreten mesh" diyordu; ağlar
üretiliyor. Kalan üç çapada (ahmed, küre, AR6) sorun MESHLEME DEĞİL YAKINSAMA:
"ince seviye YAKINSAMADI — rezidüeller platoya oturdu (limit çevrimi)".
**Ve bu ret KASITLI ve DOĞRU:** bant, raporlanan Cd'nin belirsizliğini anlatır; raporlanan
değer ince seviyeden gelir. İnce seviye yakınsamadıysa kaba seviyelerden çıkan bant onu
TARİF ETMEZ — kod bunu açıkça söyleyip aileyi reddediyor ("referans seviye kapıdan
geçmeden aile anlamsızdır"). 2-seviye vekil-bant ve ≥3-seviye GCI dalları zaten var.
**Kalan gerçek iş otomasyon değil FİZİK:** küre ve Ahmed zaman-bağımlı (bu oturumda
ölçüldü); kararlı RANS'ın yakınsayacağı çözüm yok. Çözüm URANS/DES, GCI otomasyonu değil.

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

### 2.5 ✅ Prizma katman + y⁺ otomasyonu — `duzeltici.duvar_islemini_aga_uydur`
**Doğrulandı (2026-08-19):** düzeltici y⁺/duvar-işlemi uyumsuzluğunu tespit edip kurulumu onarır ve ölçülmüş sonuçları kayıtlı (silindir DES y⁺ 0,009→0,78; NACA0012 α=8° 357→2,5). Aynı gün çapa üretimine de üretim-anı y⁺ kapısı eklendi (`validate_pipeline` → `duvar_hukmu`); band ölçütü `validity_envelope.yplus_duvar_sinifi`'nda TEK KAYNAK.
**Ne:** y⁺-hedefli ilk-hücre + katman sayısı zaten var; **gerçekleşen y⁺'ı ölç, hedef
dışıysa otomatik düzelt** (duvar-fonk vs low-Re seçimi). **Neden:** Sürtünme-drag doğruluğu
y⁺<1 ya da doğru duvar-fonk ister. **Emek:** Orta.

---

## 3. Otopilot zekâsı / öz-öğrenme

### 3.1 ✅ Sınıflandırma: bbox-tavanı aşıldı — `auto_pilot`
**Doğrulandı (2026-08-19):** `ince_yassilik` ve `radyal_doluluk` bbox-üstü sinyalleri hesaplanıyor VE kullanılıyor (`auto_pilot.py:72-73, 244`).
**Ne:** Gerçek avcı↔lifting-body bbox'ta ayrılmıyor (genelleme 4/7). bbox-üstü hafif
betimleyici (eğrilik histogramı / küçük PointNet) **yalnız belirsiz çiftlerde**. **Neden:**
Gerçek-dünya isabeti. **Emek:** Yüksek (ayrı yöntem). **Alternatif (ucuz):** öner-onayla +
MEMORY zaten kuyruğu kapatıyor — belki yeterli.

### 3.2 ✅ Cd-aykırılık öğrenmesi — BESLENDİ, sonra İSTATİSTİĞİ düzeltildi
**Veri tamam (ölçüldü 2026-08-19):** sekiz tipin hepsinde 12–20 vaka (eşik 5) ve kapı
üretim yolundan çağrılıyor (`auto_pilot:105`, `:543`). "Koşu biriktir" işi bitmişti.
**Asıl kusur istatistikteydi:** ortalama+sd ile kurulan aykırı-dedektörü, aykırıların
sd'yi şişirip KENDİLERİNİ gizlemesine izin veriyordu. `ucak` (n=14): 12 vaka
0,0039–0,0211 + 2 vaka 0,337/0,400 → eşik 0,377, yani 17 katı olan değer BAYRAKLANMIYOR.
**Düzeltildi:** medyan+MAD (sağlam) → eşik 0,0221, ikisi de yakalanıyor.
**İkinci kusur:** `record_case` `aref_mode` yazmıyordu; kapı planform↔frontal Cd'leri
aynı havuzda topluyordu (tilt_rotor'da 14–37 kat iki-kümelilik). Artık kaydediliyor.
**Teşhis ayrımı:** komşusuz aykırı → "geometri/ayar"; kümesi olan → "farklı referans
alanı, A_ref sözleşmesini doğrula".

### 3.3 ✅ Yönelim-kanoniklestirmeyi genişlet (2026-08-20)
**Ne:** `canonicalize_axial` yalnız eksenel cismi düzeltiyor; kanat/genel için de
güvenli kanoniklestirme (PCA + sınıf-bilinçli). **Neden:** Rastgele yönelimli CAD.

**ÖLÇÜLDÜ — öncül eksikti: fonksiyon yalnız genişlemeye değil DÜZELTMEYE muhtaçtı.**
Şekil testi `bbox` ekstentleriyle kuruluydu; bbox dönme-değişmez değil. Kanadın
`e_mid/e_thin` oranı yönelimle 8,33 → 1,01 saçılıyor, yani **eğik duran kanat
"eksenel" sanılıp açıklığı akışa çevriliyordu** (aktif bozma), eğik roket ise
(1,92 / 2,38) hiç hizalanmıyordu. Ölçülen sınıflandırma etkisi (NACA0012 AR6,
c=0,15 m):

| yönelim | ön alan | sınıf |
|---|---|---|
| kanonik | 0,0162 m² | uçak ✓ |
| 90° y | 0,1350 (8,3× fazla) | tilt_rotor ✗ |
| 90° z | 0,0018 (9× az) | kanatlı_roket ✗ |
| rastgele | 0,0316 | kanatlı_roket ✗ |

**Yapıldı:** şekil testi yüzey-alanı ağırlıklı asal (PCA) çerçeveye taşındı — o
çerçevede oran roket 1,00 / kanat 8,31 / Ahmed 1,29 olarak SABİT. Yassı cisim
dalı eklendi (kalınlık→z, kiriş→x, açıklık→y). Rastgele yönelimden geri kazanım:
roket ve kanat %0,01, Ahmed %1,35 (eğik art gövde asal ekseni yatırıyor).

**Beyan edilen sınırlar:** (i) ± yön ÖLÇÜLMEZ, girdiden devralınır — merkez-kayması
ölçütü denendi (koni-burunlu roket −0,073, düz silindir 0,000, Ahmed −0,002) ama
eşiği dört şekle kalibre etmek aşırı-uydurma olurdu; burun yönü `nose_axis`'in
işidir. (ii) Küt cisme dokunulmaz: eğik küpün köşe-önde mi yüz-önde mi istendiği
geometriden çıkarılamaz. (iii) Zaten kanonik girdi döndürülmez — eksenel simetride
PCA enine düzlemde keyfî açı seçtiği için kanonik roket ~0,1° dönüp ağı bozuyor ve
yanlış "hizalandı" beyanı veriyordu; en yakın eksen-permütasyonuna oturtuldu.

### 3.4 ✅ Birim-ölçek tespiti — sınıf önceli uygulandı, sınır beyanlı (2026-08-20)
**Ne:** >50→mm sezgisi gerçek CAD'de tutarsız (f16 1.5m çıktı). Geometri-tipi + tipik-boy
priori ile daha akıllı. **Neden:** Re/hız/mesh hepsi ölçeğe bağlı.

**ÖLÇÜLDÜ (5 araç × 4 birim):** kural **m ve mm'de 10/10 doğru, cm ve inç'te 10/10
yanlış**. Yol haritasındaki "f16 1,5 m çıktı" belirtisi birebir üretildi: cm cinsinden
15 m'lik F-16 → ham 1500 → ÷1000 → 1,5 m.

**Öncelli tasarım ÇALIŞMIYOR — sayıya bakıldı:** araç bandı 0,05–10 m (200× genişlik),
aday birimler arası fark ≤39×. Bu yüzden çoğu girdide iki-üç aday birden makul çıkar ve
"belirsiz" hükmü kural olur, istisna değil. Sınıflandırmanın ölçekten bağımsız olduğu
doğrulandı (6 mertebe boyunca aynı sınıf), yani "önce sınıflandır sonra ölçekle" teknik
olarak mümkün — ama sınıfa özel dar boy önceli bir **ürün kararıdır**, geometriden
çıkarılamaz.

**TEMEL SINIR:** dış bilgi olmadan *1,5 m'lik model uçak* ile *yanlış ölçeklenmiş 15 m'lik
F-16* geometrik olarak AYIRT EDİLEMEZ.

**Yapılan (tahmin değil, görünürlük):** `birim_varsayimi()` varsayımı her koşuda beyan
ediyor; sonuç araç bandının dışındaysa hangi birim varsayımlarının banda düşeceğini
listeleyip kararı çağırana bırakıyor. Yanlış ölçeklemelerin **5/10'u artık görünür**,
kalan 5'i ilkece ayırt edilemez. Uyarı `auto_configure` uyarılarına bağlandı — üretim
yolundan geçtiği testle doğrulanıyor (bu deponun baskın kusuru: kapı var, çağıran yok).

**ÖNCEL TANIMLANDI (kullanıcı beyanı, 2026-08-20): BİLSEM roketleri 0,3–2 m.** Uygulandı;
kanatçıklı roketler ayrı etiket aldığı için (ölçüldü: 3 ve 4 kanatçıkta `kanatli_roket`)
öncel her iki sınıfa bağlı. Uçtan uca ölçüm (6 roket boyu × 4 birim, `auto_configure`):

| dosya birimi | öncesi | sonrası |
|---|---|---|
| m | 6/6 | 6/6 |
| mm | 6/6 | 6/6 |
| cm | **0/6 (sessizce yanlış)** | **6/6** |
| inç | 0/6 | 2/6 (kalanı beyanlı varsayım) |

Kalan belirsizliğin tamamı cm↔inç (2,54× ayrı); inç **elenmiyor**, metrik varsayılıyor ve
bedel yazılıyor ("dosya inç ise Lmax 2,54× hatalı olur") — gerçekleşen sapma 2,536×.
İki tuzak: sınıf bandı nominaldir, sert sınır değil (2,0 m'lik roket ağ yuvarlamasıyla
kenardan düşüyordu → %5 pay; %15 denendi, inç adayını banda sokup temiz çözümü bozdu),
ve güvenlik kuralı — mevcut sonuç bandın içindeyse dokunulmaz, çünkü öncel o vakada
yanlış olabilir (5 m'lik roket `band_disi` alır, ölçeği BOZULMAZ).

**BİRİM SİSTEMİ KARARI (2026-08-20): iç sistem coherent SI (metre) KALIYOR.** mm–t–s–MPa'ya
geçme önerisi değerlendirildi ve reddedildi. Üç gerekçe: (i) çözmek istediği sorunu
çözmüyor — belirsizlik *dosyanın* ne demek istediğinde, bizim neyle hesapladığımızda
değil; ham Lmax 90 hangi iç birimde olursak olalım cm↔mm belirsizdir. (ii) Yarıçapı
ölçüldü: ρ=1,225 otuz dört dosyada, ν on sekizde, g yedide, yedi çapanın hepsi SI Re/L/U
üzerinden tanımlı — dönüşüm ölçülmüş çapa tabanını yeniden türetip yeniden koşmayı
gerektirir. (iii) FSI arayüzünde CFD ve FEA şu an aynı sistemde; iki sistem yük/deplasman
aktarımına çarpan sokar ve yeni bir sessiz-hata sınıfı açar. mm okunabilirliği istenirse
doğru yer **sunum katmanıdır** (rapor/arayüz mm gösterir, hesap SI kalır).

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
