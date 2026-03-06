# Show cross-build service status.

$TaskName = "CrossBuildService"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Service not installed."
    exit 0
}

Write-Host "Task:   $TaskName"
Write-Host "State:  $($task.State)"

$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
if ($info) {
    Write-Host "Last run: $($info.LastRunTime)"
    Write-Host "Result:   $($info.LastTaskResult)"
}
