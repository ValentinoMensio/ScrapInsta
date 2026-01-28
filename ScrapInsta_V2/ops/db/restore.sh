#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 <backup.sql>"
  exit 1
fi

BACKUP_FILE="$1"
if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "No existe el archivo: ${BACKUP_FILE}"
  exit 1
fi

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3307}"
DB_USER="${DB_USER:-app}"
DB_PASS="${DB_PASS:-app_password}"
DB_NAME="${DB_NAME:-scrapinsta}"

export MYSQL_PWD="${DB_PASS}"
mysql -h "${DB_HOST}" -P "${DB_PORT}" -u "${DB_USER}" "${DB_NAME}" < "${BACKUP_FILE}"
unset MYSQL_PWD

echo "Restore completado desde: ${BACKUP_FILE}"

