# Diagnostic: open Notepad in front and report the input language and layout of its thread.
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Fg {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern IntPtr GetKeyboardLayout(uint thread);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
}
'@
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process notepad; Start-Sleep 3
$w = (Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1).MainWindowHandle
for ($i = 0; $i -lt 10 -and [Fg]::GetForegroundWindow() -ne $w; $i++) { [Fg]::keybd_event(0x12,0,0,0); [Fg]::keybd_event(0x12,0,2,0); [Fg]::SetForegroundWindow($w) | Out-Null; Start-Sleep -Milliseconds 200 }
"foreground is notepad: $([Fg]::GetForegroundWindow() -eq $w)"
"layout: 0x{0:x}" -f [int64][Fg]::GetKeyboardLayout([Fg]::GetWindowThreadProcessId($w, [IntPtr]::Zero))
"language list:"; Get-WinUserLanguageList | ForEach-Object { "  $($_.LanguageTag): $($_.InputMethodTips -join ', ')" }
"default override: $(Get-WinDefaultInputMethodOverride)"
"PIME processes: $((Get-Process PIMELauncher, python -ErrorAction SilentlyContinue | ForEach-Object { $_.ProcessName + ':' + $_.Id }) -join ' ')"
