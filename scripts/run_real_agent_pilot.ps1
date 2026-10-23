param(
    [string]$DataDirectory = '.cache/ux-preview'
)

$ErrorActionPreference = 'Stop'
$skylarkRoot = Split-Path -Parent $PSScriptRoot
$names = @('NEBIUS_API_KEY', 'NEBIUS_MODEL', 'NEBIUS_INPUT_USD_PER_MILLION',
    'NEBIUS_OUTPUT_USD_PER_MILLION', 'SKYLARK_CONFIRMED_CREDITS_USD',
    'SKYLARK_ALLOWANCE_USD', 'SKYLARK_LIVE_ENABLED')
$original = @{}
foreach ($name in $names) { $original[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

function Read-Default([string]$prompt, [string]$default) {
    $answer = Read-Host "$prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim()
}

Push-Location -LiteralPath $skylarkRoot
try {
    if (-not $env:NEBIUS_API_KEY) {
        $secret = Read-Host 'Nebius API key (hidden; never saved to a file)' -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        try { $env:NEBIUS_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    }
    $env:NEBIUS_MODEL = Read-Default 'Verified tool-capable NVIDIA model' 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
    Write-Host 'Confirm these rates against your current Nebius account before continuing.'
    $env:NEBIUS_INPUT_USD_PER_MILLION = Read-Default 'Input USD per million tokens' '0.06'
    $env:NEBIUS_OUTPUT_USD_PER_MILLION = Read-Default 'Output USD per million tokens' '0.24'
    $env:SKYLARK_CONFIRMED_CREDITS_USD = Read-Host 'Current confirmed available credits in USD'
    $env:SKYLARK_ALLOWANCE_USD = '0.05'
    $env:SKYLARK_LIVE_ENABLED = '1'

    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
        throw 'Skylark virtual environment missing; run scripts/setup.ps1 first.'
    }
    # Validate the key-independent spending configuration before any model call.
    & '.\.venv\Scripts\python.exe' -c 'from skylark.wind.provider import Settings; print(Settings.load().snapshot())'
    if ($LASTEXITCODE -ne 0) { throw 'Pilot preflight failed; no agent run was started.' }

    $report = Join-Path '.cache' ('real-agent-pilot-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
    & '.\.venv\Scripts\python.exe' -m skylark --data $DataDirectory adapter examples/nebius_agent_adapter.py --compare-repair | Tee-Object -FilePath $report
    if ($LASTEXITCODE -ne 0) { throw "Pilot failed. Inspect the run in $DataDirectory; no success is claimed." }
    & '.\.venv\Scripts\python.exe' scripts/verify_real_agent_pilot.py $report --data $DataDirectory
    if ($LASTEXITCODE -ne 0) { throw "Pilot evidence did not pass verification. Inspect $report before claiming success." }
    Write-Host "Pilot summary saved to $report"
}
finally {
    foreach ($name in $names) {
        if ($null -eq $original[$name]) { Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue }
        else { Set-Item -LiteralPath "Env:$name" -Value $original[$name] }
    }
    Pop-Location
}
