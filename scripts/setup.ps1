param([string]$Python = 'py')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPreviousTemp = $env:TEMP
$taskPreviousTmp = $env:TMP
Push-Location -LiteralPath $taskRoot
try {
    New-Item -ItemType Directory -Path '.cache' -Force | Out-Null
    $env:TEMP = Join-Path $taskRoot '.cache'
    $env:TMP = $env:TEMP
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed. Specify a working Python 3.12+ executable with -Python.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & '.\.venv\Scripts\python.exe' -m pip install -e . --no-deps --no-build-isolation
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
    & '.\.venv\Scripts\python.exe' -m skylark status
    if ($LASTEXITCODE -ne 0) { throw 'Readiness check failed.' }
    Push-Location -LiteralPath 'frontend'
    try {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
} finally {
    $env:TEMP = $taskPreviousTemp
    $env:TMP = $taskPreviousTmp
    Pop-Location
}
