#!/bin/bash
# Script para probar la API de ScrapInsta

set -e

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

# Cargar configuración del .env si existe
if [ -f .env ]; then
    source .env
    API_KEY=${API_SHARED_SECRET:-"tu_clave_secreta_super_segura_12345"}
else
    warn "No se encontró .env, usando valores por defecto"
    API_KEY="tu_clave_secreta_super_segura_12345"
fi

API_URL=${API_URL:-"http://localhost:8000"}
X_ACCOUNT=${X_ACCOUNT:-"scrapscrapiscraper"}
# Nuevos: cliente y su clave (modo multi-cliente)
CLIENT_ID=${CLIENT_ID:-"demo"}
CLIENT_KEY=${CLIENT_KEY:-${API_KEY}}
URL="${API_URL}"

echo "🧪 Probando API de ScrapInsta"
echo "============================="
echo "URL: $URL"
echo "API Key: ${API_KEY:0:10}..."
echo "X-Account: ${X_ACCOUNT}"
echo "X-Client-Id: ${CLIENT_ID}"
echo "X-Api-Key (cliente): ${CLIENT_KEY:0:6}..."
echo ""

# 1. Health Check
echo "1️⃣ Verificando health..."
HEALTH=$(curl -s "${URL}/health")
if command -v jq >/dev/null 2>&1; then
    if echo "$HEALTH" | jq -e '.ok==true' >/dev/null 2>&1; then
        info "API está viva"
    else
        error "API no responde correctamente: $HEALTH"
    fi
else
    if echo "$HEALTH" | grep -Eq '"ok":[[:space:]]*true'; then
        info "API está viva"
    else
        error "API no responde correctamente: $HEALTH"
    fi
fi

