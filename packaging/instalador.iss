; Instalador de Windows (Inno Setup 6) para la versión piloto.
;   iscc packaging\instalador.iss
; Toma la carpeta que genera PyInstaller en dist\Anonimizador.

#define Nombre "Anonimizador"
#define Version "0.1.0"
#define Editor "LegalAtlas"

[Setup]
AppId={{6B7D3C1E-4A2F-4E8B-9C51-A1F0D2E3B4C5}
AppName={#Nombre}
AppVersion={#Version}
AppPublisher={#Editor}
DefaultDirName={autopf}\{#Nombre}
DefaultGroupName={#Nombre}
; Sin permisos de administrador: se instala para el usuario actual.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Anonimizador-{#Version}-instalador
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\Anonimizador.exe
AppPublisherURL=https://legalatlas.io
LicenseFile=..\LICENSE
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "..\dist\Anonimizador\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\Anonimizador.exe"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\Anonimizador.exe"; Tasks: escritorio

[Run]
Filename: "{app}\Anonimizador.exe"; Description: "Abrir {#Nombre}"; Flags: nowait postinstall skipifsilent
