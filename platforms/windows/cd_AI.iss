; cd_AI's Windows installer (G61), compiled by package.py, which fills in @VERSION@, @TEXT_SERVICE@
; and @PROFILE@ and lays out the payload beside this file: PIME\, python-x64\, python-arm64\ and
; icon.ico.
;
; Everything goes in cd_AI's own folder. Its PIME is a library of cd_AI's: its text service has its
; own CLSID, finds its input methods beside its own DLL, and talks to its own launcher over its own
; pipe (platforms/windows/pime), so it lives beside any PIME already installed (Chewing, Rime).
; For the machine (an administrator, once): the text service registered for x86, x64 and ARM64
; apps, and cd_AI's launcher at every login. For the person installing: cd_AI added to their input
; sources, a starter config, the service at every login, and cd_AI's settings in the browser.

[Setup]
AppId={{6C2D9B8E-3F1A-4E4B-9C55-0B7C1D2E8A41}
AppName=cd_AI
AppVersion=@VERSION@
AppPublisher=Claudish
AppPublisherURL=https://claudish.io
DefaultDirName={autopf}\cd_AI
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible arm64
ArchitecturesInstallIn64BitMode=x64compatible arm64
PrivilegesRequired=admin
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\PIME\python\input_methods\claudish\icon.ico
OutputBaseFilename=cd_AI-setup
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=no

[Files]
; The text service's DLLs are loaded in every app that takes text: in use, they are replaced at the
; next restart (as input methods' installers do), which an update asks for.
Source: "PIME\*"; DestDir: "{app}\PIME"; Flags: recursesubdirs ignoreversion restartreplace uninsrestartdelete
Source: "python-x64\*"; DestDir: "{app}\python"; Check: not IsArm64; Flags: recursesubdirs ignoreversion restartreplace uninsrestartdelete
Source: "python-arm64\*"; DestDir: "{app}\python"; Check: IsArm64; Flags: recursesubdirs ignoreversion restartreplace uninsrestartdelete

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "cd_AI"; ValueData: """{app}\PIME\PIMELauncher.exe"""; Flags: uninsdeletevalue

[Run]
Filename: "{syswow64}\regsvr32.exe"; Parameters: "/s ""{app}\PIME\x86\PIMETextService.dll"""; Flags: runhidden waituntilterminated
Filename: "{sys}\regsvr32.exe"; Parameters: "/s ""{app}\PIME\x64\PIMETextService.dll"""; Flags: runhidden waituntilterminated
Filename: "{sys}\regsvr32.exe"; Parameters: "/s ""{app}\PIME\arm64\PIMETextService.dll"""; Check: IsArm64; Flags: runhidden waituntilterminated

[UninstallRun]
; In order: cd_AI's processes stop (only cd_AI's: a PIME beside it runs a launcher of the same
; name), cd_AI leaves your input sources, its text service is unregistered; then the files go.
Filename: "{sys}\schtasks.exe"; Parameters: "/end /tn claudish"; Flags: runhidden; RunOnceId: "EndService"
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Get-Process pythonw,python,PIMELauncher -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{app}\*' } | Stop-Process -Force"""; Flags: runhidden; RunOnceId: "StopProcesses"
Filename: "{sys}\schtasks.exe"; Parameters: "/delete /tn claudish /f"; Flags: runhidden; RunOnceId: "DeleteService"
Filename: "{app}\python\python.exe"; Parameters: "-c ""import ctypes; ctypes.windll.input.InstallLayoutOrTip('0409:@TEXT_SERVICE_ESCAPED@@PROFILE_ESCAPED@', 1)"""; Flags: runhidden; RunOnceId: "LeaveInputSources"
Filename: "{syswow64}\regsvr32.exe"; Parameters: "/s /u ""{app}\PIME\x86\PIMETextService.dll"""; Flags: runhidden; RunOnceId: "UnregisterX86"
Filename: "{sys}\regsvr32.exe"; Parameters: "/s /u ""{app}\PIME\x64\PIMETextService.dll"""; Flags: runhidden; RunOnceId: "UnregisterX64"
Filename: "{sys}\regsvr32.exe"; Parameters: "/s /u ""{app}\PIME\arm64\PIMETextService.dll"""; Check: IsArm64; Flags: runhidden; RunOnceId: "UnregisterArm64"

[Code]
function InstallLayoutOrTip(Tip: String; Flags: DWORD): BOOL;
  external 'InstallLayoutOrTip@input.dll stdcall';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { An update: cd_AI's service and launcher let go of their files first (only cd_AI's). }
  ExecAsOriginalUser(ExpandConstant('{sys}\schtasks.exe'), '/end /tn claudish', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
       '-NoProfile -Command "Get-Process pythonw,PIMELauncher -ErrorAction SilentlyContinue | Where-Object { $_.Path -like ''' +
       ExpandConstant('{app}') + '\*'' } | Stop-Process -Force"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure AsYou(Arguments: String; Wait: TExecWait);
var
  Code: Integer;
begin
  ExecAsOriginalUser(ExpandConstant('{app}\python\python.exe'), Arguments, '', SW_HIDE, Wait, Code);
end;

procedure CurStepChanged(Step: TSetupStep);
var
  Code: Integer;
  First: Boolean;
begin
  if Step = ssPostInstall then
  begin
    { A first install has no config yet (init writes one; an update keeps it). }
    First := not FileExists(ExpandConstant('{%USERPROFILE}\.config\claudish\config.json'));
    { cd_AI in your input sources (English), next to the keyboard you have. }
    InstallLayoutOrTip('0409:@TEXT_SERVICE@@PROFILE@', 0);
    ExecAsOriginalUser(ExpandConstant('{app}\PIME\PIMELauncher.exe'), '', '', SW_HIDE, ewNoWait, Code);
    AsYou('-m claudish init', ewWaitUntilTerminated);
    AsYou('-m claudish service install', ewWaitUntilTerminated);
    { The first install ends in cd_AI's settings (the key, the voice); an update opens nothing. }
    if First then
      AsYou('-m claudish settings --first', ewNoWait);
  end;
end;
