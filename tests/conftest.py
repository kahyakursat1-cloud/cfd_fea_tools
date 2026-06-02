"""Pytest yapilandirmasi.

Modüller su an depo kökünde flat (Faz 4'te src/ paketine tasinacak). Testlerin
`import structural_loads` gibi çalışabilmesi için kökü sys.path'e ekliyoruz.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
