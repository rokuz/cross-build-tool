# Start cross-build service.

$ErrorActionPreference = "Stop"
$TaskName = "CrossBuildService"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Service not installed. Run install.ps1 first."
    exit 1
}

Start-ScheduledTask -TaskName $TaskName
Write-Host "Service started."
Write-Host ""

# Brief pause then show status
Start-Sleep -Seconds 2
& "$PSScriptRoot\status.ps1"
