"""Mesh kalite ve yakınsama eşikleri — TEK KAYNAK.

CLAUDE.md proje kuralı: maxNonOrthogonality < 70, maxSkewness < 4, residuals < 1e-4.
Eşikler kanonik katmanda (analysis/) tutulur çünkü onları UYGULAYAN kapı burada
(`openfoam_runner.mesh_quality_gate` + fvSolution residualControl). Kök `constants.py`
bu modülü yeniden dışa aktarır; mevcut `from constants import ...` çağrıları çalışmaya
devam eder ve bağımlılık yönü kök -> paket kalır.

İki kademe:
  *_LIMIT   — proje konvansiyonu; aşılırsa 'warn' (koşabilir, sonuç şüpheli)
  *_REJECT  — diverjans deneyimi; aşılırsa 'reject' (çözücü neredeyse kesin patlar)
"""

RESIDUAL_TARGET = 1e-4   # yakınsama kriteri (OpenFOAM residualControl)

NONORTHO_LIMIT = 70.0    # maxNonOrthogonality eşiği (°)
NONORTHO_REJECT = 75.0

SKEW_LIMIT = 4.0         # maxSkewness eşiği
SKEW_REJECT = 6.0

ASPECT_LIMIT = 1e5       # maxAspectRatio — üstü uyarı (prism layer patolojisi)
