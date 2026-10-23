# Every design-lab state drawn by Claudish's PIME panel in Notepad, to compare with
# design.html?platform=windows&state=ID: the lab's panels (claudish/web/lab-states.js, made by
# composition.py) go where the IME's preview reads them (claudish_ime.py, PREVIEW); each F12 draws the
# next, announced like gallery.ps1's states for gallery.sh to capture. Needs jobs/deploy.ps1 first.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
$state = '\\host.lan\Data\results\gallery-state.txt'
$ack = '\\host.lan\Data\results\gallery-ack.txt'
function Show-State($name) {
  Remove-Item $ack -ErrorAction SilentlyContinue
  Set-Content $state $name
  for ($i = 0; $i -lt 100 -and -not (Test-Path $ack); $i++) { Start-Sleep -Milliseconds 100 }
}
$preview = Join-Path $env:LOCALAPPDATA 'Claudish\lab-preview.js'
New-Item -ItemType Directory -Force (Split-Path $preview) | Out-Null
$source = Get-Content -Raw -Encoding UTF8 C:\claudish\claudish\web\lab-states.js
Set-Content -Encoding UTF8 $preview $source
$json = $source.Substring($source.IndexOf('{'), $source.LastIndexOf('}') - $source.IndexOf('{') + 1) | ConvertFrom-Json
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
if (-not [Keys]::Focus($window.MainWindowHandle)) { throw 'Notepad could not take the foreground' }
Start-Sleep 1
foreach ($name in $json.PSObject.Properties.Name) {
  [Keys]::Press(0x7B); Start-Sleep -Milliseconds 500
  Show-State $name
}
[Keys]::Press(0x7B)
Remove-Item $preview
Set-Content $state 'done'
Stop-Process -Name Notepad -Force
