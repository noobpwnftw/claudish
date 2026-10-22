Add-Type @'
using System; using System.Runtime.InteropServices;
public static class P {
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
  [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "SendMessageW")] public static extern IntPtr SendText(IntPtr h, uint msg, IntPtr w, string l);
  [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "SendMessageW")] public static extern IntPtr SendBuffer(IntPtr h, uint msg, IntPtr w, System.Text.StringBuilder l);
}
'@
Start-Process notepad; Start-Sleep 2
$n = Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
$edit = [P]::FindWindowEx($n.MainWindowHandle, [IntPtr]::Zero, "Edit", $null)
"edit hwnd: $edit"
foreach ($value in "abc", "") {
  $r = [P]::SendText($edit, 0x000C, [IntPtr]::Zero, $value)
  $b = New-Object System.Text.StringBuilder 256; [P]::SendBuffer($edit, 0x000D, [IntPtr]256, $b) | Out-Null
  "WM_SETTEXT('$value') returned $r; text now: '$b'"
}
Stop-Process -Name Notepad -Force
