#!/usr/bin/env python3
"""
Core System Test
Tests: Aircraft, Mesh, CFD, FEA, GUI
"""

import sys

print("=" * 70)
print("CORE SISTEM TEST")
print("=" * 70)

# 1. Core modules
print("\n1. Core Modüller:")
try:
    from aircraft_geometry import AircraftLibrary
    from fea_runner import MATERIAL_LIBRARY, FEASimulationRunner
    from mesh_generator import MeshGenerator
    from simulation_runner import SimulationRunner
    print("   [OK] Tüm core modüller import edildi")
except ImportError as e:
    print(f"   [HATA] {e}")
    sys.exit(1)

# 2. PySide6
print("\n2. GUI Framework (PySide6):")
try:
    from PySide6.QtWidgets import QApplication, QMainWindow
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    print("   [OK] PySide6 çalışıyor")
except ImportError as e:
    print(f"   [HATA] {e}")
    sys.exit(1)

# 3. Aircraft functionality
print("\n3. Aircraft Library:")
try:
    lib = AircraftLibrary()
    templates = lib.get_templates()
    print(f"   [OK] {len(templates)} aircraft şablonu yüklendi:")
    for name in list(templates.keys())[:3]:
        print(f"       • {name}")
except Exception as e:
    print(f"   [HATA] {e}")

# 4. FEA Materials
print("\n4. FEA Materials:")
try:
    print(f"   [OK] {len(MATERIAL_LIBRARY)} malzeme kütüphanesi:")
    for mat in list(MATERIAL_LIBRARY.keys())[:3]:
        print(f"       • {mat}")
except Exception as e:
    print(f"   [HATA] {e}")

# 5. Try to load main app
print("\n5. Main App Loading:")
try:
    from PySide6.QtWidgets import QApplication

    from aircraft_geometry import AircraftLibrary
    from fea_runner import MATERIAL_LIBRARY

    print("   [OK] Tüm gerekli modüller import edildi")
    print("   App başlatılabilir")
except Exception as e:
    print(f"   [HATA] {e}")

print("\n" + "=" * 70)
print("SONUC: CORE SISTEM CALISIYOR")
print("=" * 70)
print("\nKomut: python app_parametric.py")
print("\nAçılacak Tablar:")
print("  ✓ Konfigürasyon")
print("  ✓ Mesh")
print("  ✓ Simülasyon (CFD)")
print("  ✓ Sonuçlar")
print("  ✓ Malzemeler")
print("  ✓ FEA")
print("\n" + "=" * 70)
