# Diagnostic: list Notepad's UI Automation tree so the typing job can find its text area.
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 4
$window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {
  $c = $e.Current
  $patterns = ($e.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName -replace 'PatternIdentifiers.Pattern', '' }) -join ','
  "{0,-28} {1,-28} {2,-20} [{3}]" -f $c.ControlType.ProgrammaticName, $c.ClassName, $c.Name, $patterns
}
Stop-Process -Name Notepad -Force
