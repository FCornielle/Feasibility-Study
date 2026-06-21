# Construye la app de escritorio (.exe) — ejecutar desde PowerShell:
#   cd feasibility-study-app\desktop ; .\build.ps1
$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot          # feasibility-study-app/
$NODE = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.16.0-win-x64"
if (Test-Path $NODE) { $env:Path = "$NODE;$env:Path" }

Write-Host "== 1/3  Export estático del frontend (DESKTOP=1) ==" -ForegroundColor Cyan
Push-Location "$ROOT\frontend"
$env:DESKTOP = "1"
if (-not (Test-Path node_modules)) { npm install --no-fund --no-audit }
npm run build
Pop-Location
if (-not (Test-Path "$ROOT\frontend\out\index.html")) { throw "Falló el export estático (frontend\out)." }

Write-Host "== 2/3  Verificando artefactos del modelo (results) ==" -ForegroundColor Cyan
if (-not (Test-Path "$ROOT\results\substations.json")) {
  Write-Warning "Falta results\substations.json. Genera el modelo:  python pf_worker\substations.py ; python pf_worker\geo.py ; python pf_worker\enrich_coords.py"
}

Write-Host "== 3/3  Empaquetando con PyInstaller ==" -ForegroundColor Cyan
Push-Location $ROOT
python -m PyInstaller --noconfirm "desktop\launch.spec"
Pop-Location

$exe = "$ROOT\dist\InterconexionPVBESS\InterconexionPVBESS.exe"
if (Test-Path $exe) { Write-Host "OK -> $exe" -ForegroundColor Green }
else { throw "No se generó el .exe" }
