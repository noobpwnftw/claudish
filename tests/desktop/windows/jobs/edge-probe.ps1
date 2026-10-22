# Probe: can a job drive a textarea in Edge (a TSF-native app) and read it back through UI Automation?
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
# No spaces: Start-Process splits arguments on them.
$page = 'data:text/html,<title>claudish</title><textarea%20id=t%20autofocus%20rows=20%20cols=80></textarea>'
Start-Process msedge -ArgumentList "--app=$page", '--no-first-run', '--disable-features=msEdgeFRE'
Start-Sleep 5
$window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
"edge window: $($window.Id) '$($window.MainWindowTitle)'"
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
# Chromium builds its accessibility tree once a UIA client asks; retry briefly.
for ($i = 0; $i -lt 25 -and -not $edit; $i++) { Start-Sleep -Milliseconds 200
$edit = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 't'))) }
"textarea found: $([bool]$edit)"
if ($edit) { "value: '$($edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value)'" }
