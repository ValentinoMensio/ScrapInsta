set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

echo "🚀 Iniciando ScrapInsta V2"
echo "=========================="
echo ""

# Cargar .env si existe
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    success "Variables de entorno cargadas"
else
    error "No se encontró .env. Ejecuta primero: ./scripts/setup_local.sh"
fi

# Verificar que estemos en la raíz
if [ ! -f "requirements.txt" ]; then
    error "Ejecuta este script desde la raíz del proyecto"
fi

# 0. Setup del entorno virtual
echo "0️⃣ Configurando entorno virtual..."

# Detectar si ya existe .venv
if [ ! -d ".venv" ]; then
    warn "No existe .venv, creándolo..."
    python3 -m venv .venv
    success "Entorno virtual creado"
else
    info "Entorno virtual existente"
fi

# Activar el entorno virtual
source .venv/bin/activate

# Verificar que funciona
if [ -z "$VIRTUAL_ENV" ]; then
    error "No se pudo activar el entorno virtual"
fi

success "Entorno virtual activado: $VIRTUAL_ENV"

# Usar siempre el Python del venv para pip/uvicorn/etc
PY="$VIRTUAL_ENV/bin/python"

# Si el venv está roto (p.ej. moviste la carpeta), recrearlo
if [ ! -x "$PY" ]; then
    warn "El venv parece estar roto (no existe $PY). Recreando..."
    deactivate || true
    rm -rf .venv
    python3 -m venv .venv || error "No se pudo crear .venv"
    source .venv/bin/activate || error "No se pudo activar .venv"
    success "Entorno virtual recreado: $VIRTUAL_ENV"
    PY="$VIRTUAL_ENV/bin/python"
fi

# Verificar e instalar dependencias
echo ""
echo "1️⃣ Verificando dependencias..."
if ! "$PY" -c "import pymysql, selenium, pydantic, fastapi, uvicorn" 2>/dev/null; then
    warn "Algunas dependencias no están instaladas. Instalando..."
    "$PY" -m pip install -U pip setuptools wheel || error "Error actualizando pip en venv."
    "$PY" -m pip install -r requirements.txt || error "Error instalando dependencias."
    success "Dependencias instaladas"
else
    success "Dependencias verificadas"
fi

# Función para limpiar procesos al salir
cleanup() {
    echo ""
    warn "Cerrando procesos..."
    pkill -f "scrapinsta.interface.dispatcher" || true
    pkill -f "uvicorn.*api" || true
}

trap cleanup EXIT INT TERM

# 2. Levantar base de datos y Redis
echo ""
echo "2️⃣ Iniciando base de datos y Redis..."
cd docker
docker compose up -d db redis

# Esperar a que MySQL esté listo
echo "   Esperando a que MySQL esté listo..."
for i in {1..30}; do
    if docker compose exec -T db mysqladmin ping -h localhost --silent 2>/dev/null; then
        success "MySQL está listo"
        break
    fi
    if [ $i -eq 30 ]; then
        error "MySQL no respondió a tiempo"
    fi
    sleep 1
done

# Aplicar migraciones con Alembic si es necesario
echo "   Aplicando migraciones..."
if ! docker compose exec -T db mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "SELECT 1 FROM jobs LIMIT 1" > /dev/null 2>&1; then
    warn "Base de datos vacía, aplicando migraciones..."
    cd ..
    source .venv/bin/activate 2>/dev/null || true
    alembic upgrade head 2>/dev/null || true
    cd "$DOCKER_DIR"
    success "Migraciones aplicadas"
else
    info "Base de datos ya tiene datos"
fi

# Esperar a que Redis esté listo
echo "   Esperando a que Redis esté listo..."
for i in {1..15}; do
    if docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
        success "Redis está listo"
        break
    fi
    if [ $i -eq 15 ]; then
        warn "Redis no respondió, pero continuando (el caché estará deshabilitado)"
    fi
    sleep 1
done

cd ..

# 3. Iniciar API
echo ""
echo "3️⃣ Iniciando API FastAPI..."

# Configurar variables de entorno
export PYTHONPATH=src
export API_SHARED_SECRET=${API_SHARED_SECRET}
export OPENAI_API_KEY=${OPENAI_API_KEY:-""}

# Iniciar API en background con PYTHONPATH desde el venv
PYTHONPATH=src "$PY" -m uvicorn scrapinsta.interface.api:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
API_PID=$!

# Esperar a que la API esté lista
echo "   Esperando a que la API esté lista..."
sleep 2  # Dar tiempo inicial para que uvicorn inicie

for i in {1..20}; do
    # Probar con 127.0.0.1 (más seguro que localhost)
    HEALTH_RESPONSE=$(curl -s http://127.0.0.1:8000/health 2>/dev/null)
    
    # Verificar que devuelva JSON con "ok"
    if echo "$HEALTH_RESPONSE" | grep -qi '"ok"'; then
        success "API corriendo en http://127.0.0.1:8000 (PID: $API_PID)"
        info "Logs de API: tail -f api.log"
        break
    fi
    
    if [ $i -eq 20 ]; then
        warn "API no respondió a tiempo."
        if [ -n "$HEALTH_RESPONSE" ]; then
            warn "Última respuesta: $HEALTH_RESPONSE"
        else
            warn "No hay respuesta del servidor"
        fi
        warn "Revisando logs..."
        tail -n 50 api.log
        error "API no inició correctamente. Revisa api.log para más detalles"
    fi
    sleep 1
done

# 4. Iniciar Dispatcher
echo ""
echo "4️⃣ Iniciando Dispatcher y Workers..."

export SECRET_ACCOUNTS_PATH=${SECRET_ACCOUNTS_PATH:-"docker/secrets/instagram_accounts.json"}

# Iniciar dispatcher en background con PYTHONPATH desde el venv
PYTHONPATH=src "$PY" -m scrapinsta.interface.dispatcher > dispatcher.log 2>&1 &
DISPATCHER_PID=$!
sleep 3

# Verificar que el dispatcher esté corriendo
if ps -p $DISPATCHER_PID > /dev/null; then
    success "Dispatcher corriendo (PID: $DISPATCHER_PID)"
    info "Logs de Dispatcher: tail -f dispatcher.log"
else
    warn "Dispatcher no inició. Revisando logs..."
    tail -n 50 dispatcher.log
    error "Dispatcher no inició correctamente. Revisa dispatcher.log para más detalles"
fi

# Resumen
echo ""
echo "✅ Sistema iniciado correctamente"
echo ""
echo "📊 Servicios corriendo:"
echo "  - Entorno virtual: $VIRTUAL_ENV"
# CORRECCIÓN: Usar la variable del puerto de host
echo "  - Base de datos: MySQL en puerto ${DB_PORT:-3307}"
echo "  - API: http://localhost:8000"
echo "  - Dispatcher: PID $DISPATCHER_PID"
echo ""
echo "🔗 URLs útiles:"
echo "  - Documentación API: http://localhost:8000/docs"
echo "  - Health check: http://localhost:8000/health"
echo ""
echo "📝 Comandos útiles:"
echo "  - Ver logs API: tail -f api.log"
echo "  - Ver logs Dispatcher: tail -f dispatcher.log"
echo "  - Probar API: ./scripts/test_api.sh"
echo "  - Detener sistema: Ctrl+C"
echo ""
echo "⚠️  Presiona Ctrl+C para detener todos los servicios"

# Mantener script corriendo
wait