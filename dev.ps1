$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$uvicorn = Join-Path $backend ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Creation de l'environnement virtuel backend..."
    python -m venv (Join-Path $backend ".venv")
}
if (-not (Test-Path -LiteralPath $uvicorn)) {
    Write-Host "Installation des dependances backend..."
    & $python -m pip install -r (Join-Path $backend "requirements.txt")
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    Write-Host "Installation des dependances frontend..."
    npm --prefix $frontend install
}

$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell.exe" }

$backendCmd = "`$env:T3D_CONFIG_DIR='.devdata/config'; `$env:T3D_STORAGE_DIR='.devdata/storage'; `$env:T3D_OPEN_MODE='local'; & '$uvicorn' app.main:app --reload --port 8000"
$frontendCmd = "npm run dev"

Start-Process -FilePath $shell -WorkingDirectory $backend -ArgumentList "-NoExit", "-Command", $backendCmd
Start-Process -FilePath $shell -WorkingDirectory $frontend -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host ""
Write-Host "Backend  : http://localhost:8000"
Write-Host "Frontend : http://localhost:5173"
Write-Host "Les deux terminaux sont ouverts. Ctrl+C dans chaque terminal pour arreter."