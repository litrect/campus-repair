param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$workspaceRoot = $PSScriptRoot
$backendRoot = Join-Path $workspaceRoot 'houduan'
$backendLauncher = Join-Path $backendRoot 'scripts\start_backend.ps1'
$frontendRoot = Join-Path $workspaceRoot 'qianduan\campus-repair-frontend'
$frontendIndex = Join-Path $frontendRoot 'dist\index.html'
$cpolarExe = 'C:\Program Files\cpolar\cpolar.exe'
$cpolarConfig = Join-Path $env:USERPROFILE '.cpolar\cpolar.yml'
$tunnelName = 'choujiang'
$localHealthUrl = 'http://127.0.0.1:5000/api/health'

$publicUrl = (Read-Host 'Enter the cpolar public URL (for example: http://xxxx.cpolar.top)').Trim()
$parsedPublicUrl = $null
if (-not [Uri]::TryCreate($publicUrl, [UriKind]::Absolute, [ref]$parsedPublicUrl) -or
    $parsedPublicUrl.Scheme -notin @('http', 'https') -or
    [string]::IsNullOrWhiteSpace($parsedPublicUrl.Host)) {
    Write-Host 'Invalid URL. Please enter a complete http:// or https:// address.' -ForegroundColor Red
    Read-Host 'Press Enter to close this window' | Out-Null
    exit 1
}
$publicUrl = $parsedPublicUrl.GetLeftPart([UriPartial]::Authority).TrimEnd('/')

function Wait-Url {
    param(
        [Parameter(Mandatory)] [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

function Set-CpolarTunnelPort {
    param(
        [Parameter(Mandatory)] [string]$ConfigPath,
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [int]$Port
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in [System.IO.File]::ReadAllLines($ConfigPath)) {
        $lines.Add($line)
    }

    $insideTunnel = $false
    $tunnelFound = $false
    $addressFound = $false

    for ($index = 0; $index -lt $lines.Count; $index++) {
        $line = $lines[$index]

        if ($line -match '^  ([A-Za-z0-9_-]+):\s*$') {
            $insideTunnel = ($Matches[1] -eq $Name)
            if ($insideTunnel) {
                $tunnelFound = $true
            }
            continue
        }

        if ($insideTunnel -and $line -match '^    addr:\s*') {
            $lines[$index] = "    addr: `"$Port`""
            $addressFound = $true
            break
        }
    }

    if (-not $tunnelFound) {
        throw "Tunnel not found in cpolar config: $Name"
    }
    if (-not $addressFound) {
        throw "Tunnel $Name has no addr setting."
    }

    $backupPath = "$ConfigPath.campus-repair-backup"
    if (-not (Test-Path -LiteralPath $backupPath)) {
        Copy-Item -LiteralPath $ConfigPath -Destination $backupPath
    }
    [System.IO.File]::WriteAllLines(
        $ConfigPath,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

try {
    Write-Host 'Starting Campus Repair System...' -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $backendLauncher)) {
        throw "Backend launcher not found: $backendLauncher"
    }
    if (-not (Test-Path -LiteralPath $frontendIndex)) {
        throw 'Frontend is not built. Run npm run build in the frontend directory first.'
    }
    if (-not (Test-Path -LiteralPath $cpolarExe)) {
        throw "cpolar executable not found: $cpolarExe"
    }
    if (-not (Test-Path -LiteralPath $cpolarConfig)) {
        throw "cpolar config not found: $cpolarConfig"
    }

    $backendReady = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
    if (-not $backendReady) {
        Write-Host '1/4 Starting database and backend...'
        Start-Process powershell.exe -ArgumentList @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-NoExit',
            '-File', "`"$backendLauncher`""
        ) -WorkingDirectory $backendRoot | Out-Null
    }
    else {
        Write-Host '1/4 Backend is already running.'
    }

    if (-not (Wait-Url -Url $localHealthUrl -TimeoutSeconds 35)) {
        throw 'Backend did not start within 35 seconds. Check the backend window.'
    }

    Write-Host '2/4 Starting the frontend gateway on port 5173...'
    Set-CpolarTunnelPort -ConfigPath $cpolarConfig -Name $tunnelName -Port 5173

    $frontendReady = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    if (-not $frontendReady) {
        $npmCommand = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
        if (-not $npmCommand) {
            throw 'npm.cmd was not found.'
        }
        Start-Process -FilePath $npmCommand -ArgumentList @('run', 'preview') `
            -WorkingDirectory $frontendRoot -WindowStyle Minimized | Out-Null
    }

    if (-not (Wait-Url -Url 'http://127.0.0.1:5173' -TimeoutSeconds 20)) {
        throw 'Frontend gateway did not start within 20 seconds.'
    }

    Write-Host '3/4 Checking the cpolar tunnel...'
    $cpolarRunning = Get-Process cpolar -ErrorAction SilentlyContinue

    if (-not $cpolarRunning) {
        Start-Process -FilePath $cpolarExe -ArgumentList @('start', $tunnelName) -WindowStyle Minimized | Out-Null
    }
    else {
        Write-Host 'The cpolar tunnel is already running.'
    }

    if (-not (Wait-Url -Url $publicUrl -TimeoutSeconds 20)) {
        throw "The specified public URL is unavailable. The free cpolar URL may have changed: $publicUrl"
    }

    Write-Host '4/4 System started successfully.' -ForegroundColor Green
    Write-Host "Local URL:  http://127.0.0.1:5000"
    Write-Host "Public URL: $publicUrl"

    if (-not $NoBrowser) {
        Start-Sleep -Seconds 2
        Start-Process $publicUrl
    }

    Write-Host 'You may close this window. Keep the backend window open.'
}
catch {
    Write-Host ''
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Press Enter to close this window.'
    Read-Host | Out-Null
    exit 1
}
