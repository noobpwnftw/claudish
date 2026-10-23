# Probe: identify the focused terminal and read its screen through UI Automation (no hook, no MCP).
# Run: tests/desktop/windows/vm.sh run tests/desktop/probes/windows_terminal.ps1 120 (the portable Windows
# Terminal ARM64 zip from github.com/microsoft/terminal releases in the VM share's wt/wt.zip).
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$shell = New-Object -ComObject WScript.Shell
function Read-Focused($label) {
  $watch = [Diagnostics.Stopwatch]::StartNew()
  $e = [System.Windows.Automation.AutomationElement]::FocusedElement
  $c = $e.Current
  $process = (Get-Process -Id $c.ProcessId -ErrorAction SilentlyContinue).ProcessName
  $text = $null
  $pattern = $null
  if ($e.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
    $text = $pattern.DocumentRange.GetText(-1)
  }
  $ms = $watch.Elapsed.TotalMilliseconds
  "== ${label}: process=$process class=$($c.ClassName) type=$($c.ControlType.ProgrammaticName) name=$($c.Name) ms=$([math]::Round($ms,1)) chars=$(if ($text) {$text.Length} else {'none'})"
  if ($text) { ($text.TrimEnd() -split "`r?`n" | Select-Object -Last 8) -join "`n" }
}
function Run-Commands {
  foreach ($line in @("cd C:\Windows", "gti status", "dir C:\nope")) { $shell.SendKeys($line + "{ENTER}"); Start-Sleep -Milliseconds 900 }
}
if (-not (Test-Path C:\wt\terminal-1.25.2733.0\WindowsTerminal.exe)) { Expand-Archive \\host.lan\Data\wt\wt.zip C:\wt -Force }
$exe = "C:\wt\terminal-1.25.2733.0\WindowsTerminal.exe"
Start-Process $exe -ArgumentList "cmd.exe"; Start-Sleep 6
$wt = Get-Process WindowsTerminal -ErrorAction SilentlyContinue | Select-Object -First 1
"wt running: " + [bool]$wt
if ($wt) { $shell.AppActivate($wt.Id) | Out-Null; Start-Sleep 1 }
Run-Commands; Read-Focused "Windows Terminal (first read)"; Read-Focused "Windows Terminal (second read)"
Get-Process WindowsTerminal -ErrorAction SilentlyContinue | Stop-Process -Force
