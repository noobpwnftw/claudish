# Inside the Windows VM: real keystrokes through TSF and PIME into Notepad; text read back with UI Automation.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Threading;
public static class Keys {
  [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
  [StructLayout(LayoutKind.Explicit, Size = 40)] struct INPUT { [FieldOffset(0)] public uint type; [FieldOffset(8)] public KEYBDINPUT ki; }
  [DllImport("user32.dll")] static extern uint SendInput(uint n, INPUT[] inputs, int size);
  [DllImport("user32.dll")] static extern uint MapVirtualKey(uint code, uint mapType);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
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
[Keys]::SetForegroundWindow($window.MainWindowHandle) | Out-Null
Start-Sleep 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
$condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
function Text { $doc = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
  $doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern).DocumentRange.GetText(-1).TrimEnd("`r", "`n") }
function Clear { [Keys]::Press(0x41, 0x11); [Keys]::Press(0x2E); Start-Sleep -Milliseconds 300 }

# 4. Scenarios (same intent as the Linux desktop test).
[Keys]::Type('hello-world'); Start-Sleep -Milliseconds 600
Check 'composition is not committed while typing' (Text) ''
[Keys]::Press(0x0D); Start-Sleep -Milliseconds 500
Check 'Enter commits your wording, dash substituted' (Text) 'hello—world'
Clear
[Keys]::Type('very important'); Start-Sleep -Milliseconds 800
[Keys]::Press(0x09); Start-Sleep -Milliseconds 500
Check 'Tab accepts the rewrite' (Text) 'particularly crucial'
Clear
[Keys]::Type('very'); Start-Sleep -Milliseconds 800
[Keys]::Type(' good'); [Keys]::Press(0x09); Start-Sleep -Milliseconds 300
Check 'Tab right after an edit commits nothing stale' (Text) ''
Start-Sleep -Milliseconds 800; [Keys]::Press(0x09); Start-Sleep -Milliseconds 500
Check 'fresh candidate after the edit' (Text) 'particularly good'
Clear
[Keys]::Type('say hi'); [Keys]::Press(0x76); [Keys]::Press(0x76); Start-Sleep -Milliseconds 800
[Keys]::Press(0x09); Start-Sleep -Milliseconds 500
Check 'F7 to instruct, Tab writes the draft' (Text) 'As requested—say hi.'
Clear
[Keys]::Type('draft'); [Keys]::Press(0x41, 0x11); Start-Sleep -Milliseconds 400
Check 'Ctrl shortcut commits the wording first' (Text) 'draft'

Stop-Process $service -Force; Stop-Process -Name Notepad -Force
"{0}/{1} scenarios passed" -f ($results | Where-Object { $_ }).Count, $results.Count
if ($results -contains $false) { exit 1 }
