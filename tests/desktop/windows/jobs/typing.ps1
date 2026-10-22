# Inside the Windows VM: real keystrokes through TSF and PIME into classic Notepad (an IMM32 Edit
# control, reached through Windows' TSF compatibility layer); text read back with WM_GETTEXT.
$ErrorActionPreference = 'Stop'
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Threading;
public static class Keys {
  [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
  [StructLayout(LayoutKind.Explicit, Size = 40)] struct INPUT { [FieldOffset(0)] public uint type; [FieldOffset(8)] public KEYBDINPUT ki; }
  [DllImport("user32.dll")] static extern uint SendInput(uint n, INPUT[] inputs, int size);
  [DllImport("user32.dll")] static extern uint MapVirtualKey(uint code, uint mapType);
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  // A background process may not take the foreground; a synthetic Alt press lifts that lock.
  public static bool Focus(IntPtr hwnd) {
    for (int i = 0; i < 10 && GetForegroundWindow() != hwnd; i++) { Press(0x12); SetForegroundWindow(hwnd); Thread.Sleep(200); }
    return GetForegroundWindow() == hwnd;
  }
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr hwnd, uint msg, IntPtr w, System.Text.StringBuilder l);
  [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);
  // Classic Notepad: read its Edit control (WM_GETTEXTLENGTH, WM_GETTEXT).
  // Harness-only reset between scenarios: WM_SETTEXT on the Edit control, so no keys are involved.
  [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "SendMessageW")] static extern IntPtr SendText(IntPtr hwnd, uint msg, IntPtr w, string l);
  public static void ClearEdit(IntPtr window) {
    SendText(FindWindowEx(window, IntPtr.Zero, "Edit", null), 0x000C, IntPtr.Zero, "");
  }
  public static string EditText(IntPtr window) {
    IntPtr edit = FindWindowEx(window, IntPtr.Zero, "Edit", null);
    int length = (int)SendMessage(edit, 0x000E, IntPtr.Zero, IntPtr.Zero);
    var text = new System.Text.StringBuilder(length + 1);
    SendMessage(edit, 0x000D, (IntPtr)(length + 1), text);
    return text.ToString();
  }
  static void Send(ushort vk, bool up) {
    var input = new INPUT { type = 1 };
    input.ki.vk = vk; input.ki.scan = (ushort)MapVirtualKey(vk, 0); input.ki.flags = up ? 2u : 0u;
    SendInput(1, new[] { input }, Marshal.SizeOf(typeof(INPUT)));
  }
  public static void Press(ushort vk, ushort modifier = 0) {
    if (modifier != 0) Send(modifier, false);
    Send(vk, false); Send(vk, true);
    if (modifier != 0) Send(modifier, true);
    Thread.Sleep(40);
  }
  public static void Type(string text) {
    foreach (char c in text) {
      if (c >= 'a' && c <= 'z') Press((ushort)char.ToUpper(c));
      else if (c >= 'A' && c <= 'Z') Press((ushort)c, 0x10);
      else if (c == ' ') Press(0x20);
      else if (c == '-') Press(0xBD);
      else if (c == '.') Press(0xBE);
      else throw new ArgumentException("no key for " + c);
    }
  }
}
'@
$results = @()
function Check($name, $actual, $expected) {
  $ok = $actual -ceq $expected
  $script:results += $ok
  "{0} {1,-44} '{2}'{3}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $name, $actual, $(if ($ok) { '' } else { " (expected '$expected')" })
}

# 1. Make Claudish the input method for new apps.
$profile = Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\CTF\TIP' -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.PSChildName -eq '{EF97D106-1721-4466-A6B1-764987694B3C}' } | Select-Object -First 1
if (-not $profile) { throw 'Claudish TSF profile is not registered' }
$clsid = ($profile.Name -split '\\')[5]
$tip = "0409:$clsid{EF97D106-1721-4466-A6B1-764987694B3C}"
$languages = New-WinUserLanguageList en-US
$languages[0].InputMethodTips.Clear(); $languages[0].InputMethodTips.Add($tip)
Set-WinUserLanguageList $languages -Force
Set-WinDefaultInputMethodOverride -InputTip $tip
"Input method: $tip"

