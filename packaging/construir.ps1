# Construye la app de escritorio y su instalador.
#
#   .\packaging\construir.ps1              -> dist\Arbitros\ (app) y dist\Arbitros-<versión>-instalador.exe
#   .\packaging\construir.ps1 -SinInstalador  -> solo la app (no requiere Inno Setup)
#
# Requisitos: el entorno .venv con las dependencias y PyInstaller; Inno Setup 6 para el instalador.
param([switch]$SinInstalador)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$python = Join-Path $raiz ".venv\Scripts\python.exe"

$version = (& $python -c "import sys; sys.path.insert(0, 'src'); import arbitros; print(arbitros.__version__)").Trim()
Write-Host "== Árbitros $version ==" -ForegroundColor Yellow

# 1) Pruebas: no se empaqueta algo que no pasa las pruebas
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Las pruebas fallaron; no se construye." }

# 2) App en carpeta (arranca más rápido que un solo .exe y el instalador la copia completa)
Remove-Item -Recurse -Force "build", "dist\Arbitros" -ErrorAction SilentlyContinue
$env:PYTHONPATH = "src"
& $python -m flet.cli pack packaging\arbitros_app.py `
    --name Arbitros `
    --icon src\arbitros\assets\logo.ico `
    --onedir `
    --distpath dist `
    --product-name "Árbitros" `
    --file-description "Árbitros - Colegio de Árbitros de Coahuila" `
    --product-version $version `
    --file-version "$version.0" `
    --company-name "Colegio de Árbitros de Coahuila" `
    --copyright "Colegio de Árbitros de Coahuila" `
    --add-data "src\arbitros\assets;arbitros\assets" "src\arbitros\db\migrations;arbitros\db\migrations" `
    --hidden-import "logging.config" `
    -y
if ($LASTEXITCODE -ne 0) { throw "Falló el empaquetado." }
Write-Host "App lista en dist\Arbitros\Arbitros.exe" -ForegroundColor Green
if ($SinInstalador) { exit 0 }

# 3) Instalador con Inno Setup
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No se encontró Inno Setup 6. Instálalo con: winget install JRSoftware.InnoSetup" }
& $iscc "/DVersion=$version" "/O$raiz\dist" packaging\arbitros.iss
if ($LASTEXITCODE -ne 0) { throw "Falló Inno Setup." }

# 4) Huella SHA-256: el actualizador verifica la descarga contra este archivo
$instalador = "dist\Arbitros-$version-instalador.exe"
$hash = (Get-FileHash $instalador -Algorithm SHA256).Hash.ToLower()
Set-Content -Path "$instalador.sha256" -Value "$hash  Arbitros-$version-instalador.exe" -Encoding ascii -NoNewline
Write-Host "Instalador listo: $instalador" -ForegroundColor Green
