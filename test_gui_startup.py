#!/usr/bin/env python3
"""
GUI Startup Test — Check if app_parametric.py can initialize
"""

import sys
from pathlib import Path

print("=" * 70)
print("GUI STARTUP TEST — bilsem_beyin")
print("=" * 70)

# Check PySide6
print("\n1. PySide6 kontrolu...")
try:
    from PySide6.QtWidgets import QApplication, QMainWindow
    from PySide6.QtCore import Qt
    print("   [OK] PySide6 imports successful")
except ImportError as e:
    print(f"   [HATA] PySide6 import failed: {e}")
    sys.exit(1)

# Check core modules
print("\n2. Core moduller kontrolu...")
modules_to_check = [
    'aircraft_geometry',
    'mesh_generator',
    'simulation_runner',
    'fea_runner',
    'scanner_gui_module',
]

for mod in modules_to_check:
    try:
        __import__(mod)
        print(f"   [OK] {mod}")
    except ImportError as e:
        print(f"   [HATA] {mod}: {e}")

# Try to create QApplication (GUI framework)
print("\n3. QApplication test...")
try:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    print("   [OK] QApplication created successfully")
except Exception as e:
    print(f"   [HATA] QApplication failed: {e}")
    sys.exit(1)

# Try importing main app
print("\n4. app_parametric.py kontrolu...")
try:
    # Set PYTHONPATH
    sys.path.insert(0, str(Path(__file__).parent))

    # Import (will initialize GUI classes but not run event loop)
    from app_parametric import ParametricAnalysisTool
    print("   [OK] ParametricAnalysisTool class loaded")
except ImportError as e:
    print(f"   [HATA] app_parametric import failed: {e}")
    sys.exit(1)

# Try creating main window
print("\n5. Main window test...")
try:
    from app_parametric import ParametricAnalysisTool
    window = ParametricAnalysisTool()
    print("   [OK] Main window instantiated")
    print("   [OK] Window title: " + window.windowTitle())
except Exception as e:
    print(f"   [HATA] Window creation failed: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("SONUC: GUI BASLATILABILIR")
print("=" * 70)
print("\nKomut: python app_parametric.py")
print("Bu, 6 tabl?? GUI'yi acak:")
print("  1. Konfigúrasyon")
print("  2. Mesh")
print("  3. Simulasyon (CFD)")
print("  4. Sonuclar")
print("  5. Scanner (3D Tarama)")
print("  6. FEA (Statik/Frequency/Buckling)")
print("\n" + "=" * 70)