# 2. PIME launcher and the Claudish service (rules backend: deterministic output).
$pime = "${env:ProgramFiles(x86)}\PIME"
if (-not (Get-Process PIMELauncher -ErrorAction SilentlyContinue)) { Start-Process "$pime\PIMELauncher.exe" }
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$service = Start-Process python -ArgumentList '-m claudish serve --backend rules' -WorkingDirectory C:\claudish -WindowStyle Hidden -PassThru
for ($i = 0; $i -lt 50; $i++) { try { Invoke-RestMethod http://127.0.0.1:18765/health | Out-Null; break } catch { Start-Sleep -Milliseconds 200 } }

# 3. Notepad, focused; read its text through UI Automation.
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force
$notepad = Start-Process notepad -PassThru
Start-Sleep 3
$window = (Get-Process Notepad | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1)
"Notepad: $($window.Id) $(($window | Select-Object -ExpandProperty Path))"
if (-not [Keys]::Focus($window.MainWindowHandle)) { throw 'Notepad could not take the foreground' }
Start-Sleep 1
function Text { [Keys]::EditText($window.MainWindowHandle).TrimEnd("`r", "`n") }
# Not named "Clear": the built-in clear alias (Clear-Host) would take precedence.
function Reset-Notepad { [Keys]::ClearEdit($window.MainWindowHandle); Start-Sleep -Milliseconds 200 }

# 4. Scenarios (same intent as the Linux desktop test).
[Keys]::Type('hello-world'); Start-Sleep -Milliseconds 600
Check 'composition is not committed while typing' (Text) ''
[Keys]::Press(0x0D); Start-Sleep -Milliseconds 500
$dash = [string][char]0x2014  # not a literal: Windows PowerShell may read this file as ANSI
Check 'Enter commits your wording, dash substituted' (Text) "hello${dash}world"
Reset-Notepad
[Keys]::Type('very important'); Start-Sleep -Milliseconds 800
[Keys]::Press(0x09); Start-Sleep -Milliseconds 500
Check 'Tab accepts the rewrite' (Text) 'particularly crucial'
Reset-Notepad
[Keys]::Type('very'); Start-Sleep -Milliseconds 800
[Keys]::Type(' good'); [Keys]::Press(0x09); Start-Sleep -Milliseconds 300
Check 'Tab right after an edit commits nothing stale' (Text) ''
Start-Sleep -Milliseconds 800; [Keys]::Press(0x09); Start-Sleep -Milliseconds 500
Check 'fresh candidate after the edit' (Text) 'particularly good'
Reset-Notepad
[Keys]::Type('say hi'); [Keys]::Press(0x76); [Keys]::Press(0x76)
[Keys]::Press(0x0D); Start-Sleep -Milliseconds 800  # instruct: Enter sends
Check 'instruct holds the text until it is inserted' (Text) ''
[Keys]::Press(0x0D); Start-Sleep -Milliseconds 500  # the next Enter inserts
Check 'F7 to instruct, Enter sends, Enter inserts' (Text) "As requested${dash}say hi."
Reset-Notepad
[Keys]::Type('draft'); Start-Sleep -Milliseconds 300
[Keys]::Press(0x41, 0x11); Start-Sleep -Milliseconds 400  # Ctrl+A mid-composition
Check 'Ctrl shortcut keeps the composed text' (Text) 'draft'
[Keys]::Press(0x2E); Start-Sleep -Milliseconds 300  # Delete: proves Ctrl+A reached Notepad
Check '...and Notepad received Ctrl+A (all selected)' (Text) ''

Stop-Process $service -Force; Stop-Process -Name Notepad -Force
"{0}/{1} scenarios passed" -f ($results | Where-Object { $_ }).Count, $results.Count
if ($results -contains $false) { exit 1 }
