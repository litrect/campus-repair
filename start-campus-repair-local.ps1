$ErrorActionPreference = 'Stop'
$backendRoot = Join-Path $PSScriptRoot 'houduan'
$launcher = Join-Path $backendRoot 'scripts\start_backend.ps1'
$index = Join-Path $PSScriptRoot 'qianduan\campus-repair-frontend\dist\index.html'
$url = 'http://127.0.0.1:5000'

function Test-Backend {
    try {
        $health = Invoke-RestMethod -Uri "$url/api/health/ready" -TimeoutSec 3
        return ($health.code -eq 0)
    }
    catch { return $false }
}

try {
    if (-not (Test-Path -LiteralPath $launcher)) { throw "Backend launcher not found: $launcher" }
    if (-not (Test-Path -LiteralPath $index)) { throw 'Frontend is not built. Run npm run build in the frontend directory first.' }
    if (-not (Test-Backend)) {
        $listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
        if ($listener) { throw 'Port 5000 is occupied, but the system is not ready. Check the existing backend window.' }
        Write-Host 'Starting database and backend...'
        Start-Process powershell.exe -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', "`"$launcher`""
        ) -WorkingDirectory $backendRoot | Out-Null
        $deadline = (Get-Date).AddSeconds(40)
        while (-not (Test-Backend)) {
            if ((Get-Date) -ge $deadline) { throw 'Startup timed out. Check the backend window.' }
            Start-Sleep -Seconds 1
        }
    }
    Start-Process $url
    Write-Host "System opened: $url"
    Write-Host 'Keep the backend window open. Press Ctrl+C in that window to stop the backend.'
}
catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
