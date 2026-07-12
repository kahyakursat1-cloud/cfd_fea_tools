# LSR kampanyasi v2: cube/disk/ahmed_25 capalari - 4-seviye mesh + LSR kabul kapisi.
# NOT: bu dosya SALT-ASCII kalmali (PS 5.1 BOM'suz UTF-8'i ANSI okur; em-dash gibi
# cok-baytli karakterlerin son bayti cp1254'te tirnak sayilip parse'i kirar).
# Izleme: Get-Content kampanya_lsr.log -Tail 20
param([string]$Anchors = "cube,disk,ahmed_25")
$ErrorActionPreference = "Continue"
$root = "D:\bilsem_beyin\cfd_fea_tools"
Set-Location $root
$py = "C:\Python314\python.exe"
$log = Join-Path $root "kampanya_lsr.log"
$env:PYTHONIOENCODING = "utf-8"

Add-Type -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);' -Name KA2 -Namespace Win32
[Win32.KA2]::SetThreadExecutionState([uint32]2147483649) | Out-Null

function Log($m) {
    "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m | Out-File $log -Append -Encoding utf8
}

Log "=== LSR KAMPANYASI (v2, 4-seviye) BASLADI ==="
$sonuc = @()
foreach ($anchor in ($Anchors -split ",")) {
    $freeGB = [math]::Round((Get-PSDrive D).Free / 1GB, 1)
    if ($freeGB -lt 8) {
        Log ("SKIP {0} - disk {1} GB" -f $anchor, $freeGB)
        $sonuc += @{ad = $anchor; durum = "skip_disk"}
        continue
    }
    Log ("START {0} (disk {1} GB)" -f $anchor, $freeGB)
    $t0 = Get-Date
    $jlog = Join-Path $root ("kampanya_lsr_" + $anchor + ".log")
    $proc = Start-Process -FilePath $py -ArgumentList @("validate_pipeline.py", "--anchor", $anchor) `
        -WorkingDirectory $root -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $jlog -RedirectStandardError ($jlog + ".err")
    $dk = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
    Log ("END {0} exit={1} sure={2} dk" -f $anchor, $proc.ExitCode, $dk)
    $sonuc += @{ad = $anchor; exit = $proc.ExitCode; dakika = $dk}
}
$sonuc | ConvertTo-Json | Out-File (Join-Path $root "kampanya_lsr_summary.json") -Encoding utf8
if (Test-Path "$root\validation_band.json") {
    Log ("OLCULEN BAND: " + (Get-Content "$root\validation_band.json" -Raw).Replace("`n", " "))
} else {
    Log "Band yine olusmadi - kampanya_lsr_*.log icindeki LSR bloklarina bak"
}
[Win32.KA2]::SetThreadExecutionState([uint32]2147483648) | Out-Null
Log "=== BITTI ==="
