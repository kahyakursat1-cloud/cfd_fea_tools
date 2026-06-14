# Çalışma Zarfı — Geçerlilik Sınırları

Analizden **önce** istenen koşulu bu tabloya göre sınıfla. Kapsam dışıysa ya
çekince koy ya reddet (SKILL.md adım 2).

| Koşul | Güvenilirlik | Kanıt / Not |
|-------|--------------|-------------|
| Bağlı akış: α ≤ 8°, M < 0.3 | ✅ Yüksek | NACA0012 α=4°: Cd %2.2 hata |
| Yapısal lineer statik (FEA) | ✅ Çok yüksek | Ankastre kiriş analitik %0.05 |
| Mesh yakınsama (GCI) | ✅ | GCI %0.09 (airfoil) |
| Stall / CLmax (α > 8°) | ⚠️ ±2-3°, ±%15 | RANS ayrılma yaklaşık — bant ver, kesin sayı verme |
| Süpersonik roket Cd (inviscid) | ⚠️ Trend OK, mutlak ✗ | Mutlak Cd için viskoz duvar (`dogrulama_modu=True`) |
| y⁺ < 1 transition / ayrılmış akış | ❌ Kapsam dışı | C-grid / DES gerekir — reddet |
| Pervane/itki indüklemeli akış | ⚠️ Modellenmez | Aktüatör-disk yok; gerçek itki-altından sapar |

## Yakınsama & kalite eşikleri (CLAUDE.md proje kuralı)

- CFD residuals **< 1e-4** (simpleFoam/icoFoam). Üstündeyse yakınsamamış say.
- Mesh: `maxNonOrthogonality < 70`, `maxSkewness < 4`.
- y⁺ hedefi rejime göre: duvar-fonksiyonu RAS için y⁺≈30 (otopilot varsayılanı);
  transition/düşük-Re için y⁺<1 gerekir ama bu çözücü kapsamı dışında.
- FEA mesh tipi C3D8R varsayılan; lineer statik. Nonlineer/buckling kapsam dışı.

## Rejim → yöntem uygunluğu (auto_pilot.apply_type_settings ile uyumlu)

- **roket** → supersonic Cd-Mach taraması, M=[0.8,1.2,2.0,3.0]. inviscid+analitik
  sürtünme (hızlı) veya viskoz kΩ-SST (`dogrulama_modu`, mutlak Cd).
- **ucak** → subsonic polar, AoA=[0,2,4,6,8]°, U∞=25 m/s, kaldırma-ilgili
  (planform) referans.
- **multikopter** → subsonic tekil, U∞=12 m/s, frontal referans.
- **genel** → muhafazakâr subsonic tekil, U∞=20 m/s; tip belirsizse elle netleştir.

Kaynak: `README.md` "Çalışma Zarfı" tablosu, `CLAUDE.md` (proje), `auto_pilot.py`
`apply_type_settings` / `narrate`.
