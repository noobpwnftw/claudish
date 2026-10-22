# Diagnostic: run PIMELauncher with a debug log, type in Notepad, and show whether a TSF client connected.
$pime = "${env:ProgramFiles(x86)}\PIME"
Get-Process PIMELauncher, python -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item C:\setup\launcher.log -ErrorAction SilentlyContinue
Start-Process "$pime\PIMELauncher.exe" -ArgumentList '/log-file C:\setup\launcher.log' -WorkingDirectory $pime
Start-Sleep 3
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Threading;
public static class K {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
  public static void Tap(byte vk) { keybd_event(vk, 0, 0, IntPtr.Zero); keybd_event(vk, 0, 2, IntPtr.Zero); Thread.Sleep(60); }
}
'@
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$w = (Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1).MainWindowHandle
for ($i = 0; $i -lt 10 -and [K]::GetForegroundWindow() -ne $w; $i++) { [K]::Tap(0x12); [K]::SetForegroundWindow($w) | Out-Null; Start-Sleep -Milliseconds 200 }
foreach ($vk in 0x48, 0x49) { [K]::Tap($vk) }
Start-Sleep 2
"launcher processes: $((Get-Process PIMELauncher -ErrorAction SilentlyContinue).Count); python: $((Get-Process python -ErrorAction SilentlyContinue).Count)"
"log (last lines):"; Get-Content C:\setup\launcher.log -ErrorAction SilentlyContinue | Select-Object -Last 25
Stop-Process -Name Notepad -Force
