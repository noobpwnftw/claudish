# Diagnostic: with CLAUDISH_KEYLOG, how a Shift tap reaches the adapter in Notepad.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
$pime = "${env:ProgramFiles(x86)}\PIME"; $log = 'C:\setup\keylog.txt'
Remove-Item $log -ErrorAction SilentlyContinue
Get-Process PIMELauncher -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -notmatch 'claudish serve' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
$env:CLAUDISH_KEYLOG = $log
Start-Process "$pime\PIMELauncher.exe" -WorkingDirectory $pime; Start-Sleep 2
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
[Keys]::Focus($window.MainWindowHandle) | Out-Null; Start-Sleep 1
Add-Content $log '--- Shift tap, then ab'
Start-Sleep -Milliseconds 400; [Keys]::Press(0x10); Start-Sleep -Milliseconds 300
[Keys]::Type('ab'); Start-Sleep -Milliseconds 300
Get-Content $log | Select-Object -Last 14
"text: '$([Keys]::EditText($window.MainWindowHandle))'"
Stop-Process $service -Force; Stop-Process -Name Notepad -Force
