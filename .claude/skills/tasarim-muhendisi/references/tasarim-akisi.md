# Tasarım Akışı — decompose → dispatch → synthesize

## 1. Decompose (böl)
- Gereksinimi ölçülebilir başarı kriterlerine çevir: `{L/D≥12, SF≥1.5, m≤2.4 kg, maliyet≤X}`.
- Hangi disiplinler gerekli? Bağımlılık grafiğini çiz (bkz. `disiplinler.md` kuplaj şeması).
- Serbest parametreleri ve aralıklarını belirle (MDAO taraması gerekiyorsa uzay tanımı).

## 2. Dispatch (devret)
- Bağımsız disiplinler → **paralel** (tek mesajda birden çok Agent tool çağrısı).
- Kuplajlı disiplinler → **sıralı** (aero → yük → yapısal; sonra malzeme; en sonda MDAO takas).
- Her ajana gereksinim + kısıt + önceki kuplaj çıktısını ver. Kart eksikse geri sor.

## 3. Synthesize (sentezle)

### Trade-off matrisi
Disiplin kartlarını tek tabloda topla. Örnek:

| Tasarım seçeneği | Aero (L/D) | Yapısal (SF, kütle) | Malzeme/maliyet | MDAO notu | Birleşik güven |
|------------------|-----------|---------------------|-----------------|-----------|----------------|
| A — ince profil  | 15 ±%8    | SF 1.3 ⚠️, 2.1 kg   | CFRP, ~$X       | Pareto'da | ⚠️ (yapısal zayıf) |
| B — kalın profil | 12 ±%6    | SF 1.9 ✅, 2.6 kg   | Al7075, ~$Y     | dominant  | ✅ |

- Her hücrede **bant/işaret** koru. Çelişkiyi görünür yap (A aero'da iyi, yapısalda zayıf).
- **En zayıf halka:** birleşik güven, satırdaki en düşük disiplin güveninden yüksek olamaz.

### Çelişki uzlaştırma
- Ağırlıklandırma varsayımını **açık** yaz (ör. "kütle > aero-verim > maliyet"; gerekçe).
- Kısıtı ihlal eden seçenekleri ele (SF<1.5 → güvensiz, cepheden çıkar).
- Optimum taranan uzayın kenarındaysa "uzayı genişlet" uyarısı ver.

## 4. Karar-raporu şablonu (çıktı)

```markdown
# Tasarım Kararı — <proje/parça>

## Gereksinim & başarı kriteri
<ölçülebilir kriterler + kısıtlar>

## Önerilen tasarım
<seçilen nokta/parametreler + ana sayılar, HER BİRİ ± V&V/UQ bandı>
- Aero: L/D=.. ±.. | Yapısal: SF=.., m=.. kg | Malzeme: <ad>, ~$.. | Yöntem: <imalat>

## Gerekçe
<neden bu nokta; hangi takas kazandı; ağırlıklandırma varsayımı>

## Reddedilen alternatifler
<A/B/... neden elendi — 1'er cümle>

## Birleşik güven & kalan riskler
<✅/⚠️/❌ + en zayıf halka; zarf-dışı/düşük-güven disiplinler; doğrulanmamış surrogate>

## Sonraki doğrulama adımı
<ör. seçilen noktayı `python design_explorer.py --mode cfd` ile teyit;
 yapısalı hassas mesh + GCI'de tekrarla; kritik yükü coupling ile doğrula>
```

## Dürüstlük kuralları (sentezde asla ihlal etme)
- Nokta değil **bant**; en zayıf halka birleşik güveni belirler.
- Surrogate önizlemesini karar gerekçesi yapma — CFD/GCI ile teyit et.
- Zarf-dışı disiplin → tasarım seviyesinde işaretle, aşağı-akış kartlarını çekinceli say.
- Ölçülmeyeni "ölçülmedi" yaz; sayıyı süsleme, yuvarlama yapma.
