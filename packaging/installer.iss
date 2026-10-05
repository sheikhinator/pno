; PNO installer (Inno Setup 6). Installs for the current Windows user only: no administrator rights needed.
; Built by .github/workflows/build.yml:  ISCC /DAppVersion=1.0.0 /DSourceDir=dist\PNO packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\PNO"
#endif

[Setup]
AppId={{6C1D2B7E-4F0A-4E8B-9C3D-2A7F5B1E9D40}
AppName=PNO - People & Performance
AppVersion={#AppVersion}
AppVerName=PNO {#AppVersion}
AppPublisher=PNO
DefaultDirName={localappdata}\Programs\PNO
DefaultGroupName=PNO
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=PNO-Setup-{#AppVersion}
OutputDir=..\dist
SetupIconFile=..\src\pno\assets\pno.ico
UninstallDisplayIcon={app}\PNO.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PNO"; Filename: "{app}\PNO.exe"
Name: "{group}\Uninstall PNO"; Filename: "{uninstallexe}"
Name: "{userdesktop}\PNO"; Filename: "{app}\PNO.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PNO.exe"; Description: "Open PNO now"; Flags: nowait postinstall skipifsilent

; Your data (%LOCALAPPDATA%\PNO) is kept when PNO is uninstalled or updated.
