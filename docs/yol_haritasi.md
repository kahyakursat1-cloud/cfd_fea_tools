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
| Nonlinear/Dynamic FEA | `NLGEOM` ve `*DYNAMIC` yazıcıda | CSM1 %0,11 · CSM3 üç kanal <%1 | yalnız GUI |
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

1. **Load Completeness Gate.** Viskoz payı bilinmiyorsa sonuç `DESIGN`
   sınıfı alamaz. Gerekçe ölçülü: 195 kayıttan 138'inde (üretim araç yolu
   dâhil) basınç/viskoz ayrımı hiç kaydedilmemiş, okunabilen 16 ailenin
   9'unda viskoz pay %5'i aşıyor, Turek–Hron bayrağında %410.
2. **FSI Transfer Health kartı** — `esleme_is_payi` üzerinden, toplam
   artık üzerinden **değil**. Kart ayrışımı göstermeli, yoksa okur yine
   toplamı üretime yazar.
3. **Nonlinear/Dynamic FEA'yı GUI'ye taşı.** Arka uç bitti ve yayımlanmış
   değere karşı doğrulandı; kullanıcıya görünmeyen bir yetenek duruyor.
   Öneride P1'di, buraya alındı — maliyeti saatler, değeri bugün.
4. **Benchmark orkestrasyonu** — 9 betiği tek komuta bağla.

### V1.2 — kampanya planlayıcısı

Önerinin "en çok fark yaratır" dediği madde. Ağ ailesi + GCI/LSR arka uçta
var; eksik olan **"bu sonucu yayımlamak için ne gerekli"** sorusunu
maliyetle cevaplayan katman: kaç seviye, tahmini süre/RAM, hangi ek koşular.

### V1.3 — doğrulama zarfı panosu + kanıt görüntüleyici

`DOĞRULANMIŞ / EĞİLİM / ZARF-DIŞI` sınıfları zaten üretiliyor; eksik olan
görünürlük ve "bu hücreyi hangi çapa destekliyor" bağlantısı.

### V1.4 — FSI ağ GCI'si, sonra FSI2/FSI3

- FSI1 için akış **ve yapı** ağ duyarlılığı. Akış ailesi kurulu
  (`turek_hron_ag_bagimsizligi.py`), yapı ailesi yok.
- FSI2/FSI3 zaman-bağımlı kuplaj. Yapısal ön koşul CSM3 ile doğrulandı;
  kuplajın kendisi yazılmadı. Ağ hareketinin Gauss sönümden gerçek bir
  Laplace çözümüne geçmesi gerekebilir.

### V1.5 — çok amaçlı TO + imalat kısıtları

Ağırlıklı amaç (compliance + gerilme + kütle), Pareto cephesi; minimum
üye boyu, simetri, çekme yönü, korunan arayüzler.

### V2.0

Sıkıştırılabilir CFD + V&V, temas/plastisite, kompozit hasar, GPU/HPC.

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
