#!/usr/bin/env pwsh
# Avatar - build and run the single container (Windows / PowerShell).
# Stops any existing 'avatar' container, rebuilds the image, then runs it on :8000
# with the project-root .env. Open http://localhost:8000 (admin at /admin).
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = (Resolve-Path (Join-Path $ScriptDir "..")).Path

$Image     = "avatar"
$Container = "avatar"
$Port      = 8000

# Ensure Docker is available and running.
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker not found - install Docker Desktop and ensure it's running."
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker daemon is not running - start Docker Desktop first."
    exit 1
}

$EnvFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing .env at repo root ($EnvFile). Copy .env.example to .env and fill it in."
    exit 1
}

# 1. Stop and remove any existing container (ignore if absent).
$existing = docker ps -aq -f "name=^$Container$"
if ($existing) {
    Write-Host "Stopping existing '$Container' container..."
    docker rm -f $Container | Out-Null
}

# 2. Rebuild the image.
Write-Host "Building image '$Image'..."
docker build -t $Image -f (Join-Path $RepoRoot "Dockerfile") $RepoRoot
if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed."; exit 1 }

# 3. Run it with the root .env.
Write-Host "Starting '$Container' on http://localhost:$Port ..."
docker run -d `
    --name $Container `
    -p "$($Port):8000" `
    --env-file $EnvFile `
    --restart unless-stopped `
    $Image
if ($LASTEXITCODE -ne 0) { Write-Error "Docker run failed."; exit 1 }

Write-Host "Avatar is running:"
Write-Host "  Visitor: http://localhost:$Port"
Write-Host "  Admin:   http://localhost:$Port/admin"
Write-Host "Logs: docker logs -f $Container   |   Stop: ./scripts/stop_pc.ps1"
