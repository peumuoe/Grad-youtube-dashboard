param(
    [int]$Port = 9222,
    [string]$ProfileDirectory = "Default"
)

$chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$userDataDir = Join-Path $env:LocalAppData "Google\Chrome\User Data"

if (-not (Test-Path $chromeExe)) {
    Write-Error "Chrome executable not found at $chromeExe"
    exit 1
}

if (-not (Test-Path $userDataDir)) {
    Write-Error "Chrome user data directory not found at $userDataDir"
    exit 1
}

$runningChrome = Get-Process chrome -ErrorAction SilentlyContinue
if ($runningChrome) {
    Write-Host "Close all Chrome windows first, then run this script again." -ForegroundColor Yellow
    exit 1
}

$arguments = @(
    "--remote-debugging-port=$Port"
    "--user-data-dir=$userDataDir"
    "--profile-directory=$ProfileDirectory"
    "https://www.youtube.com/"
)

Write-Host "Launching Chrome with remote debugging on port $Port using profile '$ProfileDirectory'..." -ForegroundColor Green
Start-Process -FilePath $chromeExe -ArgumentList $arguments
