# Build Claudish's patched PIME (platforms/windows/pime) and install its text service over the
# released PIME: the DLLs for Win32, x64 and ARM64 processes, and textService.py. Needs
# buildtools.ps1 to have finished and the patched source (make_source.sh) unpacked beside it.
$source = 'C:\pime-src'
Remove-Item $source -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive \\host.lan\Data\pime-src.zip $source
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
Pop-Location
# Install: loaded DLLs cannot be overwritten, but they can be renamed; new processes load the new ones.
$pime = "${env:ProgramFiles(x86)}\PIME"
$targets = @{ 'Win32' = "$pime\x86"; 'x64' = "$pime\x64"; 'ARM64' = "$pime\arm64" }
foreach ($arch in $targets.Keys) {
  $built = Get-ChildItem "$source\build-$arch\PIMETextService\Release\PIMETextService*.dll"
  foreach ($dll in $built) {
    $target = Join-Path $targets[$arch] $dll.Name
    if (Test-Path $target) { Move-Item $target "$target.$(Get-Date -Format yyyyMMddHHmmss).old" -Force }
    Copy-Item $dll.FullName $target
    "installed $($dll.Name) -> $($targets[$arch])"
  }
}
Copy-Item "$source\python\textService.py" "$pime\python\textService.py" -Force
Get-Process PIMELauncher -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process "$pime\PIMELauncher.exe"
"PIME patched; launcher restarted"
