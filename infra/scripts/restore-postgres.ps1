# Restores a backup made by backup-postgres.ps1 (overwrites the current database). Usage: restore-postgres.ps1 backups\echo-<ts>.sql
param([Parameter(Mandatory = $true)][string]$File)
$ErrorActionPreference = 'Stop'
$compose = @('compose', '--env-file', '.env', '-f', 'infra/docker/docker-compose.yml')
docker @compose cp $File postgres:/tmp/echo-restore.sql
docker @compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -f /tmp/echo-restore.sql "$POSTGRES_DB" && rm -f /tmp/echo-restore.sql'
Write-Host "Restored $File"
