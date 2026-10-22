# Windows typing scenarios in classic Notepad: an IMM32 Edit control, reached through Windows'
# TSF compatibility layer; text read back with WM_GETTEXT. Needs jobs/deploy.ps1 first.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
"Notepad: $($window.Id) $($window.Path)"
if (-not [Keys]::Focus($window.MainWindowHandle)) { throw 'Notepad could not take the foreground' }
Start-Sleep 1
function Get-Text { [Keys]::EditText($window.MainWindowHandle).TrimEnd("`r", "`n") }
function Reset-Target { [Keys]::ClearEdit($window.MainWindowHandle); Start-Sleep -Milliseconds 200 }
Invoke-Scenarios
# The first shortcut press commits (and is consumed); the second reaches the app.
[Keys]::Press(0x41, 0x11); Start-Sleep -Milliseconds 300
Check 'a second Ctrl+A reaches Notepad (all selected)' ([Keys]::Selection($window.MainWindowHandle)) '0..5'

Stop-Process -Name Notepad -Force
Complete-Scenarios
