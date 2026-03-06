# Show cross-build service logs from Windows Event Log.
# The service output goes through Task Scheduler, which logs to the event log.

param(
    [int]$Count = 50
)

$TaskName = "CrossBuildService"

Write-Host "=== Task Scheduler events for $TaskName (last $Count) ==="
Get-WinEvent -FilterHashtable @{
    LogName = 'Microsoft-Windows-TaskScheduler/Operational'
    Level = @(2, 3, 4)  # Error, Warning, Info
} -MaxEvents 200 -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -like "*$TaskName*" } |
    Select-Object -First $Count |
    Format-Table TimeCreated, LevelDisplayName, Message -AutoSize -Wrap

Write-Host ""
Write-Host "For full application output, check the console window or redirect output"
Write-Host "to a file by modifying the scheduled task action."
