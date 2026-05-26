# Uruchamia backend (osobne okno), czeka az API odpowie, potem Vite w tym terminalu.
# Uzycie (z katalogu glownego repo):  .\dev.ps1
# lub:  powershell -ExecutionPolicy Bypass -File .\dev.ps1

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "analytics-embed"
$backendPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$port = 8000
$healthUrl = "http://127.0.0.1:$port/api/health"

if (-not (Test-Path $backendDir)) {
    Write-Error "Brak katalogu backend: $backendDir"
    exit 1
}
if (-not (Test-Path $frontendDir)) {
    Write-Error "Brak katalogu analytics-embed: $frontendDir"
    exit 1
}
if (-not (Test-Path $backendPython)) {
    Write-Error "Brak interpretera venv backendu: $backendPython"
    exit 1
}

Write-Host "Uruchamianie backendu (nowe okno PowerShell)..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $backendDir -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-Command",
    "& `"$backendPython`" -m uvicorn app.main:app --reload --port $port"
)

Write-Host "Oczekiwanie na backend ($healthUrl)..." -ForegroundColor Yellow
$deadline = (Get-Date).AddMinutes(2)
$ok = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            $ok = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 400
    }
}

if (-not $ok) {
    Write-Error "Backend nie odpowiedzial w czasie. Zamknij okno backendu jesli nie jest potrzebne."
    exit 1
}

Write-Host "Backend OK. Uruchamianie frontendu (Vite)..." -ForegroundColor Green
Set-Location $frontendDir
npm run dev
