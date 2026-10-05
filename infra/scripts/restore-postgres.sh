#!/usr/bin/env sh
# Restores a backup made by backup-postgres.sh. Overwrites the current database contents.
set -eu
[ $# -eq 1 ] || { echo "usage: $0 backups/echo-<timestamp>.sql.gz"; exit 1; }
COMPOSE="docker compose --env-file .env -f infra/docker/docker-compose.yml"
gunzip -c "$1" | $COMPOSE exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" "$POSTGRES_DB"'
echo "Restored $1"
