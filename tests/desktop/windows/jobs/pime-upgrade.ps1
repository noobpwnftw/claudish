# Install the PIME build in \\host.lan\Data\pime\pime-master.exe over the current one, then reinstall Claudish.
$ErrorActionPreference = 'Stop'
$pime = "${env:ProgramFiles(x86)}\PIME"
Get-Process PIMELauncher, python -ErrorAction SilentlyContinue | Stop-Process -Force
Copy-Item \\host.lan\Data\pime\pime-master.exe C:\setup\pime-master.exe -Force
$p = Start-Process C:\setup\pime-master.exe -ArgumentList '/S' -Wait -PassThru
"installer exit: $($p.ExitCode)"
"arm64 folder:"; Get-ChildItem "$pime\arm64" | ForEach-Object { "  $($_.Name) $($_.Length)" }
$installed = "$pime\python\input_methods\claudish"
if (Test-Path $installed) { Remove-Item -Recurse -Force $installed }
& C:\claudish\platforms\windows\install.ps1
Start-Process "$pime\PIMELauncher.exe" -WorkingDirectory $pime; Start-Sleep 2
"launcher running: $([bool](Get-Process PIMELauncher -ErrorAction SilentlyContinue))"
