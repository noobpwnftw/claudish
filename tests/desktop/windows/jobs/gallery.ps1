# Screenshots of cd_AI's states in Notepad, named by the design lab's state ids (design.html?platform=windows&state=ID). Each state is announced
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
[Keys]::Press(0x10); Start-Sleep -Milliseconds 300  # cd_AI starts in compose: continue first
[Keys]::Type('Thanks for the review '); Start-Sleep -Milliseconds 1500
Show-State 'continue'
[Keys]::Press(0x1B); [Keys]::ClearEdit($window.MainWindowHandle)
Start-Sleep -Milliseconds 400; [Keys]::Press(0x10); Start-Sleep -Milliseconds 300  # compose
[Keys]::Type('this is very important'); Start-Sleep -Milliseconds 400
Show-State 'compose'
[Keys]::Press(0x09); Start-Sleep -Milliseconds 1200  # the rewrite, waiting in the panel
Show-State 'converted'
[Keys]::Press(0x1B); [Keys]::Press(0x1B); Start-Sleep -Milliseconds 300
[Keys]::Type('say hi'); [Keys]::Press(0x0D); Start-Sleep -Milliseconds 1500  # drafts
Show-State 'drafts'
[Keys]::Press(0x0D); Start-Sleep -Milliseconds 400  # Enter on a draft: nothing inserted, Tab lit
Show-State 'nudged'
[Keys]::Press(0x1B); [Keys]::Press(0x1B); Start-Sleep -Milliseconds 300
# Esc steps back, then drops: it says so (Shift+Esc restores).
[Keys]::Type('never mind'); Start-Sleep -Milliseconds 300
[Keys]::Press(0x1B); Start-Sleep -Milliseconds 400
Show-State 'dropped'
Set-Content $state 'done'
Stop-Process -Name Notepad -Force
Stop-Process $service -Force
