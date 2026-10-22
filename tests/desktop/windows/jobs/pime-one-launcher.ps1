# Diagnostic: exactly one launcher (with a debug log), keys into Notepad, then: did a client connect?
$pime = "${env:ProgramFiles(x86)}\PIME"; $log = "$env:TEMP\pime-launcher.log"
Get-Process PIMELauncher, python, Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1; Remove-Item $log -ErrorAction SilentlyContinue
Start-Process "$pime\PIMELauncher.exe" -ArgumentList "/log-file=$log" -WorkingDirectory $pime
Start-Sleep 2
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Threading;
public static class K {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
  public static void Tap(byte vk) { keybd_event(vk, 0, 0, IntPtr.Zero); keybd_event(vk, 0, 2, IntPtr.Zero); Thread.Sleep(60); }
}
'@
Start-Process notepad; Start-Sleep 2
$w = (Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1).MainWindowHandle
for ($i = 0; $i -lt 10 -and [K]::GetForegroundWindow() -ne $w; $i++) { [K]::Tap(0x12); [K]::SetForegroundWindow($w) | Out-Null; Start-Sleep -Milliseconds 200 }
foreach ($vk in 0x48, 0x49, 0x48, 0x49) { [K]::Tap($vk) }
Start-Sleep 3
"launchers: $((Get-Process PIMELauncher -ErrorAction SilentlyContinue).Count)  python: $((Get-Process python -ErrorAction SilentlyContinue | ForEach-Object Path) -join ', ')"
"log exists: $(Test-Path $log)"; Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 20
