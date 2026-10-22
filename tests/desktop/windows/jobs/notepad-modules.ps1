# Diagnostic: is PIME's TSF DLL loaded inside Notepad, and which launcher processes are alive?
$n = Get-Process Notepad -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $n) { Start-Process notepad; Start-Sleep 2; $n = Get-Process Notepad | Select-Object -First 1 }
"notepad $($n.Id): text-input modules:"
$n.Modules | Where-Object { $_.ModuleName -match 'PIME|msctf|TextInput|imm32|ctf' } | ForEach-Object { "  $($_.ModuleName)  $($_.FileName)" }
"launchers:"; Get-CimInstance Win32_Process -Filter "Name='PIMELauncher.exe'" | ForEach-Object { "  $($_.ProcessId) parent=$($_.ParentProcessId) $($_.CommandLine)" }
