<#
.SYNOPSIS
    Phase 7.1: Registers Arush Manager Agent in Windows Task Scheduler to launch automatically at user logon
    (required for interactive desktop GUI access with mss + pyautogui).
#>
param(
    [string]$TaskName = "ArushManagerAgent_AutoStart",
    [string]$ProjectDir = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$PythonExe = "python.exe"
)

$ErrorActionPreference = "Stop"

# Check for Administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "⚠️ Administrator privileges required to register Scheduled Tasks." -ForegroundColor Yellow
    Write-Host "🚀 Requesting elevation via UAC..." -ForegroundColor Cyan
    $scriptPath = $MyInvocation.MyCommand.Definition
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -TaskName `"$TaskName`" -ProjectDir `"$ProjectDir`" -PythonExe `"$PythonExe`""
    exit
}

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "run.py" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Launches Arush Manager Agent on Windows logon with automatic self-healing restarts." `
    -Force

Write-Host "✅ Scheduled Task '$TaskName' registered in Windows Task Scheduler!" -ForegroundColor Green
Start-Sleep -Seconds 3
