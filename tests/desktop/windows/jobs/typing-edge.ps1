# Windows typing scenarios in Edge, a TSF-native app: a textarea, read back through UI Automation.
# Needs jobs/deploy.ps1 first.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
# No spaces: Start-Process splits arguments on them.
$page = 'data:text/html,<title>claudish</title><textarea%20id=t%20autofocus%20rows=20%20cols=80></textarea>'
Start-Process msedge -ArgumentList "--app=$page", '--no-first-run'
Start-Sleep 4
$window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
"Edge: $($window.Id)"
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
$byId = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 't')
for ($i = 0; $i -lt 25 -and -not $area; $i++) {  # Chromium builds its accessibility tree on demand
  Start-Sleep -Milliseconds 200; $area = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $byId) }
$value = $area.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
if (-not [Keys]::Focus($window.MainWindowHandle)) { throw 'Edge could not take the foreground' }
$area.SetFocus(); Start-Sleep 1
function Get-Text { $value.Current.Value.TrimEnd("`r", "`n") }
function Reset-Target { $value.SetValue(''); Start-Sleep -Milliseconds 200 }
Invoke-Scenarios
# The first shortcut press commits (and is consumed); the second reaches the app.
[Keys]::Press(0x41, 0x11); Start-Sleep -Milliseconds 300
[Keys]::Press(0x2E); Start-Sleep -Milliseconds 300  # Delete removes the selection Ctrl+A made
Check 'a second Ctrl+A reaches Edge (all selected)' (Get-Text) ''
Stop-Process -Name msedge -Force
Complete-Scenarios
