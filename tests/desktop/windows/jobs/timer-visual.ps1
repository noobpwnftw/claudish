# A rewrite that arrives late, with no key pressed after Tab: with Claudish's PIME it should take
# your words' place on screen by itself (the timer). Leaves Notepad open for a screenshot
# (vmscreen.sh); the answer takes 1.5 s.
. C:\claudish\tests\desktop\windows\jobs\typing-core.ps1
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Id -eq $service.Id } | Stop-Process -Force
Stop-Process $service -Force -ErrorAction SilentlyContinue
$config = "$env:TEMP\claudish-slow.json"
@'
{"profiles": {"slow": {"backend": "command", "timeout": 10,
  "command": ["python", "-c", "import time; time.sleep(1.5); print('Exceedingly important.')"]}}}
'@ | Set-Content $config -Encoding ascii
$slow = Start-Process python -ArgumentList "-m claudish serve --config $config --profile slow" -WorkingDirectory C:\claudish -WindowStyle Hidden -PassThru
for ($i = 0; $i -lt 50; $i++) { try { Invoke-RestMethod http://127.0.0.1:18765/health | Out-Null; break } catch { Start-Sleep -Milliseconds 200 } }
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$window = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
[Keys]::Focus($window.MainWindowHandle) | Out-Null; Start-Sleep 1
Start-Sleep -Milliseconds 400; [Keys]::Press(0x10); Start-Sleep -Milliseconds 200  # a Shift tap: compose
[Keys]::Type('this is important'); Start-Sleep -Milliseconds 300
[Keys]::Press(0x09)  # Tab asks; no key after this
Start-Sleep 4
Stop-Process $slow -Force  # the rewrite stays on screen; later jobs start their own service
"ready for the screenshot (vmscreen.sh): the rewrite should show in place, with no key pressed after Tab"
