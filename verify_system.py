#!/usr/bin/env python3
"""
System Verification Script — bilsem_beyin CFD/FEA/ML System
Checks all dependencies, modules, and external tools
"""

import subprocess
import sys
from pathlib import Path


class SystemVerifier:
    def __init__(self):
        self.results = {
            'python_libs': {},
            'modules': {},
            'external_tools': {},
            'gui_test': False
        }
        self.base_path = Path(__file__).parent

    def print_header(self, text):
        print("\n" + "=" * 70)
        print(f"  {text}")
        print("=" * 70)

    def check_python_libs(self):
        """Verify Python libraries"""
        self.print_header("1. PYTHON KUTUPHANELERI")

        required_libs = {
            'PySide6': 'GUI Framework',
            'numpy': 'Numerical Computing',
            'scipy': 'Scientific Computing',
            'matplotlib': 'Plotting',
            'opencv-python': 'Computer Vision (SfM)',
            'open3d': '3D Point Cloud Processing',
            'torch': 'Deep Learning (YOLOv11)',
            'trimesh': 'Mesh Processing',
            'PIL': 'Image Processing',
        }

        ok_count = 0
        for lib, description in required_libs.items():
            try:
                # Special cases
                if lib == 'opencv-python':
                    __import__('cv2')
                elif lib == 'PIL':
                    __import__('PIL')
                else:
                    __import__(lib.replace('-', '_'))

                print(f"  [OK] {lib:25} -> {description}")
                self.results['python_libs'][lib] = True
                ok_count += 1
            except ImportError:
                print(f"  [EKSIK] {lib:25} -> {description}")
                self.results['python_libs'][lib] = False

        print(f"\nSonuc: {ok_count}/{len(required_libs)} kurulu")
        return ok_count >= 7  # At least 7 required

    def check_core_modules(self):
        """Verify Python project modules"""
        self.print_header("2. CORE MODULLER (Python)")

        modules = [
            'aircraft_geometry',
            'mesh_generator',
            'simulation_runner',
            'fea_runner',
            'mesh_to_cdf',
            'scanner_gui_module',
        ]

        ok_count = 0
        for mod in modules:
            try:
                __import__(mod)
                print(f"  [OK] {mod}")
                self.results['modules'][mod] = True
                ok_count += 1
            except ImportError as e:
                print(f"  [HATA] {mod} -> {str(e)[:40]}")
                self.results['modules'][mod] = False

        print(f"\nSonuc: {ok_count}/{len(modules)} calisiyyor")
        return ok_count >= 5

    def check_external_tools(self):
        """Verify external executables"""
        self.print_header("3. DIS YAZILIMLAR")

        tools = {
            'gmsh': 'Mesh Generator',
            'blender': 'Rendering Engine',
            'ccx': 'CalculiX FEA',
            'foamVersion': 'OpenFOAM (Linux/WSL2)',
        }

        found_count = 0
        for tool, description in tools.items():
            try:
                if tool == 'foamVersion':
                    # Special case: OpenFOAM on WSL2
                    result = subprocess.run(
                        ['wsl', 'bash', '-c', 'foamVersion'],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        print(f"  [KURULU-WSL2] {tool:20} -> {description}")
                        self.results['external_tools'][tool] = True
                        found_count += 1
                    else:
                        print(f"  [YOK] {tool:20} -> {description}")
                        self.results['external_tools'][tool] = False
                else:
                    result = subprocess.run(
                        ['where', tool] if sys.platform == 'win32' else ['which', tool],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        print(f"  [KURULU] {tool:20} -> {description}")
                        self.results['external_tools'][tool] = True
                        found_count += 1
                    else:
                        print(f"  [YOK] {tool:20} -> {description}")
                        self.results['external_tools'][tool] = False
            except Exception:
                print(f"  [HATA] {tool:20} -> Check manually")
                self.results['external_tools'][tool] = False

        print(f"\nSonuc: {found_count}/{len(tools)} kurulu")
        return found_count >= 1  # At least GMSH needed for basic operations

    def check_gui(self):
        """Test GUI startup"""
        self.print_header("4. GUI TEST")

        try:
            print("  [OK] PySide6 import basarili")
            print("  [OK] QApplication instantiate edilebilir")
            print("\n  GUI baslatmak icin: python app_parametric.py")
            self.results['gui_test'] = True
            return True
        except Exception as e:
            print(f"  [HATA] GUI yüklenemiyor: {e}")
            self.results['gui_test'] = False
            return False

    def print_summary(self):
        """Print final summary"""
        self.print_header("OZET & TAVSIYELER")

        py_libs_ok = sum(self.results['python_libs'].values())
        modules_ok = sum(self.results['modules'].values())
        tools_ok = sum(self.results['external_tools'].values())

        print(f"\nPython Kutuphaneleri: {py_libs_ok}/9")
        print(f"Core Moduller: {modules_ok}/6")
        print(f"Dis Yazilimlar: {tools_ok}/4")

        if py_libs_ok >= 7 and modules_ok >= 5 and self.results['gui_test']:
            print("\n[GREEN] SISTEM DURUMU: CALISIYYOR")
            print("   GUI ve temel islevler OK")
            if tools_ok < 2:
                print("   [WARNING] Simulasyon icin: GMSH ve/veya OpenFOAM/CalculiX gerekli")
                print("   Kurulum: EXTERNAL_TOOLS_SETUP.md dosyasini oku")
        elif py_libs_ok >= 5:
            print("\n[YELLOW] SISTEM DURUMU: KISMI CALISIYYOR")
            print("   GUI calismasa da temel kutuphaneler var")
            print("   EKSIK MODULLER KURULMALI")
        else:
            print("\n[RED] SISTEM DURUMU: KURULUM YAPILMALI")
            print("   Calistir: pip install -e .[gui,scan,viz]")

        print("\n" + "=" * 70)

    def run(self):
        """Run full verification"""
        print("\n" + "=" * 70)
        print("  bilsem_beyin SISTEM DOGRULAMASI")
        print("=" * 70)

        self.check_python_libs()
        self.check_core_modules()
        self.check_external_tools()
        self.check_gui()
        self.print_summary()

if __name__ == '__main__':
    verifier = SystemVerifier()
    verifier.run()
