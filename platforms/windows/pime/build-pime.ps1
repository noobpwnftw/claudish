# Build cd_AI's PIME (platforms/windows/pime): the text service for Win32, x64 and ARM64 processes,
# and the launcher, both with cd_AI's own names (CLSID, pipe, mutex) so they live beside any PIME.
# Writes them into a PIME tree (a released PIME's files, which supply its Python and the rest) that
# platforms/windows/package.py packages. Needs buildtools.ps1 to have finished and the patched source
# (make_source.sh OUT.zip), given as -Zip.
param([string]$Tree = 'C:\PIME-build', [string]$Zip = '\\host.lan\Data\pime-src.zip')
$ErrorActionPreference = 'Stop'
$source = 'C:\pime-src'
Remove-Item $source -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $Zip $source  # PowerShell names ignore case: not $Source
$vs = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -products * -latest -property installationPath
$cmake = Get-ChildItem "$vs\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" | Select-Object -First 1
Push-Location $source
# Through cmd, with output to a log: PowerShell 5 turns a native command's stderr (CMake's warnings)
# into errors.
foreach ($arch in 'Win32', 'x64', 'ARM64') {
  $log = "$source\build-$arch.log"
  cmd /c "`"$($cmake.FullName)`" . -Bbuild-$arch -G `"Visual Studio 17 2022`" -A $arch -DBUILD_TESTING=OFF > `"$log`" 2>&1"
  if ($LASTEXITCODE) { Get-Content $log -Tail 30; throw "cmake configure $arch failed" }
  cmd /c "`"$($cmake.FullName)`" --build build-$arch --config Release --target PIMETextService >> `"$log`" 2>&1"
  $failed = $LASTEXITCODE
  Select-String -Path $log -Pattern ' error |error C|error LNK' | Select-Object -First 20 | ForEach-Object { $_.Line }
  if ($failed) { throw "build $arch failed" }
  "built $arch"
}
# The launcher: x86 (it runs on every Windows, as PIME's does), the C runtime linked in (no
# Visual C++ runtime to install).
$cargo = "$env:USERPROFILE\.cargo\bin\cargo.exe"
if (-not (Test-Path $cargo)) {
  cmd /c "`"$source\PIMELauncher\rustup-init.exe`" -y --profile minimal > `"$source\rustup.log`" 2>&1"
}
cmd /c "`"$env:USERPROFILE\.cargo\bin\rustup.exe`" target add i686-pc-windows-msvc > `"$source\rustup-target.log`" 2>&1"
$env:RUSTFLAGS = '-C target-feature=+crt-static'
Push-Location "$source\PIMELauncher"
cmd /c "`"$cargo`" build --release --target i686-pc-windows-msvc > `"$source\cargo.log`" 2>&1"
$failed = $LASTEXITCODE
Pop-Location
if ($failed) { Get-Content "$source\cargo.log" -Tail 30; throw 'launcher build failed' }
"built the launcher"
Pop-Location
$targets = @{ 'Win32' = "$Tree\x86"; 'x64' = "$Tree\x64"; 'ARM64' = "$Tree\arm64" }
foreach ($arch in $targets.Keys) {
  # A released PIME has only its own machine's folder (x64 or arm64): every one is made here.
  New-Item -ItemType Directory -Force $targets[$arch] | Out-Null
  foreach ($dll in Get-ChildItem "$source\build-$arch\PIMETextService\Release\PIMETextService*.dll") {
    Copy-Item $dll.FullName (Join-Path $targets[$arch] $dll.Name) -Force
    "$($dll.Name) -> $($targets[$arch])"
  }
}
# On ARM64 the registered PIMETextService.dll is a forwarder: x64 apps load PIMETextService_x64.dll
# beside it, which must be cd_AI's x64 build (as PIME's installer places its own).
Copy-Item "$source\build-x64\PIMETextService\Release\PIMETextService.dll" "$Tree\arm64\PIMETextService_x64.dll" -Force
"PIMETextService.dll (x64) -> $Tree\arm64\PIMETextService_x64.dll"
Copy-Item "$source\PIMELauncher\target\i686-pc-windows-msvc\release\PIMELauncher.exe" "$Tree\PIMELauncher.exe" -Force
Copy-Item "$source\python\textService.py" "$Tree\python\textService.py" -Force
"cd_AI's PIME is in $Tree"
