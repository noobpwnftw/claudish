# Real service install in the VM: a logon task running `claudish serve --backend rules`, then uninstall.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine')
Set-Location C:\claudish
function Health { try { (Invoke-RestMethod http://127.0.0.1:18765/health -TimeoutSec 2).backend } catch { 'down' } }
"before: $(Health)"
python -m claudish service install --serve -- --backend rules
for ($i = 0; $i -lt 30 -and (Health) -eq 'down'; $i++) { Start-Sleep -Milliseconds 500 }
"after install: $(Health)"
python -m claudish doctor | Select-String 'Service|Starts at login'
python -m claudish service uninstall
Start-Sleep 2
"after uninstall: $(Health)"
python -m claudish doctor | Select-String 'Starts at login'
