# Diagnostic: restart PIME with CLAUDISH_KEYLOG, type "draft" + Ctrl+A in Edge, and show the key routing.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
$pime = "${env:ProgramFiles(x86)}\PIME"; $log = 'C:\setup\keylog.txt'
Remove-Item $log -ErrorAction SilentlyContinue
Get-Process PIMELauncher, python -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $service.Id } | Stop-Process -Force
$env:CLAUDISH_KEYLOG = $log
Start-Process "$pime\PIMELauncher.exe" -WorkingDirectory $pime; Start-Sleep 2
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process msedge -ArgumentList 'data:text/html,<title>claudish</title><textarea%20id=t%20autofocus></textarea>', '--no-first-run'
Start-Sleep 4
$window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
[Keys]::Focus($window.MainWindowHandle) | Out-Null; Start-Sleep 1
[Keys]::Type('draft'); Start-Sleep -Milliseconds 400
Add-Content $log '--- Ctrl+A'
[Keys]::Press(0x41, 0x11); Start-Sleep -Milliseconds 800
Add-Content $log '--- Escape (control)'
[Keys]::Type('xy'); [Keys]::Press(0x1B); Start-Sleep -Milliseconds 500
Get-Content $log
Stop-Process $service -Force; Stop-Process -Name msedge -Force
