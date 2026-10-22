# Hypothesis: the x86 PIMELauncher finds an ARM64 vcruntime140.dll on PATH (0xc000007b) without the x86 runtime.
$pime = "${env:ProgramFiles(x86)}\PIME"
"x86 vcruntime in SysWOW64 before: $(Test-Path $env:WINDIR\SysWOW64\vcruntime140.dll)"
"vcruntime140.dll on PATH: $((Get-Command vcruntime140.dll -All -ErrorAction SilentlyContinue | ForEach-Object Source) -join ', ')"
Invoke-WebRequest https://aka.ms/vs/17/release/vc_redist.x86.exe -OutFile C:\setup\vc_redist.x86.exe
Start-Process C:\setup\vc_redist.x86.exe -ArgumentList '/install /quiet /norestart' -Wait
"x86 vcruntime in SysWOW64 after: $(Test-Path $env:WINDIR\SysWOW64\vcruntime140.dll)"
Get-Process PIMELauncher -ErrorAction SilentlyContinue | Stop-Process -Force
$log = "$env:TEMP\pime-launcher.log"; Remove-Item $log -ErrorAction SilentlyContinue
Start-Process "$pime\PIMELauncher.exe" -ArgumentList "/log-file=$log" -WorkingDirectory $pime; Start-Sleep 3
"launcher log exists: $(Test-Path $log)"; Get-Content $log -ErrorAction SilentlyContinue | Select-Object -First 5