# 2. Crear Job de Fetch Followings
echo ""
echo "2️⃣ Creando job de fetch_followings..."
FETCH_JOB=$(curl -s -X POST "${URL}/ext/followings/enqueue" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: ${CLIENT_KEY}" \
  -H "X-Client-Id: ${CLIENT_ID}" \
  -H "X-Account: ${X_ACCOUNT}" \
  -d '{"target_username": "dr.larosa", "limit": 5}')

if echo "$FETCH_JOB" | grep -q "job_id"; then
    if command -v jq >/dev/null 2>&1; then
        FETCH_JOB_ID=$(echo "$FETCH_JOB" | jq -r '.job_id')
    else
        # Fallback sin jq: intentar Python y luego sed
        FETCH_JOB_ID=$(python3 - <<'PY' <<< "$FETCH_JOB"
import sys, json
try:
    print(json.loads(sys.stdin.read()).get('job_id',''))
except Exception:
    print('')
PY
)
        if [ -z "$FETCH_JOB_ID" ]; then
            FETCH_JOB_ID=$(echo "$FETCH_JOB" | sed -n 's/.*"job_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
        fi
    fi
    info "Job creado: $FETCH_JOB_ID"
else
    warn "Error creando job: $FETCH_JOB"
fi

# 3. Crear Job de Analyze Profile
echo ""
echo "3️⃣ Creando job de analyze_profile..."
ANALYZE_JOB=$(curl -s -X POST "${URL}/ext/analyze/enqueue" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: ${CLIENT_KEY}" \
  -H "X-Client-Id: ${CLIENT_ID}" \
  -d '{"usernames": ["instagram", "meta"], "batch_size": 10, "priority": 5}')

if echo "$ANALYZE_JOB" | grep -q "job_id"; then
    if command -v jq >/dev/null 2>&1; then
        ANALYZE_JOB_ID=$(echo "$ANALYZE_JOB" | jq -r '.job_id')
        ANALYZE_TOTAL=$(echo "$ANALYZE_JOB" | jq -r '.total_items')
    else
        ANALYZE_JOB_ID=$(python3 - <<'PY' <<< "$ANALYZE_JOB"
import sys, json
try:
    d=json.loads(sys.stdin.read()); print(d.get('job_id',''))
except Exception:
    print('')
PY
)
        if [ -z "$ANALYZE_JOB_ID" ]; then
            ANALYZE_JOB_ID=$(echo "$ANALYZE_JOB" | sed -n 's/.*"job_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
        fi
        ANALYZE_TOTAL=$(echo "$ANALYZE_JOB" | sed -n 's/.*"total_items"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        ANALYZE_TOTAL=${ANALYZE_TOTAL:-0}
    fi
    info "Job creado: $ANALYZE_JOB_ID (items: $ANALYZE_TOTAL)"
else
    warn "Error creando job: $ANALYZE_JOB"
fi

# 4. Verificar progreso de jobs
if [ -n "$FETCH_JOB_ID" ]; then
    echo ""
    echo "4️⃣ Verificando progreso de fetch job..."
    sleep 2
    SUMMARY=$(curl -s "${URL}/jobs/${FETCH_JOB_ID}/summary" \
      -H "X-Api-Key: ${CLIENT_KEY}" \
      -H "X-Client-Id: ${CLIENT_ID}")
    
    if command -v jq >/dev/null 2>&1; then
        QUEUED=$(echo "$SUMMARY" | jq -r '.queued // 0')
        SENT=$(echo "$SUMMARY" | jq -r '.sent // 0')
        OK=$(echo "$SUMMARY" | jq -r '.ok // 0')
        ERROR=$(echo "$SUMMARY" | jq -r '.error // 0')
    else
        QUEUED=$(echo "$SUMMARY" | sed -n 's/.*"queued"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        SENT=$(echo "$SUMMARY" | sed -n 's/.*"sent"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        OK=$(echo "$SUMMARY" | sed -n 's/.*"ok"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        ERROR=$(echo "$SUMMARY" | sed -n 's/.*"error"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        QUEUED=${QUEUED:-0}; SENT=${SENT:-0}; OK=${OK:-0}; ERROR=${ERROR:-0}
    fi
    
    info "Estado del job: queued=$QUEUED, sent=$SENT, ok=$OK, error=$ERROR"
fi

if [ -n "$ANALYZE_JOB_ID" ]; then
    echo ""
    echo "5️⃣ Verificando progreso de analyze job..."
    SUMMARY=$(curl -s "${URL}/jobs/${ANALYZE_JOB_ID}/summary" \
      -H "X-Api-Key: ${CLIENT_KEY}" \
      -H "X-Client-Id: ${CLIENT_ID}")
    
    if command -v jq >/dev/null 2>&1; then
        QUEUED=$(echo "$SUMMARY" | jq -r '.queued // 0')
        SENT=$(echo "$SUMMARY" | jq -r '.sent // 0')
        OK=$(echo "$SUMMARY" | jq -r '.ok // 0')
        ERROR=$(echo "$SUMMARY" | jq -r '.error // 0')
    else
        QUEUED=$(echo "$SUMMARY" | sed -n 's/.*"queued"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        SENT=$(echo "$SUMMARY" | sed -n 's/.*"sent"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        OK=$(echo "$SUMMARY" | sed -n 's/.*"ok"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        ERROR=$(echo "$SUMMARY" | sed -n 's/.*"error"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')
        QUEUED=${QUEUED:-0}; SENT=${SENT:-0}; OK=${OK:-0}; ERROR=${ERROR:-0}
    fi
    
    info "Estado del job: queued=$QUEUED, sent=$SENT, ok=$OK, error=$ERROR"
fi

echo ""
echo "✅ Pruebas completadas"
echo ""
echo "💡 Tips:"
echo "- Revisa los logs del dispatcher para ver el progreso de los jobs"
echo "- Consulta la DB para ver los resultados: docker compose -f docker/docker-compose.yml exec db mysql -u app -papp_password scrapinsta"
echo "- Usa la documentación interactiva: ${URL}/docs"

