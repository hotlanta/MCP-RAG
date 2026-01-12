# --- Cleanup script for old PostgreSQL containers and volume ---

$containerName = "postgres-vector-db"
$volumeName = "postgres-rag-data"

Write-Host "Checking for old container '$containerName'..." -ForegroundColor Cyan

# Get container info (even if stopped)
$container = docker ps -a --filter "name=$containerName" --format "{{.ID}}"

if ($container) {
    Write-Host "Stopping container $containerName..." -ForegroundColor Yellow
    docker stop $container | Out-Null

    Write-Host "Removing container $containerName..." -ForegroundColor Yellow
    docker rm $container | Out-Null

    Write-Host "Container $containerName removed." -ForegroundColor Green
} else {
    Write-Host "No container named '$containerName' found." -ForegroundColor Green
}

# Check if the volume exists
$volume = docker volume ls --filter "name=$volumeName" --format "{{.Name}}"

if ($volume -eq $volumeName) {
    Write-Host "Removing volume '$volumeName'..." -ForegroundColor Yellow
    docker volume rm $volumeName | Out-Null
    Write-Host "Volume '$volumeName' removed." -ForegroundColor Green
} else {
    Write-Host "No volume named '$volumeName' found." -ForegroundColor Green
}

Write-Host "Cleanup complete." -ForegroundColor Cyan
