<#
.SYNOPSIS
    Phase 7.1: Installs and configures Arush Manager Agent as a 24/7 Windows Service using NSSM (Non-Sucking Service Manager).
.DESCRIPTION
    Configures automatic start on boot, automatic restart on crash (5000ms delay),
    and rotated stdout/stderr logs in data/logs/.
#>
param(
    [string]$ServiceName = "ArushManagerAgent",
    [string]$ProjectDir = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$PythonExe = "python.exe",
    [string]$NssmExe = "nssm.exe"
)

$ErrorActionPreference = "Stop"

# Check for Administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "⚠️ Administrator privileges required to install Windows Services." -ForegroundColor Yellow
    Write-Host "🚀 Requesting elevation via UAC..." -ForegroundColor Cyan
    $scriptPath = $MyInvocation.MyCommand.Definition
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -ServiceName `"$ServiceName`" -ProjectDir `"$ProjectDir`" -PythonExe `"$PythonExe`" -NssmExe `"$NssmExe`""
    exit
}
$LogDir = Join-Path $ProjectDir "data\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "🚀 Installing Windows Service '$ServiceName' via NSSM..." -ForegroundColor Cyan

& $NssmExe install $ServiceName $PythonExe "run.py"
& $NssmExe set $ServiceName AppDirectory $ProjectDir
& $NssmExe set $ServiceName Description "Arush Manager Agent — 24/7 Personal Co-Founder, Vault & Windows Automation"
& $NssmExe set $ServiceName Start SERVICE_AUTO_START
& $NssmExe set $ServiceName AppExit Default Restart
& $NssmExe set $ServiceName AppRestartDelay 5000
& $NssmExe set $ServiceName AppStdout (Join-Path $LogDir "service_stdout.log")
& $NssmExe set $ServiceName AppStderr (Join-Path $LogDir "service_stderr.log")
& $NssmExe set $ServiceName AppRotateFiles 1
& $NssmExe set $ServiceName AppRotateBytes 10485760

& $NssmExe start $ServiceName
Write-Host "✅ Service '$ServiceName' installed and started!" -ForegroundColor Green
Start-Sleep -Seconds 3
