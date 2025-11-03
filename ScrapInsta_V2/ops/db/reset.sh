#!/usr/bin/env bash
# Cargar .env si existe
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    success "Variables de entorno cargadas"
else
    error "No se encontró .env. Ejecuta primero: ./scripts/setup_local.sh"
fi


set -euo pipefail

DB_CONTAINER="docker-db-1"          # ajustá si tu nombre difiere
SCHEMA_PATH="ops/db/schema.sql"

echo "🧹 Reiniciando base de datos ScrapInsta..."
echo "-----------------------------------------"

# Copiar schema al contenedor (para no pipear desde el host)
echo "📦 Copiando schema al contenedor..."
docker cp "$SCHEMA_PATH" "$DB_CONTAINER:/schema.sql"

# Drop + Create usando variables DENTRO del contenedor
# (Usa MYSQL_ROOT_PASSWORD)
docker exec -i "$DB_CONTAINER" bash -lc '
  set -euo pipefail
  mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e \
    "DROP DATABASE IF EXISTS \`$MYSQL_DATABASE\`; \
     CREATE DATABASE \`$MYSQL_DATABASE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
'

# Aplicar schema desde el archivo que ya copiamos
# (Usa MYSQL_ROOT_PASSWORD)
docker exec -i "$DB_CONTAINER" bash -lc '
  set -euo pipefail
  mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" < /schema.sql
'

# Verificar tablas
echo "🔍 Verificando tablas creadas..."
# --- CORRECCIÓN ---
# Usar 'root' (igual que los pasos anteriores) en lugar de '$MYSQL_USER'
docker exec -i "$DB_CONTAINER" bash -lc '
  set -euo pipefail
  mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SHOW TABLES;"
'

echo "✅ Base de datos limpia y recreada con éxito."
echo "-----------------------------------------"