param([string]$PimeRoot = "${env:ProgramFiles(x86)}\PIME")
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (!(Test-Path (Join-Path $PimeRoot 'python\textService.py'))) {
    throw 'Install PIME with its Python backend first, or specify -PimeRoot.'
}
$Destination = Join-Path $PimeRoot 'python\input_methods\claudish'
if (Test-Path $Destination) {
    throw "Already installed at $Destination. Remove that folder before reinstalling."
}
Copy-Item (Join-Path $PSScriptRoot 'claudish') $Destination -Recurse
Copy-Item (Join-Path $ProjectRoot 'claudish\composition.py') $Destination
Copy-Item (Join-Path $ProjectRoot 'claudish\client.py') $Destination
Copy-Item (Join-Path $ProjectRoot 'claudish\screen.py') $Destination
# PIME enumerates input methods when its TSF DLL is registered. PIME 2.0 ships an
# ARM64X DLL for Windows on ARM; native ARM64 apps load only that one.
foreach ($Arch in @('x86', 'x64', 'arm64')) {
    $Dll = Join-Path $PimeRoot "$Arch\PIMETextService.dll"
    if (Test-Path $Dll) {
        $Regsvr = if ($Arch -eq 'x86' -and [Environment]::Is64BitOperatingSystem) {
            "$env:WINDIR\SysWOW64\regsvr32.exe"
        } else { "$env:WINDIR\System32\regsvr32.exe" }
        $Process = Start-Process $Regsvr -ArgumentList @('/s', "`"$Dll`"") -Wait -PassThru
        if ($Process.ExitCode -ne 0) { throw "Registration failed: $Dll" }
    }
}
Write-Host 'Installed cd_AI — Claudish. Sign out/in, then select it with Win+Space.'
Write-Host 'Run the Claudish service and llama-server under your normal user account.'
