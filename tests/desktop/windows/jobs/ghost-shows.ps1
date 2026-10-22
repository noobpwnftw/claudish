# Continue on Windows: after a word and its key-up, the suggestion shows by itself (no F6).
# For a screenshot from the host while this waits (vmscreen.sh).
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
if (-not [Keys]::Focus($window.MainWindowHandle)) { throw 'Notepad could not take the foreground' }
Start-Sleep 1
[Keys]::Type('Thanks for the review ')
Set-Content \\host.lan\Data\results\ghost-ready.txt "ready"  # the host takes its screenshot now
Start-Sleep 8
Stop-Process -Name Notepad -Force
Stop-Process $service -Force
