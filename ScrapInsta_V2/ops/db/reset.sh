#!/usr/bin/env bash

set -euo pipefail

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

# Cargar .env si existe (desde la raíz del proyecto)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
    success "Variables de entorno cargadas"
else
    error "No se encontró .env en $PROJECT_ROOT. Ejecuta primero: ./scripts/setup_local.sh"
fi

SCHEMA_PATH="$PROJECT_ROOT/ops/db/schema.sql"
DOCKER_DIR="$PROJECT_ROOT/docker"

echo "🧹 Reiniciando base de datos ScrapInsta..."
echo "-----------------------------------------"

# Verificar que docker compose esté disponible y el contenedor corriendo
if ! docker ps | grep -q "docker-db-1"; then
    error "El contenedor docker-db-1 no está corriendo. Inicia primero: ./scripts/start_local.sh"
fi

# Usar docker compose desde el directorio docker (como start_local.sh)
cd "$DOCKER_DIR"

# Drop + Create usando el usuario app (que tiene permisos)
info "Eliminando y recreando base de datos..."
docker compose exec -T db mysql -u"${DB_USER}" -p"${DB_PASS}" -e \
  "DROP DATABASE IF EXISTS \`${DB_NAME}\`; \
   CREATE DATABASE \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>&1 | grep -v "Warning" || true

# Aplicar schema
info "Aplicando schema..."
docker compose exec -T db mysql -u"${DB_USER}" -p"${DB_PASS}" "${DB_NAME}" < "$SCHEMA_PATH" 2>&1 | grep -v "Warning" || true

# Verificar tablas
echo "🔍 Verificando tablas creadas..."
docker compose exec -T db mysql -u"${DB_USER}" -p"${DB_PASS}" "${DB_NAME}" -e "SHOW TABLES;" 2>&1 | grep -v "Warning"

success "Base de datos limpia y recreada con éxito."
echo "-----------------------------------------"