# G35 in Windows terminals: "gti status" fails, then Shift, fix, Enter, Enter drafts at the prompt an
# instruction that saw the screen (the service reads it through UI Automation; nothing is installed
# in the shell). Windows Terminal is the portable ARM64 build from github.com/microsoft/terminal
# releases, unpacked from the VM share's wt\wt.zip. Needs jobs/deploy.ps1 first.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
function Get-Screen {
  $element = [System.Windows.Automation.AutomationElement]::FocusedElement
  $pattern = $null
  if (-not $element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) { return '' }
  (($pattern.DocumentRange.GetText(-1) -split "`r?`n" | ForEach-Object { $_.TrimEnd() }) -join "`n").TrimEnd()
}
function Last-Line { (Get-Screen) -split "`n" | Select-Object -Last 1 }
function Wait-Screen($pattern) {
  for ($i = 0; $i -lt 40; $i++) { if ((Get-Screen) -match $pattern) { return } ; Start-Sleep -Milliseconds 250 }
}
function Invoke-Terminal($name, $window) {
  if (-not [Keys]::Focus($window)) { throw "$name could not take the foreground" }
  Start-Sleep 1
  [Keys]::Type('gti status'); Start-Sleep -Milliseconds 400
  if (-not ((Last-Line) -like '*gti status')) {  # composing: drop it and switch to continue
    [Keys]::Press(0x1B); Start-Sleep -Milliseconds 400; [Keys]::Press(0x10); Start-Sleep -Milliseconds 300
    [Keys]::Type('gti status'); Start-Sleep -Milliseconds 400
  }
  Check "${name}: continue types the command straight in" ((Last-Line) -like '*>gti status') $true
  [Keys]::Press(0x0D); Wait-Screen 'not recognized'
  Start-Sleep -Milliseconds 400; [Keys]::Press(0x10); Start-Sleep -Milliseconds 300  # compose
  [Keys]::Type('fix'); [Keys]::Press(0x0D)  # the instruction, with the screen's last lines
  Start-Sleep -Milliseconds 1500
  [Keys]::Press(0x09)  # Tab: the draft, inserted at the prompt; running it would be the user's Enter
  Wait-Screen 'having read the terminal'
  # (cmd shows the em dash as a hyphen; this file is read as ANSI, so match any character there)
  Check "${name}: fix sees the screen, the draft lands at the prompt" ((Last-Line) -match '>As requested.fix, having read the terminal\.$') $true
}

if (-not (Test-Path C:\wt\terminal-1.25.2733.0\WindowsTerminal.exe)) { Expand-Archive \\host.lan\Data\wt\wt.zip C:\wt -Force }
Get-Process WindowsTerminal -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process C:\wt\terminal-1.25.2733.0\WindowsTerminal.exe -ArgumentList 'cmd.exe'; Start-Sleep 6
$wt = Get-Process WindowsTerminal | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
Invoke-Terminal 'Windows Terminal' $wt.MainWindowHandle
Stop-Process -Name WindowsTerminal -Force

$console = Start-Process conhost.exe -ArgumentList 'cmd.exe' -PassThru; Start-Sleep 3
# A console window reports its shell as the owner, not conhost.
$shell = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($console.Id) AND Name='cmd.exe'" | Select-Object -First 1
$handle = (Get-Process -Id $shell.ProcessId).MainWindowHandle
Invoke-Terminal 'classic console' $handle
Stop-Process -Id $console.Id -Force -ErrorAction SilentlyContinue
Complete-Scenarios
