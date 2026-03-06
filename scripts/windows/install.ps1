# Install cross-build as a Windows scheduled task.
# Usage: .\install.ps1 -RepoPath C:\path\to\project [-Port 5200]

param(
    [Parameter(Mandatory=$true)]
    [string]$RepoPath,

    [int]$Port = 5200
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PkgDir = (Resolve-Path "$ScriptDir\..\..").Path
$VenvDir = Join-Path $PkgDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$TaskName = "CrossBuildService"
$RepoPath = (Resolve-Path $RepoPath).Path

# Create venv if needed
if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating venv at $VenvDir..."
    python -m venv $VenvDir
    & (Join-Path $VenvDir "Scripts\pip.exe") install --quiet -r (Join-Path $PkgDir "requirements.txt")
}

# Remove existing task if present
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task."
}

# Create the scheduled task
$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m cross_build serve --repo `"$RepoPath`" --port $Port" `
    -WorkingDirectory $PkgDir

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Cross-Platform Build Service" | Out-Null

Write-Host ""
Write-Host "Installed scheduled task: $TaskName"
Write-Host "  Repo: $RepoPath"
Write-Host "  Port: $Port"
Write-Host "  Python: $PythonExe"
Write-Host ""
Write-Host "Run: scripts\windows\start.ps1"
