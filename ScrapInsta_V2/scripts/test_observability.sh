#!/usr/bin/env bash
# Script para probar la observabilidad implementada
# - Logging estructurado
# - Métricas Prometheus
# - Health checks mejorados

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
API_KEY="${API_SHARED_SECRET:-test_key}"

echo "🧪 Probando Observabilidad de ScrapInsta"
echo "========================================"
echo ""

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Verificar que la API esté corriendo
echo -e "${BLUE}1️⃣ Verificando que la API esté corriendo...${NC}"
if ! curl -s "${API_URL}/health" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  La API no está corriendo. Iníciala con:${NC}"
    echo "   ./scripts/start_local.sh"
    echo "   o"
    echo "   PYTHONPATH=src python -m uvicorn scrapinsta.interface.api:app --host 0.0.0.0 --port 8000"
    exit 1
fi
echo -e "${GREEN}✓ API está corriendo${NC}"
echo ""

# 2. Probar Health Checks
echo -e "${BLUE}2️⃣ Probando Health Checks...${NC}"
echo ""

echo "   GET /health:"
curl -s "${API_URL}/health" | jq . || curl -s "${API_URL}/health"
echo ""
echo ""

echo "   GET /ready:"
curl -s "${API_URL}/ready" | jq . || curl -s "${API_URL}/ready"
echo ""
echo ""

echo "   GET /live:"
curl -s "${API_URL}/live" | jq . || curl -s "${API_URL}/live"
echo ""
echo ""

# 3. Probar Métricas Prometheus
echo -e "${BLUE}3️⃣ Probando Métricas Prometheus...${NC}"
echo ""

echo "   GET /metrics/summary (JSON legible - RECOMENDADO):"
curl -s "${API_URL}/metrics/summary" | python3 -m json.tool 2>/dev/null || curl -s "${API_URL}/metrics/summary"
echo ""
echo ""

echo "   GET /metrics/json (Todas las métricas en JSON):"
curl -s "${API_URL}/metrics/json" | python3 -m json.tool 2>/dev/null | head -n 40 || curl -s "${API_URL}/metrics/json" | head -n 40
echo ""
echo ""

echo "   GET /metrics (Formato Prometheus - para scraping):"
echo "   (Mostrando primeras 20 líneas)"
curl -s "${API_URL}/metrics" | head -n 20
echo ""
echo ""

# 4. Generar tráfico para ver métricas
echo -e "${BLUE}4️⃣ Generando tráfico para ver métricas...${NC}"
echo ""

for i in {1..5}; do
    echo "   Request $i..."
    curl -s "${API_URL}/health" > /dev/null
    sleep 0.5
done

echo ""
echo "   Métricas después de 5 requests:"
curl -s "${API_URL}/metrics" | grep -E "http_requests_total|http_request_duration" | head -n 10
echo ""
echo ""

# 5. Probar logging estructurado
echo -e "${BLUE}5️⃣ Verificando Logging Estructurado...${NC}"
echo ""

if [ -f "api.log" ]; then
    echo "   Últimas 10 líneas de api.log:"
    tail -n 10 api.log
    echo ""
    echo "   Para ver logs en tiempo real:"
    echo "   tail -f api.log"
else
    echo "   ⚠️  No se encontró api.log"
    echo "   Los logs deberían estar en la salida de uvicorn"
fi
echo ""

# 6. Probar con formato JSON
echo -e "${BLUE}6️⃣ Probando con LOG_FORMAT=json...${NC}"
echo ""
echo "   Para ver logs en formato JSON, reinicia la API con:"
echo "   LOG_FORMAT=json PYTHONPATH=src python -m uvicorn scrapinsta.interface.api:app --host 0.0.0.0 --port 8000"
echo ""

# 7. Probar endpoint con autenticación (para ver request ID)
echo -e "${BLUE}7️⃣ Probando endpoint con autenticación (para ver Request ID)...${NC}"
echo ""

RESPONSE=$(curl -s -i "${API_URL}/jobs/test_job/summary" \
    -H "X-Api-Key: ${API_KEY}" 2>&1)

echo "   Headers de respuesta:"
echo "$RESPONSE" | grep -E "X-Request-ID|X-Trace-ID" || echo "   (No se encontraron headers de correlación)"
echo ""

# 8. Resumen
echo -e "${GREEN}✅ Pruebas completadas${NC}"
echo ""
echo "📊 Endpoints disponibles:"
echo "   - GET ${API_URL}/health          - Health check básico"
echo "   - GET ${API_URL}/ready           - Readiness check (Kubernetes)"
echo "   - GET ${API_URL}/live            - Liveness check (Kubernetes)"
echo "   - GET ${API_URL}/metrics         - Métricas Prometheus (formato estándar)"
echo "   - GET ${API_URL}/metrics/json    - Métricas en JSON completo"
echo "   - GET ${API_URL}/metrics/summary - Resumen de métricas (JSON legible) ⭐"
echo ""
echo "📝 Para ver logs estructurados:"
echo "   tail -f api.log"
echo ""
echo "📈 Para ver métricas en formato Prometheus:"
echo "   curl ${API_URL}/metrics"
echo ""
echo "🔍 Para probar con formato JSON:"
echo "   LOG_FORMAT=json PYTHONPATH=src python -m uvicorn scrapinsta.interface.api:app --host 0.0.0.0 --port 8000"

