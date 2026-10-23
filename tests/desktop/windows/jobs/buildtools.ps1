# Start installing the Visual Studio 2022 C++ build tools (x64 and ARM64, Windows 11 SDK, CMake)
# for building PIME from source; returns at once. Run again to see whether they are ready.
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
  $found = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.ARM64 -property installationPath
  if ($found) { "ready: $found"; exit 0 }
}
if (Get-Process vs_BuildTools, vs_installer, setup -ErrorAction SilentlyContinue) { "installing..."; exit 0 }
$bootstrapper = "$env:TEMP\vs_BuildTools.exe"
Invoke-WebRequest https://aka.ms/vs/17/release/vs_BuildTools.exe -OutFile $bootstrapper -UseBasicParsing
$arguments = '--quiet --wait --norestart --nocache ' +
  '--add Microsoft.VisualStudio.Workload.VCTools ' +
  '--add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 ' +
  '--add Microsoft.VisualStudio.Component.VC.Tools.ARM64 ' +
  '--add Microsoft.VisualStudio.Component.VC.CMake.Project ' +
  '--add Microsoft.VisualStudio.Component.Windows11SDK.22621'
Start-Process $bootstrapper -ArgumentList $arguments
"started"
