$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { throw "Backend environment missing. Run scripts\setup-windows.ps1 first." }
Push-Location $Backend
try {
  & $VenvPython -m app.doctor
  if ($LASTEXITCODE -ne 0) { throw "AGASTYA setup checks failed. Fix the doctor output before starting the server." }
  & $VenvPython -m uvicorn app.main:app --reload --log-level info --port 8000
} finally { Pop-Location }
