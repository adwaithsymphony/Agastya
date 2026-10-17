$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Portal = Join-Path $Root "plant-portal"
if (-not (Test-Path (Join-Path $Portal "node_modules"))) {
    Write-Host "Plant Intelligence dependencies are not installed. Run npm.cmd install in plant-portal first." -ForegroundColor Yellow
    exit 1
}
Set-Location $Portal
npm.cmd run dev
