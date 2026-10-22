# Diagnostic: PIME binaries' architectures, VC++ runtimes, and how PIMELauncher starts.
$pime = "${env:ProgramFiles(x86)}\PIME"
function Machine($path) {
  $bytes = [IO.File]::ReadAllBytes($path); $pe = [BitConverter]::ToInt32($bytes, 0x3C)
  switch ([BitConverter]::ToUInt16($bytes, $pe + 4)) { 0x14c {'x86'} 0x8664 {'x64'} 0xAA64 {'arm64'} 0xA641 {'arm64ec'} default {'other'} }
}
Get-ChildItem $pime -Recurse -Include *.exe, *.dll -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\python\\(Lib|DLLs)\\' } | Select-Object -First 25 |
  ForEach-Object { "{0,-8} {1}" -f (Machine $_.FullName), $_.FullName.Replace($pime, '') }
"VC++ runtimes:"
Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }
"backends.json:"; Get-Content "$pime\backends.json" -ErrorAction SilentlyContinue
"Launcher run:"
$p = Start-Process "$pime\PIMELauncher.exe" -ArgumentList '/log-file C:\setup\launcher.log' -PassThru; Start-Sleep 5
"exit: $($p.HasExited) $(if ($p.HasExited) { '0x{0:x}' -f $p.ExitCode })"
Get-Content C:\setup\launcher.log -ErrorAction SilentlyContinue | Select-Object -Last 15
