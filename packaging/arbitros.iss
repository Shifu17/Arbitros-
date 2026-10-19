; Instalador de Árbitros (Inno Setup 6). Lo compila packaging\construir.ps1:
;   ISCC.exe /DVersion=0.6.0 /O<dist> packaging\arbitros.iss
; Se instala por usuario (sin pedir permisos de administrador), así las actualizaciones
; automáticas se aplican sin ventanas de Windows pidiendo confirmación.
; Los datos (%APPDATA%\Arbitros) NO se tocan al instalar, actualizar ni desinstalar.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{8F3C6A2E-4B7D-4E1A-9C5B-2D6E7F8A9B10}
AppName=Árbitros
AppVersion={#Version}
AppVerName=Árbitros {#Version}
AppPublisher=Colegio de Árbitros de Coahuila
VersionInfoVersion={#Version}
DefaultDirName={localappdata}\Programs\Arbitros
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Arbitros-{#Version}-instalador
SetupIconFile=..\src\arbitros\assets\logo.ico
UninstallDisplayIcon={app}\Arbitros.exe
UninstallDisplayName=Árbitros
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Cierra la app si está abierta (también en las actualizaciones silenciosas)
CloseApplications=force
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Quita las librerías de la versión anterior para que no queden archivos viejos mezclados
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Arbitros\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Árbitros"; Filename: "{app}\Arbitros.exe"
Name: "{autodesktop}\Árbitros"; Filename: "{app}\Arbitros.exe"; Tasks: escritorio

[Run]
; Sin "skipifsilent": tras una actualización automática (silenciosa) la app se vuelve a abrir sola
Filename: "{app}\Arbitros.exe"; Description: "Abrir Árbitros"; Flags: nowait postinstall
