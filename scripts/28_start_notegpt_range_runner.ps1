param(
    [int]$StartBatch = 19,
    [int]$EndBatch = 0,
    [switch]$AutoEnd
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $projectRoot "scripts\27_run_notegpt_batch_range.py"
$stdout = Join-Path $projectRoot "data\raw\notegpt_range_auto_stdout.log"
$stderr = Join-Path $projectRoot "data\raw\notegpt_range_auto_stderr.log"

if (!(Test-Path $python)) {
    throw "Python executable not found: $python"
}
if (!(Test-Path $runner)) {
    throw "Range runner not found: $runner"
}

$env:PYTHONUNBUFFERED = "1"

$arguments = @(
    "-u"
    $runner
    "--start-batch"
    "$StartBatch"
)

if ($AutoEnd.IsPresent) {
    $arguments += "--auto-end"
}
elseif ($EndBatch -gt 0) {
    $arguments += @("--end-batch", "$EndBatch")
}
else {
    throw "Provide -AutoEnd or a positive -EndBatch."
}

& $python @arguments 1>> $stdout 2>> $stderr
