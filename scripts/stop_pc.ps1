#!/usr/bin/env pwsh
# Avatar - stop and remove the running container (Windows / PowerShell).
$ErrorActionPreference = "Stop"

$Container = "avatar"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker not found."
    exit 1
}

$existing = docker ps -aq -f "name=^$Container$"
if ($existing) {
    Write-Host "Stopping and removing '$Container'..."
    docker rm -f $Container | Out-Null
    Write-Host "Stopped."
} else {
    Write-Host "No '$Container' container is running."
}
