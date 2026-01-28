#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3307}"
DB_USER="${DB_USER:-app}"
DB_PASS="${DB_PASS:-app_password}"
DB_NAME="${DB_NAME:-scrapinsta}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

mkdir -p "${BACKUP_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/${DB_NAME}_${TS}.sql"

export MYSQL_PWD="${DB_PASS}"
mysqldump -h "${DB_HOST}" -P "${DB_PORT}" -u "${DB_USER}" "${DB_NAME}" > "${OUT}"
unset MYSQL_PWD

echo "Backup generado: ${OUT}"

