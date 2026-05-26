param(
    [int]$StartBatch = 19
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $projectRoot "scripts\31_run_notegpt_range_direct.py"

if (!(Test-Path $python)) {
    throw "Python executable not found: $python"
}

if (!(Test-Path $runner)) {
    throw "Range runner not found: $runner"
}

Set-Location $projectRoot
$env:PYTHONUNBUFFERED = "1"

& $python -u $runner --start-batch $StartBatch --auto-end
