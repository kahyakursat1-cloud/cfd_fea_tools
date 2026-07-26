"""Proje-geneli mesh kalite ve yakınsama eşikleri — kök erişim noktası.

Sayıların TEK KAYNAĞI `analysis/thresholds.py`; eşiği uygulayan kapı (mesh_quality_gate,
fvSolution residualControl) orada olduğu için değerler kanonik katmanda tutulur. Bu modül
kök seviyeden (vehicle_pipeline, vehicle_report) erişim için yeniden dışa aktarır —
bağımlılık yönü kök -> paket, tersi değil.
"""

from analysis.thresholds import (
    ASPECT_LIMIT,
    NONORTHO_LIMIT,
    NONORTHO_REJECT,
    RESIDUAL_TARGET,
    SKEW_LIMIT,
    SKEW_REJECT,
)

__all__ = ["ASPECT_LIMIT", "NONORTHO_LIMIT", "NONORTHO_REJECT",
           "RESIDUAL_TARGET", "SKEW_LIMIT", "SKEW_REJECT"]
