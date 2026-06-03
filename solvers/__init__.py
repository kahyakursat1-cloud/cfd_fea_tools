"""
Solvers Module — CFD, FEA, Mesh oluşturma wrappers

Submodules:
  - gmsh_wrapper: GMSH mesh generation
  - openfoam_wrapper: OpenFOAM CFD simulation
  - calculix_wrapper: CalculiX FEA simulation

İKİNCİL wrapper katmanı (bkz. docs/adr/0001-kanonik-mimari.md). Gerçek-solver
kanonik yolları: ``pipeline.py`` (uçak V&V) ve ``analysis/`` (genel sıfırdan).
Bu paketi entegrasyon smoke testleri (test_integration — mock solver'larla,
full_integration_test) tüketir. Yeni gerçek-solver kodu için pipeline/analysis tercih et.
"""

from solvers.calculix_wrapper import CalculiXRunner
from solvers.gmsh_wrapper import GMSHMeshGenerator
from solvers.openfoam_wrapper import OpenFOAMRunner

__all__ = [
    'GMSHMeshGenerator',
    'OpenFOAMRunner',
    'CalculiXRunner',
]
