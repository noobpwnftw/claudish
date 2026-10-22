# Diagnostic: can a native ARM64 process load PIME's TSF DLL?
$pime = "${env:ProgramFiles(x86)}\PIME"
"arm64 folder:"; Get-ChildItem "$pime\arm64" | ForEach-Object { "  $($_.Name) $($_.Length)" }
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine')
python -c "import ctypes, platform, sys; print('python', platform.machine())
for name in ('arm64', 'x64'):
    path = sys.argv[1] + '\\' + name + '\\PIMETextService.dll'
    try:
        ctypes.WinDLL(path); print(name, 'loaded')
    except OSError as e:
        print(name, 'failed:', e)" "$pime"
"Launcher running: $([bool](Get-Process PIMELauncher -ErrorAction SilentlyContinue))"
