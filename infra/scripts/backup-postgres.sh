#!/usr/bin/env sh
# Dumps the ECHO Postgres database to backups/echo-<timestamp>.sql.gz (run from the repository root).
# Restore: infra/scripts/restore-postgres.sh backups/echo-<timestamp>.sql.gz
set -eu
COMPOSE="docker compose --env-file .env -f infra/docker/docker-compose.yml"
mkdir -p backups
FILE="backups/echo-$(date +%Y%m%d-%H%M%S).sql.gz"
$COMPOSE exec -T postgres sh -c 'pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$FILE"
echo "Backup written to $FILE"
# keep the 14 most recent backups
ls -1t backups/echo-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
