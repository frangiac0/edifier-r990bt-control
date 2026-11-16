; Per-user installer for the Edifier R990BT app (no admin rights).
; Built by packaging\build.ps1:  ISCC /DAppVersion=x.y.z /DSourceDir=<onedir build> installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\onedir\EdifierR990BT"
#endif

[Setup]
AppId={{6F1B7C1E-4E0A-4B8E-9C61-5E0B8A3D9A10}
AppName=Edifier R990BT
AppVersion={#AppVersion}
AppVerName=Edifier R990BT {#AppVersion}
AppPublisher=edifier-r990bt-control
AppPublisherURL=https://github.com/frangiac0/edifier-r990bt-control
AppSupportURL=https://github.com/frangiac0/edifier-r990bt-control/issues
DefaultDirName={localappdata}\Programs\Edifier R990BT
DefaultGroupName=Edifier R990BT
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=EdifierR990BT-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\EdifierR990BT.exe
UninstallDisplayName=Edifier R990BT
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Files of the previous version that a new build may no longer ship.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Edifier R990BT"; Filename: "{app}\EdifierR990BT.exe"
Name: "{autodesktop}\Edifier R990BT"; Filename: "{app}\EdifierR990BT.exe"; Tasks: desktopicon

[Run]
; Interactive install: offer to open the app at the end.
Filename: "{app}\EdifierR990BT.exe"; Description: "{cm:LaunchProgram,Edifier R990BT}"; Flags: nowait postinstall skipifsilent
; Silent install started by the app's updater (/RELAUNCH=1): reopen the app.
Filename: "{app}\EdifierR990BT.exe"; Parameters: "--updated"; Flags: nowait; Check: WantsRelaunch

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  AppMutex = 'Local\EdifierR990BT.Instance';
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

function WantsRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

// The updater starts this installer and then closes the app: wait for it.
function InitializeSetup: Boolean;
var
  I: Integer;
begin
  I := 0;
  while CheckForMutexes(AppMutex) and (I < 60) do
  begin
    Sleep(500);
    I := I + 1;
  end;
  Result := True;
end;

function InitializeUninstall: Boolean;
begin
  if CheckForMutexes(AppMutex) then
    MsgBox(CustomMessage('CloseAppFirst'), mbInformation, MB_OK);
  Result := not CheckForMutexes(AppMutex);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Remove the "Start with Windows" entry the app may have created.
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, RunKey, 'EdifierR990BT');
end;

[CustomMessages]
en.CloseAppFirst=Close Edifier R990BT first (tray icon > Quit), then run the uninstaller again.
es.CloseAppFirst=Cerrá primero Edifier R990BT (ícono de la bandeja > Salir) y volvé a ejecutar el desinstalador.
