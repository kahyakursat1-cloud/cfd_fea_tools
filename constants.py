"""Proje-geneli mesh kalite ve yakınsama eşikleri — TEK KAYNAK.

CLAUDE.md proje kuralı: maxNonOrthogonality < 70, maxSkewness < 4, residuals < 1e-4.
Bu eşikler birden çok modülde (vehicle_pipeline, vehicle_report) kullanılır; burada
tutulur ki çatallaşmasın.
"""

RESIDUAL_TARGET = 1e-4   # yakınsama kriteri (OpenFOAM residuals)
NONORTHO_LIMIT = 70.0    # maxNonOrthogonality eşiği (°)
SKEW_LIMIT = 4.0         # maxSkewness eşiği
