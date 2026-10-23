# Screenshots of every state cd_AI shows in Notepad (the visual pass, G45). Each state is announced
# in the share's results\gallery-state.txt; the host (gallery.sh) screenshots the VM when it changes,
# then writes results\gallery-ack.txt. Needs jobs/deploy.ps1 first.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
$state = '\\host.lan\Data\results\gallery-state.txt'
$ack = '\\host.lan\Data\results\gallery-ack.txt'
function Show-State($name) {
  Remove-Item $ack -ErrorAction SilentlyContinue
  Set-Content $state $name
  for ($i = 0; $i -lt 100 -and -not (Test-Path $ack); $i++) { Start-Sleep -Milliseconds 100 }
}
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
if (-not [Keys]::Focus($window.MainWindowHandle)) { throw 'Notepad could not take the foreground' }
Start-Sleep 1
[Keys]::Type('Thanks for the review '); Start-Sleep -Milliseconds 1500
Show-State '01-continue-suggestion'
[Keys]::Press(0x1B); [Keys]::ClearEdit($window.MainWindowHandle)
Start-Sleep -Milliseconds 400; [Keys]::Press(0x10); Start-Sleep -Milliseconds 300  # compose
[Keys]::Type('this is very important'); Start-Sleep -Milliseconds 400
Show-State '02-compose-typing'
[Keys]::Press(0x09); Start-Sleep -Milliseconds 1200  # the rewrite in place
Show-State '03-rewrite-in-place'
[Keys]::Press(0x1B); [Keys]::Press(0x1B); Start-Sleep -Milliseconds 300
[Keys]::Type('say hi'); [Keys]::Press(0x0D); Start-Sleep -Milliseconds 1500  # drafts
Show-State '04-instruct-drafts'
[Keys]::Press(0x1B); [Keys]::Press(0x1B); Start-Sleep -Milliseconds 300
# A long instruction: the panel opens at the end of it, and when Enter sends it (the text leaves),
# the panel moves back to the caret.
[Keys]::Type('write a short note to the whole team thanking them for shipping on time'); Start-Sleep -Milliseconds 1500
Show-State '05-long-instruction'
[Keys]::Press(0x0D); Start-Sleep -Milliseconds 1500
Show-State '06-long-instruction-sent'
[Keys]::Press(0x1B); [Keys]::Press(0x1B)
Set-Content $state 'done'
Stop-Process -Name Notepad -Force
Stop-Process $service -Force
