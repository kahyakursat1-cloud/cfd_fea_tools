# Yol Haritası — ürün katmanı

**Kaynak:** dış inceleme (2026-08-28), platformun tezine dayanan bir öneri
listesi: *sayı → belirsizlik → geçerlilik → karar*. Öneri doğru okumuş —
kalan işin çoğu yeni çözücü değil, mevcut ölçümleri **karar verilebilir**
hâle getiren katman.

**Bu dosyanın kuralı:** bir madde "bitti" diye işaretlenmeden önce koşan
bir kanıt dosyası ve onu kurala bağlayan bir test gerekir. Öneri metnindeki
sıralama olduğu gibi alınmadı; farklar aşağıda **gerekçesiyle** yazılı.

---

## Zaten arka uçta bitmiş olanlar

Öneri listesinin P0 satırının yarısı 2026-08-27/28'de kapandı. Yeniden
yazılmasın diye buraya alınıyor; eksik olan **ürün katmanı**, fizik değil.

| Öneri | Arka uç | Kanıt | Kalan |
|---|---|---|---|
| Surface Traction Transfer | `coupling_fsi.cfd_pressure_to_fea_loads(kayma=True)`; `t = -p n + mu (grad U + grad U^T) n` | `turek_hron_fsi1.json` — toplam viskoz kuvvet çözücünün `forces` çıktısıyla %0,95 | varsayılan/isim, **Load Completeness Gate**, GUI'de yük bileşimi |
| Report Integrity Gate | `experiments/rapor_butunlugu.py` + `tests/test_rapor_kapsam_senkronu.py` | `rapor_butunlugu.json` | bayat **sayı** denetimi, DOI, tek `report_check()` girişi |
| FSI Benchmark Manager | 9 betik: ağ, ağ-ailesi, CFD1, FSI1, FSI1-iki-yönlü, CSM1, CSM3 | `turek_hron_*.json` | orkestrasyon + tek komut + GUI |
| Nonlinear/Dynamic FEA | `NLGEOM` ve `*DYNAMIC` yazıcıda | CSM1 %0,11 · CSM3 üç kanal <%1 | GUI maddesi ÖLÇÜLÜP kapandı (V1.1/4) |
| FSI Transfer Quality (ölçüm) | kuvvet/moment/iş + **eşleme–yüzey ayrışımı** | `fsi_korunum.json` | kart, heatmap, kapı eşiği |
| V&V Campaign (parçalar) | `vehicle_pipeline` ağ ailesi + GCI/LSR | `mesh_duyarlilik` | **planlayıcı** (maliyet/süre, "yayımlamak için ne gerekli") |

---

## Öneriden ayrıldığım tek teknik nokta

Öneri, FSI sağlık kartında **arayüz işi artığını** doğrudan bir RET
ölçütü yapıyor (`Interface work %8,7 ⚠`). **Bu hâliyle iyi sonuçları
reddeder.**

`arayuz_isi_hatasi` düğüm momentini (üretimdeki korunumlu şema) yüz
momentiyle (**terk edilmiş** şemanın FEA yüzünde yeniden integre ettiği
kuvvet) kıyaslar — yani şemaları kıyaslar, eşlemeyi ölçmez. Doğru referans
CFD tarafıdır ve orada bir kimlik vardır:

    T_düğüm − T_CFD  =  Σ_f dF_f ⊗ δ_f ,   δ_f = Σ_k w_k x_k − x_cfd,f

Kimlik 24/24 vakada ≤1e-10 tuttu. Ayrışım: **eşleme payı en kötü %24,1,
19/24 vakada %1'in altında**; geri kalanı terk edilmiş şemadan.

**Kapı `esleme_is_payi`'na bağlanmalı, toplam artığa değil.**

Bundan çıkan "δ'ya bakıp kuplajdan önce uyaralım" fikri denendi ve
**çürüdü**: δ'nın kuvvet-ağırlıklı ve en-büyük ölçüleri eşleme payıyla
korele değil (Spearman 0,00 ve −0,25; n=24, kritik |r|≈0,41). Hata bir
tensör normudur; skaler bir sapma ortalaması yön uyumunu göremez. Doğru
kapı, yükler geldikten **sonra** eşleme payını doğrudan hesaplamaktır —
ucuzdur ve yapısal çözümden öncedir.

---

## Sıra

### V1.1 — mevcut sonuçları yayımlanabilir yapan ucuz kazanımlar

