# Inside the Windows VM: Python (native ARM64), PIME 2.0 with its Python backend, and Claudish from the shared folder.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$shared = '\\host.lan\Data'
New-Item -ItemType Directory -Force C:\setup | Out-Null
"OS: $([Environment]::OSVersion.VersionString) $env:PROCESSOR_ARCHITECTURE"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  Invoke-WebRequest https://www.python.org/ftp/python/3.13.9/python-3.13.9-arm64.exe -OutFile C:\setup\python.exe
  Start-Process C:\setup\python.exe -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0' -Wait
}
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
"Python: $(python --version) $(python -c 'import platform; print(platform.machine())')"
$pime = "${env:ProgramFiles(x86)}\PIME"
# PIME's installer asks about the VC++ runtime in a dialog even with /S; install it silently first.
# On ARM64 it wants both the ARM64 and the x64 runtime, and runs the x64 one interactively.
foreach ($arch in 'arm64', 'x64') {
  Invoke-WebRequest "https://aka.ms/vs/17/release/vc_redist.$arch.exe" -OutFile "C:\setup\vc_redist.$arch.exe"
  Start-Process "C:\setup\vc_redist.$arch.exe" -ArgumentList '/install /quiet /norestart' -Wait
}
if (-not (Test-Path "$pime\python\textService.py")) {
  Invoke-WebRequest https://github.com/EasyIME/PIME/releases/download/v2.0.0-beta3/PIME-2.0.0-beta3-setup.exe -OutFile C:\setup\pime.exe
  Start-Process C:\setup\pime.exe -ArgumentList '/S' -Wait
}
"PIME: $(Get-ChildItem $pime -Directory | ForEach-Object Name)"
if (Test-Path C:\claudish) { Remove-Item -Recurse -Force C:\claudish }
Expand-Archive "$shared\claudish.zip" C:\claudish
$installed = "$pime\python\input_methods\claudish"
if (Test-Path $installed) { Remove-Item -Recurse -Force $installed }
& C:\claudish\platforms\windows\install.ps1
"Registered TSF profiles containing the Claudish GUID:"
Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\CTF\TIP' -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.PSChildName -eq '{EF97D106-1721-4466-A6B1-764987694B3C}' } | ForEach-Object { $_.Name }
