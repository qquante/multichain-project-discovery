# PowerShell script to manage Docker services
param(
    [Parameter(Position=0)]
    [ValidateSet("up", "down", "logs", "status", "build", "restart", "clean")]
    [string]$Action = "up"
)

switch ($Action) {
    "up" {
        Write-Host "Starting all services..." -ForegroundColor Green
        docker-compose up -d --build
        Write-Host "`nServices started. Use 'logs' to view output." -ForegroundColor Cyan
    }
    "down" {
        Write-Host "Stopping all services..." -ForegroundColor Yellow
        docker-compose down
    }
    "logs" {
        Write-Host "Showing logs (Ctrl+C to exit)..." -ForegroundColor Cyan
        docker-compose logs -f
    }
    "status" {
        Write-Host "Service status:" -ForegroundColor Cyan
        docker-compose ps
    }
    "build" {
        Write-Host "Building images..." -ForegroundColor Green
        docker-compose build
    }
    "restart" {
        Write-Host "Restarting services..." -ForegroundColor Yellow
        docker-compose restart
    }
    "clean" {
        Write-Host "Stopping and removing all containers, volumes..." -ForegroundColor Red
        docker-compose down -v
        docker system prune -f
    }
}

Write-Host "`nDone!" -ForegroundColor Green

