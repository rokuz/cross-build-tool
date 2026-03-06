# Stop cross-build service.

$ErrorActionPreference = "Stop"
$TaskName = "CrossBuildService"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Service not installed."
    exit 0
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Write-Host "Service stopped."
