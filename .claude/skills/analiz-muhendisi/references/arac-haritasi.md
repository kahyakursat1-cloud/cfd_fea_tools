# Araç Haritası — Hangi Araç Neyi Yapar

## auto_pilot.py — karar motoru (GUI'siz, hızlı, harici solver yok)

| Fonksiyon | Girdi | Çıktı / İş |
|-----------|-------|-----------|
| `auto_configure(stl_path, out_dir=..., dogrulama_modu=False)` | STL yolu | Tam config: tip, kalite, rejim, mach/aoa listesi, `plan`, `uyarilar`, `gerekce`. prepare→inspect→classify→settings zincirini koşar. |
| `classify_vehicle(geo)` | geo dict (`boyutlar_m=[L,W,H]`, `on_alan_m2`, `planform_alan_m2`, `govde_sayisi`) | `{tip, guven, metrik, gerekce}`. Kural skoru + k-NN öğrenme oyu. |
| `apply_type_settings(cfg, tip, dogrulama_modu)` | cfg + tip | Tipe göre rejim/Mach/AoA/hız + `plan`. Kullanıcı tip düzeltince de bu çağrılır. |
| `narrate(config, result=None)` | config (+sonuç) | Hakem-seviyesi çevrimdışı eleştiri metni (güven, öğrenme, rejim uygunluğu, V&V çekincesi). `ANTHROPIC_API_KEY` varsa LLM ile zenginleşir. |
| `cd_outlier(vtype, cd)` | tip, Cd | Cd tipik banttan saparsa uyarı stringi, yoksa None. |
| `record_case(metrik, otopilot_tip, onayli_tip, ...)` | — | Onaylı vakayı kütüphaneye yazar (öğrenme). Kullanıcı onay/düzeltme sonrası çağır. |

Tipler: `roket`, `ucak`, `multikopter`, `genel`. Düşük güven eşiği < 0.45.

## vehicle_pipeline.py — gerçek araç CFD koşusu (OpenFOAM gerekir)

```powershell
python vehicle_pipeline.py <model.stl> --tip ucak --hiz 25 --aoa 4 \
       --kalite standart --burun +x --ust +z [--duyarlilik] [--katman N] [--yplus 30]
```
- `--tip`: VEHICLE_PRESETS (ucak/roket/multikopter/genel)
- `--kalite`: MESH_QUALITY (hizli/standart/hassas)
- `--islemci 0` = otomatik çekirdek; `--duyarlilik` = 2. kaba koşu (mesh duyarlılık bandı)
- Programatik: `run_vehicle_analysis(stl_path, vehicle_type, velocity, alpha_deg, ...)`
- Çıktı: araca-uygun mesh → CFD → Cd/Cl/L-D + mühendis raporu (`vehicle_runs/`).

## pipeline.py — V&V / yapısal hat (harici solver GEREKMEZ)

```powershell
python pipeline.py [komut]
```
| Komut | İş |
|-------|----|
| (boş) / `all` | loads → kritik FEA → rapor (`report/VV_report.md`) |
| `loads` | V-n yük zarfı + tasarım-kritik yük durumları → `envelope.json` |
| `fea` | Kritik gust yükünde kanat FEA (limit + ultimate, SF) |
| `validate-fea` | Ankastre kiriş analitik doğrulama (%0.05) |
| `report` | Mevcut JSON'lardan V&V raporu |
| `vspaero α1 α2 ...` | OpenVSP VLM hızlı polar (saniyeler, OpenVSP gerekir) |
| `rocket <file.ork>` | OpenRocket uçuş simülasyonu (JVM gerekir) |
| `coupling <VTK> <STL>` | CFD basınç → FEA kuvvet eşlemesi |

## fea_runner.py — CalculiX FEA motoru

- `.inp` (C3D8R varsayılan), lineer/nonlineer statik. `ccx` gerekir.
- von Mises, deplasman, emniyet katsayısı (SF). `pipeline.py fea` bunu sarmalar.

## Yardımcılar

- `validation_gci.py` / `validation_yplus.py` — mesh-bağımsızlık (GCI) ve y⁺ kontrolü.
- `report_generator.py` / `vehicle_report.py` — figür (300 DPI) + Markdown rapor.
- GUI (görsel arayüz): `launcher.py` / `app_analyzer.py` (PySide6) — `auto_configure`
  ile aynı kararı GUI'siz verebildiğin için analiz mühendisi olarak gerekmez.