Hepsi mevcut parçaların birleştirilmesi; yeni fizik yok.

1. ~~**Load Completeness Gate.**~~ **BİTTİ** (`validity_envelope.classify_fea`
   `yuk_bileseni` alır; üç dal: kayma taşındı / pay küçük / pay bilinmiyor
   ya da büyük → EĞİLİM). Eşik `kayma_payi.ESIK_PCT`'ten tek kaynaktan
   okunuyor. `vehicle_fea` payı koşu dizininden okuyup kapıya taşıyor ve
   bir AST testi bunu kilitliyor. Gerekçe ölçülü: 195 kayıttan 138'inde
   ayrım hiç kaydedilmemiş, okunabilen 16 ailenin 9'unda pay %5'i aşıyor,
   Turek–Hron bayrağında %410.
2. ~~**Aktarım kapısı doğru artığa baksın.**~~ **BİTTİ** — `aktarim_hukmu`
   artık `esleme_is_payi_pct` alıyor; ayrışım yoksa toplama düşüyor ama
   bunu hükümde açıkça söylüyor. `fsi_surucu` payı üretip taşıyor.
3. **FSI Transfer Health kartı** — ölçüm hazır, eksik olan GUI. Kart
   ayrışımı göstermeli, yoksa okur yine toplamı üretime yazar.
4. ~~**Nonlinear/Dynamic FEA'yı GUI'ye taşı.**~~ **ÖLÇÜLDÜ VE KAPANDI —
   yapılmasına gerek çıkmadı.** Ön koşulu önce kapatıldı: üretim yolu
   `.inp` metnini elle düzenliyordu (`txt.replace("*STATIC", ...)`) ve
   NLGEOM açılır açılmaz patlayacaktı; `FEACase.dugum_kuvvetleri` eklenip
   üç enjeksiyon birden kaldırıldı. Ardından asıl soru soruldu: **büyük
   yer değiştirme nerede başlıyor?** Literatürden bir sayı almak yerine
   ölçüldü (`experiments/buyuk_yer_degistirme_esigi.py`; CSM1 konsolu,
   yerçekimi süpürmesi, bir çift koşu 10 s):

   - Enine sehim: `sapma% = 0,0077·(δ/L %)^2,02`, en kötü artık %1,4,
     band δ/L %0,48–18,9. Üstel **ölçüldü**, varsayılmadı. → %1 hata için
     eşik **δ/L = %11,1**.
   - Eksenel kısalma: bandın tamamında %99,7–99,99 yanlış ve **eşikten
     bağımsız** — lineer kinematikte ikinci-mertebe terim yok.

   **Sonuç:** üretim yolundaki mekanizma kapısı δ/L > %5'te sonucu zaten
   GEÇERSİZ ilan ediyor; ölçülen eşik (%11,1) onun üstünde. Geçerli
   pencerenin tamamı lineerin içinde, dolayısıyla o pencerede NLGEOM enine
   sehmi düzeltmez. Madde gerekçesiyle kapandı, sessizce düşürülmedi.

   **Ne zaman geri açılır:** eksenel yolun besleme yapmaması mesnet
   presetlerinin **tek yüz** tutmasına dayanıyor (uç eksenel serbest → zar
   sertleşmesi yok). İki ucu tutulu bir preset ailesi eklenirse lineer bu
   banttan çok önce bozulur. Ölçülen eşik bir **alt sınırdır**.
   `vehicle_fea._lineer_gecerlilik` gerekçeyi yazıyor; iki test bağlıyor
   (mekanizma tavanı < %11,1 · presetler tek düzlem).
5. ~~**Benchmark orkestrasyonu**~~ **BİTTİ** —
   `experiments/turek_hron_kiyaslama.py`: sekiz aşamalı zincirin tek
   tablosu, `--kos` ile eksikleri koşar. Sayıları yeniden hesaplamaz,
   kanıt dosyalarından okur (yönetici YOL bilir, DEĞER bilmez; bir test
   bunu AST ile kilitliyor). **BAYATLIK da durumun parçası** ve ilk
   koşusunda iki aşamayı bayat buldu: `gmsh` ve `CFD1` kanıtları kendi
   betiklerinden eskiydi. Yenilenince sayılar birebir aynı çıktı ama
   CFD1'in hükmü hâlâ "ağ-bağımsızlığı sınanmadı" diyordu --- o cümle de
   kanıttan türetilir yapıldı.

