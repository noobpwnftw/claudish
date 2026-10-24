; cd_AI's Windows installer (G61), compiled by package.py, which fills in @VERSION@, @TEXT_SERVICE@
; and @PROFILE@ and lays out the payload beside this file: PIME\, python-x64\, python-arm64\,
; vc_redist.x86.exe and icon.ico.
;
; For the machine (an administrator, once): cd_AI's PIME in Program Files, its text service
; registered for x86, x64 and ARM64 apps, and PIME's launcher at every login. For the person
; installing: cd_AI added to their input sources, a starter config, the service at every login,
; and cd_AI's settings in the browser (the key, the voice).

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
Source: "PIME\*"; DestDir: "{app}\PIME"; Flags: recursesubdirs ignoreversion
Source: "python-x64\*"; DestDir: "{app}\python"; Check: not IsArm64; Flags: recursesubdirs ignoreversion
Source: "python-arm64\*"; DestDir: "{app}\python"; Check: IsArm64; Flags: recursesubdirs ignoreversion
Source: "vc_redist.x86.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PIMELauncher"; ValueData: """{app}\PIME\PIMELauncher.exe"""; Flags: uninsdeletevalue

[Run]
; PIME's launcher is an x86 program: the x86 Visual C++ runtime, which an ARM64 Windows lacks.
Filename: "{tmp}\vc_redist.x86.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing the Visual C++ runtime..."; Flags: runhidden waituntilterminated
Filename: "{syswow64}\regsvr32.exe"; Parameters: "/s ""{app}\PIME\x86\PIMETextService.dll"""; Flags: runhidden waituntilterminated
Filename: "{sys}\regsvr32.exe"; Parameters: "/s ""{app}\PIME\x64\PIMETextService.dll"""; Flags: runhidden waituntilterminated
Filename: "{sys}\regsvr32.exe"; Parameters: "/s ""{app}\PIME\arm64\PIMETextService.dll"""; Check: IsArm64; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im PIMELauncher.exe"; Flags: runhidden; RunOnceId: "StopLauncher"
Filename: "{sys}\schtasks.exe"; Parameters: "/delete /tn claudish /f"; Flags: runhidden; RunOnceId: "StopService"
Filename: "{syswow64}\regsvr32.exe"; Parameters: "/s /u ""{app}\PIME\x86\PIMETextService.dll"""; Flags: runhidden; RunOnceId: "UnregisterX86"
Filename: "{sys}\regsvr32.exe"; Parameters: "/s /u ""{app}\PIME\x64\PIMETextService.dll"""; Flags: runhidden; RunOnceId: "UnregisterX64"
Filename: "{sys}\regsvr32.exe"; Parameters: "/s /u ""{app}\PIME\arm64\PIMETextService.dll"""; Check: IsArm64; Flags: runhidden; RunOnceId: "UnregisterArm64"

[Code]
function InstallLayoutOrTip(Tip: String; Flags: DWORD): BOOL;
  external 'InstallLayoutOrTip@input.dll stdcall';

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
