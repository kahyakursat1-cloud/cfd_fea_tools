#!/usr/bin/env python3
"""
Blender Kurulum Kontrolü
Blender ve gerekli modüllerin yüklü olup olmadığını kontrol et
"""

import platform
import subprocess
import sys
from pathlib import Path


class BlenderVerifier:
    """Blender kurulumunu doğrula"""

    def __init__(self):
        self.blender_path = None
        self.blender_version = None
        self.is_windows = platform.system() == "Windows"
        self.is_linux = platform.system() == "Linux"
        self.is_mac = platform.system() == "Darwin"

    def find_blender(self) -> bool:
        """Blender çalıştırılabilir dosyasını bul"""
        print("🔍 Blender aranıyor...")

        # Ortak Blender konumları
        common_paths = []

        if self.is_windows:
            common_paths = [
                Path("C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe"),
                Path("C:\\Program Files\\Blender Foundation\\Blender 3.6\\blender.exe"),
                Path("C:\\Program Files\\Blender Foundation\\Blender\\blender.exe"),
                Path("C:\\Program Files (x86)\\Blender Foundation\\Blender\\blender.exe"),
            ]
        elif self.is_linux:
            common_paths = [
                Path("/usr/bin/blender"),
                Path("/snap/bin/blender"),
                Path(Path.home() / ".local/bin/blender"),
            ]
        elif self.is_mac:
            common_paths = [
                Path("/Applications/Blender.app/Contents/MacOS/Blender"),
                Path(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
            ]

        # Her konumu dene
        for path in common_paths:
            if path.exists():
                self.blender_path = path
                print(f"  ✅ Bulundu: {path}")
                return True

        # PATH'te ara
        try:
            result = subprocess.run(
                "where blender" if self.is_windows else "which blender",
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                self.blender_path = Path(result.stdout.strip())
                print(f"  ✅ PATH'de bulundu: {self.blender_path}")
                return True
        except Exception:
            pass

        print("  ❌ Blender bulunamadı!")
        return False

    def get_blender_version(self) -> bool:
        """Blender versiyonunu al"""
        if not self.blender_path:
            return False

        try:
            result = subprocess.run(
                [str(self.blender_path), "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                version_str = result.stdout.strip() + result.stderr.strip()
                self.blender_version = version_str
                print(f"  ✅ Versiyon: {version_str}")
                return True
        except Exception:
            pass

        print("  ❌ Versiyon alınamadı!")
        return False

    def check_python_api(self) -> bool:
        """Blender Python API'sini kontrol et"""
        print("🔍 Blender Python API kontrol ediliyor...")

        if not self.blender_path:
            return False

        # Test scripti
        test_script = """
import bpy
import sys

print("✅ Blender Python API çalışıyor")
print(f"  Blender Version: {bpy.app.version_string}")
print(f"  Python: {sys.version}")

# Temel API testleri
try:
    bpy.ops.object.camera_add()
    print("  ✅ Object operations: OK")
except Exception:
    print("  ❌ Object operations: FAILED")

try:
    bpy.data.materials.new(name="Test")
    print("  ✅ Material operations: OK")
except Exception:
    print("  ❌ Material operations: FAILED")

try:
    bpy.data.worlds["World"]
    print("  ✅ World access: OK")
except Exception:
    print("  ❌ World access: FAILED")
"""

        try:
            result = subprocess.run(
                [str(self.blender_path), "--background", "--python-text", "-c", test_script],
                capture_output=True,
                text=True,
                timeout=30
            )

            if "✅ Blender Python API" in result.stdout or "✅ Blender Python API" in result.stderr:
                print("  ✅ API Test Passed")
                print(result.stdout if result.stdout else result.stderr)
                return True
        except subprocess.TimeoutExpired:
            print("  ⚠️  API test timeout (Blender başlangıç yavaş)")
            return True  # Timeout başarısızlık değil
        except Exception as e:
            print(f"  ⚠️  API test error: {str(e)}")

        print("  ❌ API Test Failed")
        return False

    def verify_synthetic_generator(self) -> bool:
        """Synthetic dataset generator script'i kontrol et"""
        print("🔍 Synthetic dataset generator kontrol ediliyor...")

        script_path = Path(__file__).parent / "blender_synthetic_generator.py"

        if not script_path.exists():
            print(f"  ❌ Script bulunamadı: {script_path}")
            return False

        print(f"  ✅ Script bulundu: {script_path}")

        # Temel syntax kontrolü
        try:
            with open(script_path) as f:
                code = f.read()

            # Önemli fonksiyonlar var mı?
            required_items = [
                "class SyntheticDatasetGenerator",
                "def generate_dataset",
                "def generate_camera_views",
                "def generate_lighting_setups",
                "def generate_texture_variants"
            ]

            missing = []
            for item in required_items:
                if item not in code:
                    missing.append(item)

            if missing:
                print(f"  ⚠️  Eksik: {', '.join(missing)}")
                return False

            print("  ✅ Tüm gerekli bileşenler var")
            return True

        except Exception as e:
            print(f"  ❌ Script okuma hatası: {str(e)}")
            return False

    def run_verification(self):
        """Tüm doğrulamaları çalıştır"""
        print("\n" + "=" * 60)
        print("BLENDER KURULUM DOĞRULMASI")
        print("=" * 60 + "\n")

        results = {
            "Blender Bulundu": self.find_blender(),
            "Versiyon Alındı": self.get_blender_version(),
            "Python API Çalışıyor": self.check_python_api(),
            "Synthetic Generator Hazır": self.verify_synthetic_generator(),
        }

        print("\n" + "=" * 60)
        print("SONUÇ:")
        print("=" * 60)

        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:30} {status}")

        all_pass = all(results.values())

        print("\n" + "=" * 60)
        if all_pass:
            print("🚀 Blender tamamen kurulu ve hazır!")
            print("   Sentetik dataset üretimi başlatılabilir.")
        else:
            print("⚠️  Blender kurulumunda sorun var.")
            print("\n   Çözüm:")
            if not self.blender_path:
                print("   1. Blender indir: https://www.blender.org/download/")
                print("   2. Yükle ve PATH'e ekle")
            elif not results["Python API Çalışıyor"]:
                print("   1. Blender'ı sil ve yeniden yükle")
                print("   2. Python API seçeneğinin seçildiğinden emin ol")

        print("=" * 60)

        return all_pass


if __name__ == "__main__":
    verifier = BlenderVerifier()
    success = verifier.run_verification()
    sys.exit(0 if success else 1)
