# Diagnostic: "draft" + Ctrl+A in Edge, then hold 6 s so the host can look at the screen.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process msedge -ArgumentList 'data:text/html,<title>claudish</title><textarea%20id=t%20autofocus></textarea>', '--no-first-run'
Start-Sleep 4
$window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
[Keys]::Focus($window.MainWindowHandle) | Out-Null; Start-Sleep 1
[Keys]::Type('draft'); Start-Sleep -Milliseconds 400
[Keys]::Press(0x41, 0x11)
"pressed at $(Get-Date -Format HH:mm:ss.fff)"
Start-Sleep 6
Stop-Process $service -Force; Stop-Process -Name msedge -Force
