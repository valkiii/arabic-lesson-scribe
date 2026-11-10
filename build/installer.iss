; Inno Setup 6.3+ script. Compile from repo root:
;   iscc /DMyAppVersion=0.1.0 build\installer.iss
; Expects the PyInstaller onedir output in dist\ArabicLessonScribe\.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppName "Arabic Lesson Scribe"
#define MyAppExe "ArabicLessonScribe.exe"

[Setup]
AppId={{6F0B7E52-3C5A-4E0B-9A57-1D7C2B8E4A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Arabic Lesson Scribe
DefaultDirName={localappdata}\ArabicLessonScribe
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist_installer
OutputBaseFilename=ArabicLessonScribe-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExe}
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\ArabicLessonScribe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Start {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WEBVIEW2_GUID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WEBVIEW2_URL  = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';
  VCREDIST_URL  = 'https://aka.ms/vs/17/release/vc_redist.x64.exe';

var
  DownloadPage: TDownloadWizardPage;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if Progress = ProgressMax then
    Log(Format('Downloaded %s', [FileName]));
  Result := True;
end;

function WebView2Installed(): Boolean;
var
  Ver: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WEBVIEW2_GUID, 'pv', Ver) then
    Result := (Ver <> '') and (Ver <> '0.0.0.0');
  if (not Result) and RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WEBVIEW2_GUID, 'pv', Ver) then
    Result := (Ver <> '') and (Ver <> '0.0.0.0');
end;

function VCRedistInstalled(): Boolean;
var
  Installed: Cardinal;
begin
  // Setup runs in 64-bit mode, so HKLM is the 64-bit view.
  Result := RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed)
            and (Installed = 1);
end;

procedure RunInstaller(const FileName, Params, Title: String);
var
  Code: Integer;
  Path: String;
begin
  Path := ExpandConstant('{tmp}\' + FileName);
  if not FileExists(Path) then Exit;
  WizardForm.StatusLabel.Caption := Title;
  // Try as the current user first; if the installer needs elevation (error 740),
  // ask Windows for it once via the normal UAC prompt.
  if not Exec(Path, Params, '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code) or (Code = 740) then
  begin
    if not ShellExec('runas', Path, Params, '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code) then
      Log(Format('Could not run %s (code %d)', [FileName, Code]));
  end;
  Log(Format('%s exit code %d', [FileName, Code]));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  NeedWV2, NeedVC: Boolean;
begin
  Result := '';
  NeedWV2 := not WebView2Installed();
  NeedVC := not VCRedistInstalled();
  if not (NeedWV2 or NeedVC) then Exit;

  DownloadPage := CreateDownloadPage('Downloading required Windows components',
    'This is a one-time download from Microsoft. Please keep this window open.', @OnDownloadProgress);
  DownloadPage.Clear;
  if NeedWV2 then DownloadPage.Add(WEBVIEW2_URL, 'MicrosoftEdgeWebview2Setup.exe', '');
  if NeedVC then DownloadPage.Add(VCREDIST_URL, 'vc_redist.x64.exe', '');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
    except
      // Degrade gracefully: continue installing the app even if offline.
      Log('Prerequisite download failed: ' + GetExceptionMessage);
      SuppressibleMsgBox('Could not download a Windows component (' + GetExceptionMessage + ').'#13#10 +
        'The app will still be installed. If it does not open, install "Microsoft Edge WebView2 Runtime" ' +
        'and "Microsoft Visual C++ Redistributable (x64)" from microsoft.com and try again.',
        mbInformation, MB_OK, IDOK);
    end;
  finally
    DownloadPage.Hide;
  end;

  if NeedWV2 then
    RunInstaller('MicrosoftEdgeWebview2Setup.exe', '/silent /install', 'Installing Microsoft Edge WebView2 Runtime...');
  if NeedVC then
    RunInstaller('vc_redist.x64.exe', '/install /quiet /norestart', 'Installing Visual C++ runtime...');
end;
