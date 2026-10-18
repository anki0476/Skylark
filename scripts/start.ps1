param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$skylarkRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $skylarkRoot
try {
    if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Build the frontend first using scripts/setup.ps1' }
    & '.\.venv\Scripts\python.exe' -m skylark serve --port $Port
} finally { Pop-Location }
