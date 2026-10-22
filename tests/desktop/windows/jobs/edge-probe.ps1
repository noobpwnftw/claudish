# Probe: can a job drive a textarea in Edge (a TSF-native app) and read it back through UI Automation?
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
$page = 'data:text/html,<title>claudish</title><textarea id=t autofocus style="width:90vw;height:80vh"></textarea>'
Start-Process msedge -ArgumentList "--app=$page", '--no-first-run', '--disable-features=msEdgeFRE'
Start-Sleep 5
$window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
"edge window: $($window.Id) '$($window.MainWindowTitle)'"
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
$edit = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)))
"textarea found: $([bool]$edit)"
if ($edit) { "value: '$($edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value)'" }
