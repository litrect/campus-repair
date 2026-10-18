param(
    [Parameter(Mandatory=$true)][string]$Mysql,
    [string]$DbHost = '127.0.0.1',
    [int]$Port = 3306,
    [string]$User = 'root',
    [string]$Database = 'campus_repair'
)
$ErrorActionPreference = 'Stop'
if ($Database -notmatch '^[A-Za-z][A-Za-z0-9_]{0,63}$') { throw 'Invalid database name.' }
$mysqlPath = (Resolve-Path -LiteralPath $Mysql).Path
$sqlRoot = Join-Path $PSScriptRoot '..\sql'
$clientArgs = @('--no-defaults','--protocol=TCP',"--host=$DbHost", "--port=$Port", "--user=$User", '--default-character-set=utf8mb4','--batch','--skip-column-names')
function Invoke-DatabaseSql([string]$Sql) {
    $Sql | & $mysqlPath @clientArgs
    if ($LASTEXITCODE -ne 0) { throw 'MySQL operation failed; inspect existing objects before retrying.' }
}
$previousEncoding = $OutputEncoding
try {
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $versionText = Invoke-DatabaseSql 'SELECT VERSION();'
    if ($versionText -notmatch '^(\d+)\.(\d+)\.(\d+)' -or $versionText -match 'MariaDB') { throw 'MySQL 8.0.16+ is required.' }
    if ([version]$Matches[0] -lt [version]'8.0.16') { throw 'MySQL 8.0.16+ is required.' }
    $exists = Invoke-DatabaseSql "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='$Database';"
    if ($exists.Trim() -ne '0') { throw 'Target database already exists. Choose a new name; existing data will not be changed.' }
    $schema = Get-Content -LiteralPath (Join-Path $sqlRoot 'schema.sql') -Raw -Encoding UTF8
    $seed = Get-Content -LiteralPath (Join-Path $sqlRoot 'seed.sql') -Raw -Encoding UTF8
    Invoke-DatabaseSql ($schema.Replace('campus_repair', $Database))
    Invoke-DatabaseSql ($seed.Replace('campus_repair', $Database))
    Invoke-DatabaseSql "USE $Database; SHOW TABLES; SELECT id,username,role,is_active FROM user;"
} finally {
    $OutputEncoding = $previousEncoding
}
