# Disiplin Ajanları — Kadro, Araç, Dispatch

Ajanlar `.claude/agents/`'te tanımlı. **Agent tool** ile çağır; her biri sabit
formatta bir *disiplin kartı* döner. Ajanlar solver dosyası sıfırdan yazmaz —
mevcut proje araçlarını sürer ve `analiz-muhendisi/references/*` kılavuzlarına dayanır.

## Kadro

| Ajan | Kapsam | Sürdüğü araç | Döndürdüğü kart |
|------|--------|--------------|-----------------|
| **aero-muhendisi** | Cl, Cd, L/D, polar, kararlılık, stall/ayrılma, Mach | `auto_pilot.auto_configure`, `vehicle_pipeline.run_vehicle_analysis`, `pipeline.py vspaero`, XFLR5/OpenFOAM (manuel) | Aero kartı + basınç/yük çıktısı (yapısala girdi) |
| **yapisal-termal-muhendisi** | von Mises, SF, deplasman, modal, burkulma, termal gerilme | `pipeline.py loads/fea/coupling`, `fea_runner`, CalculiX (manuel) | Yapısal/termal kartı + kütle |
| **malzeme-imalat-muhendisi** | Malzeme seçimi, spesifik dayanım, DFM, tolerans, maliyet | `materials.json` / `material_database.py` | Malzeme/imalat kartı |
| **sistem-mdao-muhendisi** | DOE/LHS, Pareto, boyutlandırma, duyarlılık, ağırlıklandırma | `design_explorer.py` (`explore`/`evaluate_surrogate`/`evaluate_cfd`), `make_doe_figure.py` | Sistem/MDAO kartı |

## Kuplaj ve sıra

```
              ┌─ malzeme (SF/kütle girdisiyle) ─┐
aero ──yük──▶ yapısal/termal ───────────────────┼──▶ sistem/MDAO (sentez/takas)
  │                                             │
  └─ (bağımsız: erken tarama istenirse MDAO en başta surrogate ile) ─┘
```

- **aero → yapısal:** aero ajanı basınç alanı (VTK) üretir; yapısal ajan
  `pipeline.py coupling <VTK> <STL>` ile FEA yüküne çevirir. **Aero bitmeden
  yapısal başlamaz** (sıralı).
- **yapısal → malzeme:** malzeme ajanı SF ve kütle hedefiyle aday sıralar; yapısal
  karttan sonra çalışması daha isabetli (ama bağımsız da çalışabilir, ön-eleme için).
- **MDAO iki konum:** (a) *en başta* — parametre uzayını `evaluate_surrogate` ile
  ucuz tara, umut veren bölgeyi daralt; (b) *en sonda* — disiplin kartlarını Pareto/
  takasa çevir, seçilen noktayı `evaluate_cfd` ile doğrula.

## Paralel mi, sıralı mı?

| Senaryo | Dispatch |
|---------|----------|
| Aero + malzeme ön-eleme (yükten bağımsız) | **Paralel** (tek mesajda 2 Agent çağrısı) |
| Yapısal (aero yüküne bağlı) | Aero'dan **sonra sıralı** |
| Malzeme nihai (SF/kütle girdili) | Yapısal'dan sonra |
| MDAO geniş tarama | En başta, tek başına (surrogate) |
| MDAO nihai takas | En sonda, tüm kartlar geldikten sonra |

Kural: **bağımlılık yoksa paralel, veri akışı varsa sıralı.** Bağımsız disiplinleri
aynı mesajda birden çok Agent tool çağrısıyla başlat.

## Ajana ne verilir
- Geometri/STL yolu veya parametre seti.
- O disipline ait gereksinim + başarı kriteri (SF≥1.5, L/D≥12, kütle≤X, maliyet≤Y).
- Varsa önceki ajanın kuplaj çıktısı (aero VTK, yapısal SF/kütle).
- Çalışma-zarfı bağlamı (hız, irtifa, AoA, sıcaklık).

Kart eksik/çelişkiliyse ajana **geri sor**; körlemesine sentezleme.
