$ErrorActionPreference = "Stop"

$projectRoot = "C:\Users\PC2512\Desktop\Grad"
$runnerPath = Join-Path $projectRoot "scripts\run_daily_video_collect.ps1"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$runnerPath`"" `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At 4:10PM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName "GradYouTubeVideoCollect" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily YouTube video collection for Grad project at 16:10 KST" `
    -Force

Get-ScheduledTask -TaskName "GradYouTubeVideoCollect" | Get-ScheduledTaskInfo | Format-List *
