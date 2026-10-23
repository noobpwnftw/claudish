# Diagnostic: with CLAUDISH_KEYLOG, what Claudish's PIME reports around the caret and for a
# selection in Notepad (lengths and input scopes only, never text).
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
$pime = "${env:ProgramFiles(x86)}\PIME"; $log = 'C:\setup\keylog.txt'
Remove-Item $log -ErrorAction SilentlyContinue
Get-Process PIMELauncher -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -notmatch 'claudish serve' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
$env:CLAUDISH_KEYLOG = $log
Start-Process "$pime\PIMELauncher.exe" -WorkingDirectory $pime; Start-Sleep 2
if ($env:PROBE_EDGE -or (Test-Path C:\setup\probe-edge)) {
  Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Process msedge -ArgumentList 'data:text/html,<title>claudish</title><textarea%20id=t%20autofocus></textarea>', '--no-first-run'
  Start-Sleep 4
  $window = Get-Process msedge | Where-Object { $_.MainWindowTitle -like 'claudish*' } | Select-Object -First 1
} else {
  Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Process notepad; Start-Sleep 3
  $window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
}
[Keys]::Focus($window.MainWindowHandle) | Out-Null; Start-Sleep 1
[Keys]::Press(0x76); [Keys]::Press(0x76)  # rewrite
[Keys]::Type('very important'); [Keys]::Press(0x1B); Start-Sleep -Milliseconds 300
Add-Content $log '--- Ctrl+A, then Tab'
[Keys]::Press(0x41, 0x11); Start-Sleep -Milliseconds 300
[Keys]::Press(0x09); Start-Sleep -Milliseconds 800
Get-Content $log | Select-Object -Last 12
Stop-Process $service -Force; Stop-Process -Name Notepad, msedge -Force -ErrorAction SilentlyContinue
