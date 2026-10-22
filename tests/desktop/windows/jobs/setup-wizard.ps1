# `claudish setup` for real in the VM: plan, then --yes (llama.cpp ARM64 and model downloads,
# logon task running the local stack), a rewrite through it, then remove the logon task.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine')
Set-Location C:\claudish
Remove-Item -Recurse -Force "$env:USERPROFILE\.config\claudish", C:\claudish\models\*.gguf -ErrorAction SilentlyContinue
function Health { try { (Invoke-RestMethod http://127.0.0.1:18765/health -TimeoutSec 2).backend } catch { 'down' } }
python -m claudish setup --dry-run
"--- yes"
python -m claudish setup --yes
"setup exit=$LASTEXITCODE; health: $(Health)"
$body = '{"text": "this is important"}'
try { "rewrite: " + (Invoke-RestMethod http://127.0.0.1:18765/suggest -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 30).text } catch { "rewrite failed: $_" }
"--- steps left"
python -m claudish setup --dry-run | Select-String 'download|write|register|start '
python -m claudish service uninstall
Start-Sleep 2
"llama-server left after uninstall: $([bool](Get-Process llama-server -ErrorAction SilentlyContinue))"
