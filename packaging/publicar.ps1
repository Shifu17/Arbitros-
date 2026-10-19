# Publica la versión actual como actualización (GitHub Releases).
#
#   .\packaging\publicar.ps1 -Notas "- Se agregó X`n- Se corrigió Y"
#
# Construye el instalador (si falta), crea el release v<versión> en el repositorio de
# actualizaciones y sube el instalador y su .sha256. Las apps instaladas lo detectan al abrirse.
# Requisitos: GitHub CLI (gh) con sesión iniciada:  gh auth login
param([Parameter(Mandatory = $true)][string]$Notas)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$python = Join-Path $raiz ".venv\Scripts\python.exe"
$env:PYTHONPATH = "src"
$version = (& $python -c "import arbitros; print(arbitros.__version__)").Trim()
$repo = (& $python -c "from arbitros.config import REPO_ACTUALIZACIONES; print(REPO_ACTUALIZACIONES)").Trim()

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "Falta GitHub CLI: winget install GitHub.cli" }
gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Inicia sesión primero: gh auth login" }

$existe = gh release view "v$version" --repo $repo 2>$null
if ($LASTEXITCODE -eq 0) { throw "La versión v$version ya está publicada en $repo. Sube el número de versión primero." }

$instalador = "dist\Arbitros-$version-instalador.exe"
if (-not (Test-Path $instalador)) { & "$PSScriptRoot\construir.ps1" }

gh release create "v$version" $instalador "$instalador.sha256" --repo $repo --title "Árbitros $version" --notes $Notas
if ($LASTEXITCODE -ne 0) { throw "No se pudo publicar." }
Write-Host "Publicado: https://github.com/$repo/releases/tag/v$version" -ForegroundColor Green
