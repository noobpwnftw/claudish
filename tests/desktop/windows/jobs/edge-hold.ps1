# Diagnostic: "draft" + Ctrl+A in Edge, then hold 6 s so the host can look at the screen.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process msedge -ArgumentList "--app=data:text/html,<title>claudish</title><textarea%20id=t%20autofocus></textarea>", '--no-first-run'
Start-Sleep 4
$window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
[Keys]::Focus($window.MainWindowHandle) | Out-Null; Start-Sleep 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
$byId = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 't')
for ($i = 0; $i -lt 25 -and -not $area; $i++) { Start-Sleep -Milliseconds 200; $area = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $byId) }
$area.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue(''); Start-Sleep -Milliseconds 300
[Keys]::Type('draft'); Start-Sleep -Milliseconds 400
[Keys]::Press(0x41, 0x11)
"pressed; uia value: '$($root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $byId).GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value)'"
Start-Sleep 6
Stop-Process $service -Force; Stop-Process -Name msedge -Force