6. ~~**Tarihsel/güncel hüküm yönetimi**~~ **BİTTİ** (2026-08-28) —
   ikinci dış hakem raporunun P0'ı. Ölçüm zaten vardı (`hukum_tazeligi`:
   23 koşunun 15'inde kalem-düzeyi hüküm bayat, **on beşi de gevşek
   yönde**) ama tek çağıranı kendi testiydi. Koşu Geçmişi'ne
   *"Bugünkü kurallarla yeniden değerlendir"* düğmesi eklendi: kayıtlı
   hüküm ile bugünkü hüküm yan yana, gevşemede **V&V POLİTİKASI DEĞİŞTİ**
   bandı. Çözücü yeniden koşulmuyor; kayıt değiştirilmiyor (iki test AST
   ile bağlıyor); sıkılaşma yönünde uyarı çıkmıyor.
7. ~~**Rapor bütünlük kapısı genişletildi**~~ **BİTTİ** (2026-08-28) —
   hakem, kapının "bütün" dediği PDF'te iki kusur buldu ve ikisi de
   ölçütün iddiasından dar olmasındandı: ham LaTeX kalıntısı (`??`
   aranıyordu, oysa LaTeX hiç `\ref` görmemişti) ve çakışan şekil
   numaralandırması (yalnız `Şekil N:` sayılıyordu, elle yazılan
   `Şekil N.` ailesi görünmüyordu). Kapak damgası da artık ölçümden
   üretiliyor (`docs/rapor_damga.py`).

### V1.2 — FSI alıcı-ağ yeterliliği ✅ BİTTİ (2026-08-28)

Hakem RBF/mortar önerisini **geri çekti** ve yerine bunu koydu; ayrışım
onu haklı çıkarıyor: `_fsi_esnek`'in %102,64'ünün yalnız %24,10'u gerçek
eşleme, %78,60'ı yüzey/yeniden-integrasyon farkı. Yani çare daha zengin
bir eşleme şeması değil, **alıcı FEA yüzeyinin CFD yük dağılımını
çözebilmesi**. Çok daha ucuz ve mühendislik olarak doğru sıra.

**Ölçüldü ve iki ayrı sonuç çıktı.** (a) Eşleme payı: gerçek geometrilerde
15/15 vakada %1'in altında; en kötü %24,1 olan vakanın alıcı yüzeyi 12
üçgenlik bir sınama kutusu. Yeterliliğin doğal ölçütü sanılan *çözünürlük
oranı* hiçbir şey yordamıyor (ρ=+0,01 / −0,33, kritik 0,52). (b) Araç
yolunun UYGULADIĞI yük aerodinamik kuvvetten medyan %9,5 sapıyordu — bu
eşleme değil ŞEMA hatasıydı.

**Sonuç:** araç yolu (dolu-katı + kabuk) korunumlu şemaya taşındı. Korunum
artığı 4,8e-15 ve her koşuda ölçülüyor. T6 tutarlılığı korundu (kuadratik
şekil fonksiyonları; üniform basınçta eski kurala iniyor).

### V1.2b — iki-hızlı katmanın DENETLENMESİ ✅ BİTTİ (2026-08-28)

Bugünkü yük kusuru teknik değil **yapısal** bir sebeple hayatta kaldı:
`fsi_korunumlu_esleme.disa_yonlendir` centroid ölçütünü zaten çürütmüş ve
gerekçesini kendi gövdesine yazmıştı; `vehicle_fea` aynı ölçütü kullanmaya
devam ediyordu. İki yol yan yana, biri dersi öğrenmiş öteki duymamış.

Bu, CLAUDE.md'nin "iki-hızlı uyarı"sının ilk **ölçülmüş** bedeli (yükün
%70'i). Gereken şey büyük bir refactor değil — o riskli ve ayrı iş. Gereken:
bir düzeltme yapıldığında *"aynı kusur hangi öteki yolda duruyor"* sorusunu
soran bir denetim. **Yapıldı:** `iki_hiz.py`, `saglik.py`'nin altıncı ölçeri. İki iş yapar:

1. Kayıtlı uygulamaları paylaştıkları sözleşmeye karşı **davranışla** sınar.
   İlk sözleşme *"yönlendirme bütünseldir"* — üç uygulama (araç yolu, FSI
   eşlemesi, ölçüm betiği) geçiyor.
