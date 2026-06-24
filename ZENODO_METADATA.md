# Zenodo Deposit Metadata — cfdfea-tools (Paper 1 reproducibility DOI)

> Yükleme dosyası: `cfdfea-tools-snapshot.zip` (git archive HEAD, 236 dosya, ~2.9 MB açık).
> **PUBLISH'e basMADAN önce:** ortak-yazar onayı (VKI/TU Delft), grant no, paper DOI teyidi.

| Alan | Değer |
|------|-------|
| **Upload type** | Software |
| **Title** | cfdfea-tools: An open-source OpenFOAM+CalculiX pipeline with a guarded, self-classifying verification-and-validation layer |
| **Authors** | Kahya, Kürşat (BİLSEM Aviation & Space) [ORCID: TODO]; *[TODO: VKI / TU Delft ortak-yazarlar — onay sonrası]* |
| **Description** | Open-source, reproducible computer-aided engineering pipeline coupling OpenFOAM (CFD) and CalculiX (FEA) behind a single automated driver with a *guarded, self-classifying* verification-and-validation (V&V) layer. Every output is automatically assigned a reliability class (design-grade / trend-grade / out-of-envelope); a non-overridable asymptotic-range guard withholds the Grid Convergence Index outside the asymptotic range; a force-coefficient plateau criterion supersedes residual-only convergence; and a far-field/surface-pressure cross-check surfaces drag inconsistency. This archive is the software accompanying the paper "Guarded Automation for Trustworthy CAE" and reproduces its verification (six closed-form FEA benchmarks), validation (NACA0012 vs NASA Ladson; NASA TMR reference-grid drag GCI; supersonic sphere vs Charters–Thomas), and the silent-failure detection assay. |
| **Version** | 1.0.0 |
| **License** | MIT |
| **Keywords** | verification and validation; uncertainty classification; trustworthy automation; silent-failure detection; Grid Convergence Index; coupled CFD/FEA; OpenFOAM; CalculiX; open-source CAE; reproducibility |
| **Language** | English |
| **Related identifiers** | "is supplement to" → Paper 1 DOI [TODO]; "is derived from" → GitHub repo URL [TODO public repo] |
| **Grant / Funding** | Erasmus+ KA220-SCH — AERO-ARCHITECT+ [grant no: TODO] |
| **Publication date** | (Zenodo otomatik) |

## Açık [TODO] (publish-öncesi, honest-engineering — uydurma yok)
- [ ] ORCID (yazar)
- [ ] Ortak-yazar listesi + VKI/TU Delft onayı
- [ ] Erasmus+ grant numarası
- [ ] Paper 1 DOI (dergi kabul/preprint sonrası — yoksa "is supplement to" boş bırakılır)
- [ ] Public GitHub repo URL (Zenodo-GitHub entegrasyonu tercih edilirse manuel zip yerine release-tag)
