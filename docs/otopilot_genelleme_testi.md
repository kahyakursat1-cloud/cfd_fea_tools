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

## Sonuç: 2/7 uyum

| Model | Bilinen | Tahmin | Not |
|-------|---------|--------|-----|
| rocket_tvc | roket | **roket** ✓ | temiz ayrışır |
| su57_fighter | ucak | **ucak** ✓ | pf/fr çapayı yakaladı |
| f16 / gripen | ucak | kaldirici_govde | blended-wing-body |
| a320 | ucak | multikopter | W/L≈0.9 + yassı |
| x15_rocketplane | kanatli_roket | kaldirici_govde | gerçekten sınırda |
| minihawk_vtol | kanatli_vtol | multikopter | kompakt VTOL |

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
  Sentetik LOO **100/100 korundu**; su57 artık doğru.
- 7 gerçek model **hakem-etiketli çapa** olarak kütüphaneye eklendi
  (`auto_pilot_real_seed.jsonl` — yalnız türetilen metrikler; STL'ler lisanslı,
  commit edilmez).

## Kalan Belirsizliğin Çözümü — tasarım gereği
Sistem **öner+onayla** modunda: gövdeli uçak↔lifting body gibi bbox-belirsiz
gerçek geometride otopilot önerir, kullanıcı bir kez düzeltir → `MEMORY`'ye
kaydedilir → sonraki benzer gerçek geometri eşleşir. İnsan-döngüde adımı tam da
bu özellik-uzayı tavanını kapatmak için var.

## Gelecek İş (kapsam dışı)
Gerçek avcı↔lifting body ayrımı için bbox-üstü betimleyiciler gerekir: eğrilik
histogramı, spin-image, ya da öğrenilmiş 3B özellik (PointNet vb.). Bu ayrı bir
yöntem sınıfıdır; mevcut hafif k-NN'in kapsamı değil.