2. **Kayıtsız aday** tarar: sözleşmenin konusu olan işi yapıp kayıtta
   bulunmayan kod. Bugünkü kusuru yakalayacak olan budur — kusur kayıtlı bir
   uygulama DEĞİLDİ, ham bir maske atamasıydı. Depoda bugün 0 aday.

**Kısıt yazılı:** kod-klonu dedektörü değil; sözleşmeler elle bildirilir.
Ölçtüğü şey "iki-hızlı katman temiz" değil, "bildirilen sözleşmelerde
ayrışma yok".

**İkinci sözleşme ailesi bildirildi (2026-08-28):** *"yük aktarımı
korunumludur"* — `fsi_korunumlu_esleme.korunumlu_dagit` ve araç yolunun T6
dağıtımı. Negatif kontrol eski şemayı reddediyor.

**Sınav geometrisi iki kez kusuru işletmiyordu** ve ikisi de düzeltildi:
yönlendirmede dışbükey kutu (→ iki ayrık küp), korunumda eşit-alanlı küp
(→ alan oranı 7,2). İki test sınavların yeterliliğini bağlıyor.

### V1.3 — kampanya planlayıcısı

Önerinin "en çok fark yaratır" dediği madde. Ağ ailesi + GCI/LSR arka uçta
var; eksik olan **"bu sonucu yayımlamak için ne gerekli"** sorusunu
maliyetle cevaplayan katman: kaç seviye, tahmini süre/RAM, hangi ek koşular.

### V1.4 — doğrulama zarfı panosu + kanıt görüntüleyici

`DOĞRULANMIŞ / EĞİLİM / ZARF-DIŞI` sınıfları zaten üretiliyor; eksik olan
görünürlük ve "bu hücreyi hangi çapa destekliyor" bağlantısı.

### V1.5 — FSI ağ GCI'si, sonra FSI2/FSI3

- FSI1 için akış **ve yapı** ağ duyarlılığı. Akış ailesi kurulu
  (`turek_hron_ag_bagimsizligi.py`), yapı ailesi yok.
- FSI2/FSI3 zaman-bağımlı kuplaj. Yapısal ön koşul CSM3 ile doğrulandı;
  kuplajın kendisi yazılmadı. Ağ hareketinin Gauss sönümden gerçek bir
  Laplace çözümüne geçmesi gerekebilir.

### V1.6 — çok amaçlı TO + imalat kısıtları

Ağırlıklı amaç (compliance + gerilme + kütle), Pareto cephesi; minimum
üye boyu, simetri, çekme yönü, korunan arayüzler.

### V2.0

Sıkıştırılabilir CFD + V&V, temas/plastisite, kompozit hasar, GPU/HPC.

---

## Kapsam kararı: tez önerisi

FSI/Turek–Hron çalışması **tez önerisinin kapsamı dışındadır** ve öyle
kalacak. Öneri AS1–AS4 üzerine kurulu (baskı parametreleri → geometri
sapması → aerodinamik katsayı → belirsizlik bütçesi) ve 36 aydan 24 aya
bilinçli daraltılmış. `tez_onerisi.tex`'te FSI'nin hiç geçmemesi bir
unutma değil, o daraltmanın sonucu; kendi kanıt denetimi de 29/29 temiz.

Bugünkü yanlışlanabilirlik örneği (δ ön-uçuş yordayıcısı öngörüsü kuruldu,
n=24 için kritik |r|≈0,41 ölçütüyle sınandı, Spearman 0,00 / −0,25 çıktı ve
geri çekildi) **öneriye değil**, tez yazılırken *"yapılması planlananlar"*
bölümüne girecek. Karar 2026-08-28.

---

## Kapanmamış V&V borçları (sıradan bağımsız, her an geçerli)

- FSI1'in ağ-bağımsızlığı: aktarım yüzeyi on kat inceltildi, **akış ve
  yapı ağı incelmedi**.
- CSM1/CSM3 tek yapı ağıyla koşuldu (kasıtlı — sınanan o ağdı).
- CSM3'te zaman adımı iki seviyede koşuldu; iki seviye bir GCI değildir.
- Metodoloji kaynaklarının DOI/künyesi birincil kaynaktan doğrulanmadı.
- İki-hızlı katman: `simulation_runner.py` ve standalone V&V betikleri
  `analysis/`'i kullanmıyor; `vehicle_fea.py` kendi basınç eşlemesini
  taşıyor ve bu yüzden viskoz kanalı **alamıyor**.
