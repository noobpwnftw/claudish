# Shared by the Windows typing jobs: real keystrokes (SendInput) through TSF and PIME into an app.
# A job dot-sources this, defines Get-Text and Reset-Target for its app, then calls Invoke-Scenarios.
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
  public static string Selection(IntPtr window) {
    IntPtr edit = FindWindowEx(window, IntPtr.Zero, "Edit", null);
    long r = (long)SendMessage(edit, 0x00B0, IntPtr.Zero, IntPtr.Zero);  // EM_GETSEL
    return (r & 0xFFFF) + ".." + ((r >> 16) & 0xFFFF);
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
$script:results = @()
$script:known = @{}  # scenario name -> issue; reported as KNOWN, not counted as a failure
function Check($name, $actual, $expected) {
  $ok = $actual -ceq $expected
  if (-not $ok -and $script:known.ContainsKey($name)) {
    "KNOWN {0,-44} '{1}' ({2})" -f $name, $actual, $script:known[$name]; return
  }
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

function Invoke-Scenarios {
  # Scenarios (same intent as the Linux desktop test).
  [Keys]::Type('ls -la'); Start-Sleep -Milliseconds 300  # switching to cd_AI types like en_US
  Check 'cd_AI starts in continue: keys go straight in' (Get-Text) 'ls -la'
  Reset-Target
  [Keys]::Press(0x10); Start-Sleep -Milliseconds 200  # a Shift tap: continue -> compose
  [Keys]::Type('hello-world'); Start-Sleep -Milliseconds 600
  Check 'composition is not committed while typing' (Get-Text) ''
  [Keys]::Press(0x0D, 0x10); Start-Sleep -Milliseconds 500  # Shift+Enter keeps your words
  $dash = [string][char]0x2014  # not a literal: Windows PowerShell may read this file as ANSI
  Check 'Shift+Enter keeps your words as typed' (Get-Text) 'hello-world'
  Reset-Target
  [Keys]::Type('very important'); Start-Sleep -Milliseconds 300
  [Keys]::Press(0x09); Start-Sleep -Milliseconds 500  # Tab asks; the rewrite takes your words' place
  Check 'Tab rewrites in place, nothing committed yet' (Get-Text) ''
  [Keys]::Press(0x09); Start-Sleep -Milliseconds 500  # Tab again keeps it
  Check 'Tab again keeps the rewrite' (Get-Text) 'particularly crucial'
  Reset-Target
  [Keys]::Type('very'); Start-Sleep -Milliseconds 800
  Check 'rewrite sends nothing while you type' (Get-Text) ''
  [Keys]::Type(' good'); [Keys]::Press(0x09); Start-Sleep -Milliseconds 800
  [Keys]::Press(0x09); Start-Sleep -Milliseconds 500
  Check 'the rewrite is of the whole phrase' (Get-Text) 'particularly good'
  Reset-Target
  [Keys]::Type(' hi'); Start-Sleep -Milliseconds 300  # a leading space is the app's, not the phrase's
  [Keys]::Press(0x0D, 0x10); Start-Sleep -Milliseconds 300  # Shift+Enter keeps your words
  Check 'a leading space goes straight to the app' (Get-Text) ' hi'
  Reset-Target
  [Keys]::Press(0x10); Start-Sleep -Milliseconds 200  # a Shift tap: continue, typing goes straight in
  [Keys]::Type('Only my words '); Start-Sleep -Milliseconds 300  # a pause after a word: continue asks
  Check 'continue: typing goes straight into the app' (Get-Text) 'Only my words '
  Start-Sleep -Milliseconds 800; [Keys]::Press(0x75)  # F6 shows the suggestion (PIME redraws on keys)
  [Keys]::Press(0x09); Start-Sleep -Milliseconds 500
  Check 'continue: Tab takes the rest of the sentence' (Get-Text) "Only my words and then some${dash}naturally."
  Reset-Target
  [Keys]::Press(0x10); Start-Sleep -Milliseconds 200  # a Shift tap: compose
  [Keys]::Type('say hi')
  [Keys]::Press(0x0D); Start-Sleep -Milliseconds 800  # instruct: Enter sends
  Check 'instruct holds the text until it is inserted' (Get-Text) ''
  [Keys]::Press(0x0D); Start-Sleep -Milliseconds 500  # the next Enter inserts
  Check 'Enter sends an instruction, Enter inserts' (Get-Text) "As requested${dash}say hi."
  Reset-Target
  [Keys]::Type('never mind'); [Keys]::Press(0x0D); Start-Sleep -Milliseconds 800
  [Keys]::Press(0x1B); Start-Sleep -Milliseconds 300  # Esc: the draft closes, the instruction stays
  [Keys]::Press(0x1B); Start-Sleep -Milliseconds 300  # Esc again: it is dropped
  Check 'Esc twice drops an instruction, nothing inserted' (Get-Text) ''
  Reset-Target
  [Keys]::Type('draft'); Start-Sleep -Milliseconds 300
  [Keys]::Press(0x41, 0x11); Start-Sleep -Milliseconds 400  # Ctrl+A mid-composition
  Check 'Ctrl shortcut keeps the composed text' (Get-Text) 'draft'
}

function Complete-Scenarios {
  Stop-Process $service -Force
  "{0}/{1} scenarios passed" -f ($script:results | Where-Object { $_ }).Count, $script:results.Count
  if ($script:results -contains $false) { exit 1 }
}
