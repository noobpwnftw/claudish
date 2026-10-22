# Probe: what happens to a composition in Edge (TSF-native) on Ctrl+A, Escape, and Right arrow?
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process msedge -ArgumentList 'data:text/html,<title>claudish</title><textarea%20id=t%20autofocus></textarea>', '--no-first-run'
Start-Sleep 4
$window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
$byId = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 't')
for ($i = 0; $i -lt 25 -and -not $area; $i++) { Start-Sleep -Milliseconds 200; $area = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $byId) }
$value = $area.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
[Keys]::Focus($window.MainWindowHandle) | Out-Null; $area.SetFocus(); Start-Sleep 1
foreach ($case in @(@('Ctrl+A', 0x41, 0x11), @('Escape', 0x1B, 0), @('Right', 0x27, 0))) {
  $value.SetValue(''); Start-Sleep -Milliseconds 200
  [Keys]::Type('draft'); Start-Sleep -Milliseconds 400
  $during = $value.Current.Value
  [Keys]::Press([uint16]$case[1], [uint16]$case[2])
  Start-Sleep -Milliseconds 100; $soon = $value.Current.Value
  Start-Sleep -Milliseconds 900; $later = $value.Current.Value
  "{0,-7} during='{1}' 100ms='{2}' 1s='{3}'" -f $case[0], $during, $soon, $later
}
Stop-Process $service -Force; Stop-Process -Name msedge -Force
