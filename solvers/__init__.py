"""
Solvers Module — CFD, FEA, Mesh oluşturma wrappers

Submodules:
  - gmsh_wrapper: GMSH mesh generation
  - openfoam_wrapper: OpenFOAM CFD simulation
  - calculix_wrapper: CalculiX FEA simulation

.. deprecated::
    Eski kuşak #2 (bkz. docs/adr/0001-kanonik-mimari.md). Kanonik path
    ``simulation_runner`` / ``fea_runner`` (pipeline.py). Tüketici: main.py (yetim) +
    test_integration / full_integration_test. Yeni kod buraya bağımlanmamalı.
"""

from solvers.calculix_wrapper import CalculiXRunner
from solvers.gmsh_wrapper import GMSHMeshGenerator
from solvers.openfoam_wrapper import OpenFOAMRunner

__all__ = [
    'GMSHMeshGenerator',
    'OpenFOAMRunner',
    'CalculiXRunner',
]
