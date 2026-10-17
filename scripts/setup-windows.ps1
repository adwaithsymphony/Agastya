$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

Write-Host "AGASTYA Windows setup" -ForegroundColor Green

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Write-Host "Created .env. Review DATABASE_URL before continuing."
}

if (-not (Test-Path $VenvPython)) {
    Push-Location $Backend
    try {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.13 -m venv .venv
            if ($LASTEXITCODE -ne 0) {
                & py -3.12 -m venv .venv
            }
            if ($LASTEXITCODE -ne 0) {
                & py -3.11 -m venv .venv
            }
            if ($LASTEXITCODE -ne 0) {
                throw "Could not create the Python virtual environment."
            }
        } else {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) {
                throw "Could not create the Python virtual environment."
            }
        }
    } finally {
        Pop-Location
    }
}

Push-Location $Backend
try {
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

    & $VenvPython -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

    & $VenvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed. Check DATABASE_URL." }

    $doctor = & $VenvPython -m app.doctor 2>&1
    $doctor | ForEach-Object { Write-Host $_ }

    if ($LASTEXITCODE -ne 0) {
        throw "Setup diagnostics failed. Review the output above."
    }

    if ($doctor -match "Users: 0 total; 0 sample accounts") {
        & $VenvPython -m app.seed
        if ($LASTEXITCODE -ne 0) { throw "Demo seeding failed." }
    } else {
        Write-Host "Existing users detected; skipped demo seeding."
    }

    Write-Host "Setup complete. Start the backend with scripts\start-backend.ps1" -ForegroundColor Green
} finally {
    Pop-Location
}
