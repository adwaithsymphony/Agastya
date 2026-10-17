$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js 20+ and npm are required. Install Node.js, then reopen PowerShell." }
Push-Location $Frontend
try {
  if (-not (Test-Path (Join-Path $Frontend "node_modules"))) { npm install }
  npm run dev
} finally { Pop-Location }
