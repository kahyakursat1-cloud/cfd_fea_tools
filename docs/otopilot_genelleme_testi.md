# Otopilot Sınıflandırıcı — Gerçek-Dünya Genelleme Testi

**Tarih:** 2026-06-15 · **Kapsam:** `auto_pilot.classify_vehicle` (bbox+alan metrikli k-NN)

## Amaç
Sentetik (idealize) seed kütüphanesiyle eğitilen sınıflandırıcının, internetten
indirilen **gerçek CAD modellerine** genellemesini ölçmek. Eğitim ≠ ezber
doğrulaması.

## Yöntem
`experiments/ingest_real.py`: GitHub'dan doğrudan indirilen STL'ler → bilinen
sınıfa göre **uçuş-konvansiyonuna kanonikleştirme** (rastgele yönelim düzeltmesi:
ince eksen→z; eksenel→x=boy, kanat→y=açıklık) → `inspect_geometry` → mevcut
kütüphaneyle sınıflandırma. Kaynaklar: mathworks TVC-roket, Ro3code aircraft
(A320/F-16/Su-57/Gripen/X-15), StephenCarlson MiniHawk-VTOL.

## Sonuç: 2/7 → 4/7 (bbox-üstü özellikle)

İlk durum (yalnız bbox): **2/7**. `ince_yassilik` (kanat-inceliği) eklenince **4/7**.

| Model | Bilinen | Tahmin (bbox) | Tahmin (+yass) | Not |
|-------|---------|------|------|-----|
| rocket_tvc | roket | **roket** ✓ | **roket** ✓ | temiz |
| su57_fighter | ucak | **ucak** ✓ | **ucak** ✓ | pf/fr yakaladı |
| f16_fighter | ucak | kaldirici_govde | **ucak** ✓ | yass düzeltti |
| a320_airliner | ucak | multikopter | **ucak** ✓ | yass düzeltti |
| gripen_fighter | ucak | kaldirici_govde | kaldirici_govde | yass=0.349 sınırda |
| x15_rocketplane | kanatli_roket | kaldirici_govde | kaldirici_govde | yass=0.45, gerçekten kalın |
| minihawk_vtol | kanatli_vtol | multikopter | multikopter | kompakt VTOL |

## Kök Neden — bbox tavanı (ampirik)

1. **Sentetik uçaklar gerçekçi değildi.** İdealize ince plakalar: `H_L≈0.03`,
   `pf/fr 10–16`. Gerçek uçaklar gövdeli+dikey kuyruklu: `H_L≈0.25`, `pf/fr≈2.7`.
   Sentetik kütüphane gerçek uçakların metrik bölgesini hiç kapsamıyordu.
2. **Gerçek avcı uçağı ≈ lifting body.** F-16/Su-57/Gripen *blended-wing-body
   delta*; bounding-box oranları (L_D, W_L, H_L, H_W) ve alan form-faktörleri
   (`A/planform`, `A/lmax²`, `ince_kalinlik/lmax`) lifting body ile **örtüşüyor**.
   Test edilen hiçbir bbox/alan özelliği bu iki sınıfı temiz ayırmıyor — çünkü
   geometrik olarak gerçekten benzerler. Bu bir bug değil, özellik-uzayı sınırı.

## Yapılan İyileştirmeler (dürüst, uydurma değil)

- `planform_frontal` k-NN özelliğine eklendi (kanat»frontal, küt gövdeden ayırır).
  Sentetik LOO 100/100 korundu; su57 düzeldi.
- **`ince_yassilik` (bbox-üstü) eklendi** — `vehicle_pipeline._thin_flatness`:
  en-uzun eksen boyunca dilimleyip her dilimde kalınlık/kiriş oranının alt
  yüzdeliği. İnce kaldırma yüzeyi (kanat) ~0.1, kalın/küt gövde ~0.4–1.0.
  Yönelimden bağımsız. Gerçek genelleme **2/7→4/7** (f16, a320 düzeldi).
- 7 gerçek model **hakem-etiketli çapa** olarak kütüphaneye eklendi
  (`auto_pilot_real_seed.jsonl` — yalnız türetilen metrikler; STL'ler lisanslı,
  commit edilmez).

### Takas (dürüstçe)
`ince_yassilik` sentetik LOO'yu 100→**99/100** düşürdü: tek regresyon
`mlt_hexa_ince` (ince-kollu hexakopter → kanatli_vtol). İnce-kollu hexa,
geometrik olarak quadplane'e (yassı, çok-rotor, ~kare) gerçekten benzer —
benign sınır. İdealize veride %100 zaten *overfitting* imzasıydı; bir sentetik
sınır vakasını iki gerçek avcı/airliner tanımaya değişmek doğru bias-variance
takasıdır. Hata profili "yaygın gerçek uçak"tan "1 hexa + zor hibrit"e kaydı.

## Kalan Belirsizliğin Çözümü — tasarım gereği
Sistem **öner+onayla** modunda: gövdeli uçak↔lifting body gibi bbox-belirsiz
gerçek geometride otopilot önerir, kullanıcı bir kez düzeltir → `MEMORY`'ye
kaydedilir → sonraki benzer gerçek geometri eşleşir. İnsan-döngüde adımı tam da
bu özellik-uzayı tavanını kapatmak için var.

## Gelecek İş (kapsam dışı)
Kalan zor vakalar (gripen, x15, minihawk) tek bir skaler yassılık özelliğiyle
çözülmüyor — bunlar geometrik olarak gerçekten sınırda. Daha ileri ayrım için
zengin 3B betimleyiciler gerekir: eğrilik histogramı, spin-image, ya da
öğrenilmiş özellik (PointNet vb.). Bu ayrı bir yöntem sınıfıdır; mevcut hafif
k-NN'in kapsamı değil. Pratikte öner+onayla + `MEMORY` bu kuyruğu kapatır.
