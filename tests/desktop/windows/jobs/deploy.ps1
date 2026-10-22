# Deploy the synced checkout (vm.sh sync) into PIME and restart its backend so the new code loads.
$ErrorActionPreference = 'Stop'
$pime = "${env:ProgramFiles(x86)}\PIME"
Get-Process PIMELauncher, python, Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path C:\claudish) { Remove-Item -Recurse -Force C:\claudish }
Expand-Archive \\host.lan\Data\claudish.zip C:\claudish
$installed = "$pime\python\input_methods\claudish"
if (Test-Path $installed) { Remove-Item -Recurse -Force $installed }
& C:\claudish\platforms\windows\install.ps1 | Out-Null
Start-Process "$pime\PIMELauncher.exe" -WorkingDirectory $pime; Start-Sleep 2
"deployed; launcher running: $([bool](Get-Process PIMELauncher -ErrorAction SilentlyContinue))"
