# Windows PowerShell version of backup-postgres.sh. Run from the repository root.
# The dump is written inside the container and copied out byte-for-byte (PowerShell 5 pipes would re-encode it).
$ErrorActionPreference = 'Stop'
$compose = @('compose', '--env-file', '.env', '-f', 'infra/docker/docker-compose.yml')
New-Item -ItemType Directory -Force backups | Out-Null
$file = "backups/echo-$(Get-Date -Format yyyyMMdd-HHmmss).sql"
docker @compose exec -T postgres sh -c 'pg_dump --clean --if-exists -U "$POSTGRES_USER" -f /tmp/echo-backup.sql "$POSTGRES_DB"'
docker @compose cp postgres:/tmp/echo-backup.sql $file
docker @compose exec -T postgres rm -f /tmp/echo-backup.sql
Write-Host "Backup written to $file"
Get-ChildItem backups/echo-*.sql | Sort-Object LastWriteTime -Descending | Select-Object -Skip 14 | Remove-Item
