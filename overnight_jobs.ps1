# Gece kampanyasi: validasyon capalari (cube/sphere/ahmed_25) + roket mesh-GCI.
# Her is sirayla kosar, kendi loguna yazar; biri cokerse digerleri devam eder.
# Izleme: Get-Content overnight_validation.log -Tail 20
$ErrorActionPreference = "Continue"
$root = "D:\bilsem_beyin\cfd_fea_tools"
Set-Location $root
$py = "C:\Python314\python.exe"
$log = Join-Path $root "overnight_validation.log"
$env:PYTHONIOENCODING = "utf-8"

Add-Type -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);' -Name KA -Namespace Win32
[Win32.KA]::SetThreadExecutionState([uint32]2147483649) | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

function Log($m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    $line | Out-File $log -Append -Encoding utf8
}

Log "=== GECE KAMPANYASI BASLADI ==="
$jobs = @(
    @{ad = "anchor_cube";     args = @("validate_pipeline.py", "--anchor", "cube")},
    @{ad = "anchor_sphere";   args = @("validate_pipeline.py", "--anchor", "sphere")},
    @{ad = "anchor_ahmed_25"; args = @("validate_pipeline.py", "--anchor", "ahmed_25")},
    @{ad = "rocket_gci";      args = @("experiments\mesh_gci_campaign.py",
                                       "vehicle_runs\clean_rocket_fixed\clean_rocket_fixed_prep.stl",
                                       "--tip", "roket", "--hiz", "30")}
)
$sonuc = @()
foreach ($j in $jobs) {
    $freeGB = [math]::Round((Get-PSDrive D).Free / 1GB, 1)
    if ($freeGB -lt 8) {
        Log ("SKIP {0} - disk {1} GB < 8 GB esigi" -f $j.ad, $freeGB)
        $sonuc += @{ad = $j.ad; durum = "skip_disk"; disk_gb = $freeGB}
        continue
    }
    Log ("START {0} (disk {1} GB)" -f $j.ad, $freeGB)
    $t0 = Get-Date
    $jlog = Join-Path $root ("overnight_" + $j.ad + ".log")
    $jerr = Join-Path $root ("overnight_" + $j.ad + ".err.log")
    $proc = Start-Process -FilePath $py -ArgumentList $j.args -WorkingDirectory $root `
        -NoNewWindow -Wait -PassThru -RedirectStandardOutput $jlog -RedirectStandardError $jerr
    $dk = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
    Log ("END {0} exit={1} sure={2} dk" -f $j.ad, $proc.ExitCode, $dk)
    $sonuc += @{ad = $j.ad; exit = $proc.ExitCode; dakika = $dk}
}
$sonuc | ConvertTo-Json | Out-File (Join-Path $root "overnight_summary.json") -Encoding utf8
if (Test-Path "$root\validation_band.json") {
    Log ("OLCULEN BAND: " + (Get-Content "$root\validation_band.json" -Raw).Replace("`n", " "))
} else {
    Log "UYARI: validation_band.json olusmadi (hicbir capa GCI kapisini gecemedi olabilir)"
}
[Win32.KA]::SetThreadExecutionState([uint32]2147483648) | Out-Null
Log "=== TUM ISLER BITTI ==="
