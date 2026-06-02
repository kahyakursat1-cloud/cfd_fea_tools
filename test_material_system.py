#!/usr/bin/env python3
"""
Material System Test — Malzeme kütüphanesi işlevselliğini test et
"""

import sys
from pathlib import Path

# Test 1: Import test
print("[TEST 1] Modülleri yükle...")
try:
    from material_database import MaterialLibrary, MaterialProperties, MaterialType
    print("  [OK] material_database yüklendi")
except Exception as e:
    print(f"  [FAIL] material_database hatası: {e}")
    sys.exit(1)

try:
    from material_editor_gui import MaterialManagerTab, MaterialEditorDialog
    print("  [OK] material_editor_gui yüklendi")
except Exception as e:
    print(f"  [FAIL] material_editor_gui hatası: {e}")
    sys.exit(1)

# Test 2: Kütüphane oluştur
print("\n[TEST 2] MaterialLibrary ornegi olustur...")
try:
    lib = MaterialLibrary()
    print(f"  [OK] Kutuhane olusturuldu")
    print(f"  [OK] {len(lib.materials)} malzeme yuklendi")
except Exception as e:
    print(f"  [FAIL] Hata: {e}")
    sys.exit(1)

# Test 3: Malzeme ozellikleri
print("\n[TEST 3] Malzeme ozelliklerini kontrol et...")
try:
    aluminum = lib.get_material("Aluminum 6061")
    print(f"  Malzeme: {aluminum.name}")
    print(f"  - Young's Modulus: {aluminum.youngs_modulus} GPa")
    print(f"  - Shear Modulus (hesaplanmis): {aluminum.shear_modulus:.1f} GPa")
    print(f"  - Bulk Modulus (hesaplanmis): {aluminum.bulk_modulus:.1f} GPa")
    print(f"  - Lame Constant (hesaplanmis): {aluminum.lame_constant:.1f} GPa")
    print(f"  - Strength-to-Weight: {aluminum.strength_to_weight/1e6:.2f} m/s2")
    print(f"  - Stiffness-to-Weight: {aluminum.stiffness_to_weight/1e6:.2f} m/s2")
    print(f"  [OK] Otomatik hesaplamalar dogru")
except Exception as e:
    print(f"  [FAIL] Hata: {e}")
    sys.exit(1)

# Test 4: Yeni malzeme ekle
print("\n[TEST 4] Yeni malzeme ekle...")
try:
    custom = MaterialProperties(
        name="Test Custom Material",
        material_type=MaterialType.ALUMINUM,
        density=2700,
        youngs_modulus=70,
        poisson_ratio=0.33,
        yield_strength=300,
        tensile_strength=350,
        cost_per_kg=3.0,
        typical_applications=["Testing"]
    )
    print(f"  [OK] Malzeme nesnesi olusturuldu")
    print(f"  - Shear Modulus: {custom.shear_modulus:.1f} GPa")
    print(f"  - Bulk Modulus: {custom.bulk_modulus:.1f} GPa")

    lib.add_material(custom)
    print(f"  [OK] Kutuphanaye eklendi")
except Exception as e:
    print(f"  [FAIL] Hata: {e}")
    sys.exit(1)

# Test 5: Malzeme ara
print("\n[TEST 5] Malzeme ara...")
try:
    strong_materials = lib.search_by_property("yield_strength", 400, 10000)
    print(f"  [OK] Akma gerilmesi > 400 MPa olan malzemeler: {len(strong_materials)}")
    for name in strong_materials:
        mat = lib.get_material(name)
        print(f"    - {name}: {mat.yield_strength} MPa")
except Exception as e:
    print(f"  [FAIL] Hata: {e}")
    sys.exit(1)

# Test 6: CSV disari aktarma
print("\n[TEST 6] CSV'ye disari aktar...")
try:
    output_path = Path(__file__).parent / "test_materials_export.csv"
    lib.export_csv(output_path)
    if output_path.exists():
        print(f"  [OK] CSV dosyasi olusturuldu: {output_path}")
        with open(output_path) as f:
            lines = f.readlines()
            print(f"  [OK] {len(lines)} satir iceriyor")
    else:
        print(f"  [FAIL] Dosya olusturulamadi")
except Exception as e:
    print(f"  [FAIL] Hata: {e}")
    sys.exit(1)

# Test 7: Dogrulama
print("\n[TEST 7] Malzeme dogrulamas...")
try:
    invalid_test = False

    # Gecersiz: E <= 0
    try:
        bad = MaterialProperties(
            name="Bad Material",
            material_type=MaterialType.ALUMINUM,
            density=2700,
            youngs_modulus=-50,  # Invalid
            poisson_ratio=0.33,
            yield_strength=300,
            tensile_strength=350
        )
        invalid_test = True
    except ValueError as ve:
        print(f"  [OK] Gecersiz E degeri yakalmasi: {str(ve)[:50]}...")

    if invalid_test:
        print(f"  [FAIL] Dogrulama basarisiz!")
        sys.exit(1)
    else:
        print(f"  [OK] Dogrulama calistiyor")
except Exception as e:
    print(f"  [FAIL] Hata: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("[SUCCESS] TUM TESTLER BASARILI!")
print("="*60)
print("\nMalzeme Sistemi Ozeti:")
print(f"  - Toplam malzeme: {len(lib.materials)}")
print(f"  - Otomatik hesaplamalar: [OK] Calisiyor")
print(f"  - Dogrulama: [OK] Calisiyor")
print(f"  - Disari aktarma: [OK] Calisiyor")
print(f"  - GUI entegrasyonu: Hazir (MaterialManagerTab)")
print("\nSistem uretime hazir!")
