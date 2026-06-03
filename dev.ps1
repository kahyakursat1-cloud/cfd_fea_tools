# Geliştirme görev koşucusu — kullanım:  .\dev.ps1 <komut>
#   lint      ruff lint
#   test      hızlı testler (dış araç hariç — her zaman yeşil olmalı)
#   test-all  external golden dahil tüm testler (bu makinede solver'lar mevcutken)
#   cov       kapsam raporu
#   check     lint + test (commit öncesi)
#   verify    canlı pipeline doğrulama (compute-hafif aşamalar)
param([Parameter(Position=0)][string]$cmd = "check")

$ErrorActionPreference = "Stop"

switch ($cmd) {
    "lint"     { python -m ruff check . }
    "test"     { python -m pytest -m "not external and not slow and not gui" }
    "test-all" { python -m pytest }
    "cov"      { python -m pytest -m "not external" --cov --cov-report=term-missing }
    "check"    {
        python -m ruff check .
        if ($LASTEXITCODE -eq 0) { python -m pytest -m "not external and not slow and not gui" }
    }
    "verify"   {
        python pipeline.py loads
        python pipeline.py validate-fea
        python pipeline.py report
    }
    default    { Write-Host "Bilinmeyen komut: $cmd`nGecerli: lint test test-all cov check verify" }
}
