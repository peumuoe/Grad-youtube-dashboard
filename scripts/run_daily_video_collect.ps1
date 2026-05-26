$ErrorActionPreference = "Stop"

$projectRoot = "C:\Users\PC2512\Desktop\Grad"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$videoScriptPath = Join-Path $projectRoot "scripts\01_collect_videos.py"
$transcriptScriptPath = Join-Path $projectRoot "scripts\03_collect_transcripts_stub.py"
$logDir = Join-Path $projectRoot "logs"
$schedulerLogPath = Join-Path $logDir "scheduled_video_collect.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Set-Location $projectRoot

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] Scheduled collection started." | Out-File -FilePath $schedulerLogPath -Append -Encoding utf8

cmd /c "`"$pythonExe`" `"$videoScriptPath`" >> `"$schedulerLogPath`" 2>&1"
$videoExitCode = $LASTEXITCODE
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] Video collection finished with exit code $videoExitCode." | Out-File -FilePath $schedulerLogPath -Append -Encoding utf8

cmd /c "`"$pythonExe`" `"$transcriptScriptPath`" >> `"$schedulerLogPath`" 2>&1"
$transcriptExitCode = $LASTEXITCODE
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] Transcript collection finished with exit code $transcriptExitCode." | Out-File -FilePath $schedulerLogPath -Append -Encoding utf8

if ($videoExitCode -ne 0) {
    exit $videoExitCode
}

exit $transcriptExitCode
