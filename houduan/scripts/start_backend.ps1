$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the project Python environment first.' }
& $pythonPath (Join-Path $PSScriptRoot 'local_mysql.py') start
if ($LASTEXITCODE -ne 0) { throw 'MySQL startup failed.' }
& $pythonPath (Join-Path $PSScriptRoot 'run_server.py')
if ($LASTEXITCODE -ne 0) { throw 'API server failed.' }
