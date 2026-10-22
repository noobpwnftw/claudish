# Test-VM job runner: executes \\host.lan\Data\jobs\*.ps1 in this desktop session, writes output to results\.
$shared = "\\host.lan\Data"
while (-not (Test-Path $shared)) { Start-Sleep 5 }
foreach ($d in "jobs", "results", "done") { New-Item -ItemType Directory -Force -Path "$shared\$d" | Out-Null }
"ready $(Get-Date -Format o) $([System.Environment]::OSVersion.VersionString) $env:PROCESSOR_ARCHITECTURE" |
  Out-File "$shared\results\agent-ready.txt" -Encoding utf8
while ($true) {
  Get-ChildItem "$shared\jobs\*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
    $out = "$shared\results\$($_.BaseName).txt"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $_.FullName *> "$out.partial"
    "exit=$LASTEXITCODE" | Out-File "$out.partial" -Append -Encoding utf8
    Move-Item -Force "$out.partial" $out
    Move-Item -Force $_.FullName "$shared\done\"
  }
  Start-Sleep 2
}
