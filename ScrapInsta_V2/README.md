# ScrapInsta V2

Sistema profesional y escalable para scraping, análisis y envío de mensajes en Instagram con soporte multi-tenant.

## ✨ Características Principales

### Funcionalidades Core
- **Analizar perfiles**: Obtener información de perfiles (seguidores, publicaciones, reels, engagement)
- **Extraer followings**: Obtener la lista de cuentas que sigue un usuario
- **Enviar mensajes**: Automatizar el envío de DMs con soporte para composición con IA

### Características Profesionales
- 🔐 **Multi-Tenancy**: Aislamiento completo de datos por cliente
- 🔑 **Autenticación JWT**: Tokens seguros con scopes y validación
- 🛡️ **Seguridad HTTPS**: Headers de seguridad, HSTS, CSP, CORS configurado
- ⚡ **Rate Limiting**: Control de tasa por cliente e IP
- 📊 **Observabilidad**: Logging estructurado (JSON) y métricas Prometheus
- 🏥 **Health Checks**: Endpoints `/health`, `/ready`, `/live`
- 🔄 **Exception Handlers**: Manejo centralizado y consistente de errores
- 🗄️ **Migraciones DB**: Alembic para gestión de esquema
- ✅ **Testing**: 320+ tests con 77%+ cobertura
- 📦 **Cola Externa**: Soporte para SQS FIFO o cola local

## Inicio rápido

### 1. Configuración inicial

```bash
# Copiar archivo de configuración
cp env.example .env

# Configurar cuentas de Instagram
# Edita: docker/secrets/instagram_accounts.json
```

### 2. Iniciar el sistema

```bash
./scripts/start_local.sh
```

Este script configura todo automáticamente:
- Entorno virtual Python
- Base de datos MySQL
- API (puerto 8000)
- Workers y dispatcher

### 3. Verificar que funciona

```bash
# Health check
curl http://localhost:8000/health

# Ver documentación interactiva
open http://localhost:8000/docs
```

## Uso de la API

### Autenticación

ScrapInsta V2 soporta dos métodos de autenticación:

#### 1. API Key (Simple)
```bash
X-Api-Key: TU_API_KEY
```

#### 2. JWT Token (Recomendado para producción)
```bash
# 1. Obtener token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"api_key": "TU_API_KEY"}'

# Respuesta:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "token_type": "bearer",
#   "expires_in": 3600,
#   "client_id": "client123"
# }

# 2. Usar token en requests
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Ejemplos

**Analizar un perfil:**
```bash
curl -X POST http://localhost:8000/ext/analyze/enqueue \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"usernames": ["usuario1", "usuario2"]}'
```

**Extraer followings:**
```bash
curl -X POST http://localhost:8000/ext/followings/enqueue \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "X-Account: tu_cuenta_cliente" \
  -H "Content-Type: application/json" \
  -d '{"target_username": "usuario_target", "limit": 50}'
```

**Consultar estado de un job:**
```bash
curl http://localhost:8000/jobs/JOB_ID/summary \
  -H "Authorization: Bearer TU_TOKEN"
```

**Pull de tareas (Workers):**
```bash
curl -X POST http://localhost:8000/api/send/pull \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "X-Account: worker_account" \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}'
```

## Configuración

### Variables principales (.env)

#### Base de Datos
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`: Configuración de MySQL

#### Autenticación y Seguridad
- `API_SHARED_SECRET`: Clave secreta para autenticación API (cambiar en producción)
- `REQUIRE_HTTPS`: Requerir HTTPS en producción (`true`/`false`)
- `CORS_ORIGINS`: Orígenes permitidos para CORS (separados por coma, vacío = deshabilitado)

#### Colas
- `QUEUES_BACKEND`: Backend de colas (`local` o `sqs`)
- `AWS_REGION`: Región de AWS (si usas SQS)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: Credenciales AWS (si usas SQS)

#### Observabilidad
- `LOG_LEVEL`: Nivel de logging (`INFO`, `DEBUG`, `WARNING`, `ERROR`)
- `LOG_FORMAT`: Formato de logs (`text` o `json`)

#### IA (Opcional)
- `OPENAI_API_KEY`: Para composición de mensajes con IA

### Cuentas Instagram

Edita `docker/secrets/instagram_accounts.json`:
```json
[
  {
    "username": "tu_cuenta",
    "password": "tu_password",
    "proxy": null
  }
]
```

## Monitoreo y Observabilidad

### Métricas Prometheus

```bash
# Resumen legible de métricas (JSON)
curl http://localhost:8000/metrics/summary | jq .

# Métricas en formato Prometheus (para scraping)
curl http://localhost:8000/metrics

# Métricas en formato JSON
curl http://localhost:8000/metrics/json | jq .
```

**Métricas disponibles:**
- `http_requests_total`: Total de requests HTTP por método, endpoint y status
- `http_request_duration_seconds`: Duración de requests
- `rate_limit_hits_total`: Hits de rate limiting
- `tasks_processed_total`: Tareas procesadas por workers
- `jobs_created_total`: Jobs creados
- Y más...

### Health Checks

```bash
# Health check básico (estado general)
curl http://localhost:8000/health

# Readiness (listo para recibir tráfico)
curl http://localhost:8000/ready

# Liveness (proceso vivo)
curl http://localhost:8000/live
```

### Logging Estructurado

Los logs están en formato estructurado (JSON en producción, texto en desarrollo):

```json
{
  "event": "request_completed",
  "level": "info",
  "method": "POST",
  "path": "/ext/analyze/enqueue",
  "status_code": 200,
  "duration_ms": 45.2,
  "request_id": "abc123",
  "trace_id": "xyz789",
  "client_id": "client123"
}
```

**Correlación de requests:**
- Cada request tiene un `X-Request-ID` único
- `X-Trace-ID` para rastrear requests relacionados
- Headers disponibles en respuestas para debugging

## Comandos útiles

```bash
# Ver logs
tail -f api.log dispatcher.log

# Probar API
./scripts/test_api.sh

# Probar observabilidad
./scripts/test_observability.sh

# Reiniciar base de datos
./ops/db/reset.sh
```

## Estructura del proyecto

```
src/scrapinsta/
├── application/          # Casos de uso y lógica de negocio
│   ├── dto/             # Data Transfer Objects
│   ├── services/        # Servicios de aplicación
│   └── use_cases/       # Casos de uso (analyze, fetch, send)
├── domain/              # Capa de dominio
│   ├── models/          # Modelos de dominio
│   └── ports/           # Interfaces (puertos)
├── infrastructure/      # Implementaciones concretas
│   ├── auth/            # Autenticación JWT
│   ├── db/              # Repositorios SQL
│   └── browser/         # Adaptador Selenium
├── interface/           # Capa de interfaz
│   ├── api.py           # API REST FastAPI
│   └── queues/          # Colas (local/SQS)
├── crosscutting/        # Concerns transversales
│   ├── exceptions.py     # Excepciones HTTP personalizadas
│   ├── logging_config.py # Logging estructurado
│   ├── metrics.py       # Métricas Prometheus
│   └── rate_limit.py    # Rate limiting
└── config/              # Configuración
```

## Documentación

### Guías Técnicas
- **Guía técnica**: [DEVELOPERGUIE.md](DEVELOPERGUIE.md)
- **Guía de métricas**: [docs/METRICAS_GUIA.md](docs/METRICAS_GUIA.md)
- **Migraciones de BD**: [docs/MIGRACIONES_BD.md](docs/MIGRACIONES_BD.md)
- **Seguridad HTTPS**: [docs/SEGURIDAD_HTTPS.md](docs/SEGURIDAD_HTTPS.md)

### Documentación de Sistema
- **Sistema Multi-Tenant**: [docs/SISTEMA_MULTI_TENANT.md](docs/SISTEMA_MULTI_TENANT.md)
- **Revisión Flujo Multi-Tenant**: [docs/REVISION_FLUJO_MULTI_TENANT.md](docs/REVISION_FLUJO_MULTI_TENANT.md)
- **Plan de Mejoras**: [MEJORAS_PROFESIONALES.md](MEJORAS_PROFESIONALES.md)

## Testing

```bash
# Ejecutar todos los tests
pytest -v

# Con cobertura
pytest --cov=src/scrapinsta --cov-report=html

# Solo tests de integración
pytest tests/integration/ -v

# Solo tests unitarios
pytest tests/unit/ -v
```

**Estado actual:**
- ✅ 320+ tests pasando
- ✅ 77%+ cobertura de código
- ✅ Tests de integración para API, autenticación, exception handlers
- ✅ Tests unitarios para lógica de negocio

## Seguridad

### Implementaciones de Seguridad

- 🔐 **HTTPS**: Validación y headers de seguridad (HSTS, CSP, X-Frame-Options)
- 🔑 **JWT**: Tokens seguros con expiración y scopes
- 🛡️ **Rate Limiting**: Protección contra abuso por cliente e IP
- 🚫 **CORS**: Configuración restrictiva (deshabilitado por defecto)
- 📝 **Exception Handlers**: Manejo seguro y consistente de errores
- 🔒 **Multi-Tenancy**: Aislamiento completo de datos por cliente

### Mejores Prácticas

⚠️ **Importante para producción**: 
- ✅ Cambia `API_SHARED_SECRET` por un valor seguro
- ✅ Habilita `REQUIRE_HTTPS=true` en producción
- ✅ Configura certificados SSL/TLS (Let's Encrypt, AWS ACM)
- ✅ Configura `CORS_ORIGINS` con dominios permitidos
- ✅ No incluyas credenciales reales en el repositorio
- ✅ Usa variables de entorno para secretos
- ✅ Rota tokens y API keys regularmente

Ver [SECURITY.md](SECURITY.md) y [docs/SEGURIDAD_HTTPS.md](docs/SEGURIDAD_HTTPS.md) para más detalles.

## Arquitectura

### Multi-Tenancy

ScrapInsta V2 está diseñado para soportar múltiples clientes con:
- Aislamiento completo de datos por `client_id`
- Límites configurables por cliente (`client_limits`)
- Validación de ownership en todos los endpoints
- Scopes JWT para control de acceso granular

### Rate Limiting

- Rate limiting por cliente (desde BD)
- Rate limiting por IP
- Límites configurables: `requests_per_minute`, `requests_per_hour`, `requests_per_day`
- Respuestas `429 Too Many Requests` cuando se excede

### Colas

Soporte para dos backends de cola:
- **Local**: Multiprocessing (desarrollo)
- **SQS**: AWS SQS FIFO (producción, distribuido)

Configuración mediante `QUEUES_BACKEND` en `.env`.

## Despliegue

### Requisitos

- Python 3.12+
- MySQL 8.0+
- (Opcional) Redis para rate limiting distribuido
- (Opcional) AWS SQS para colas distribuidas

### Producción

1. **Configurar variables de entorno**:
   ```bash
   REQUIRE_HTTPS=true
   CORS_ORIGINS=https://app.tudominio.com
   API_SHARED_SECRET=<secreto-seguro>
   ```

2. **Configurar certificados SSL/TLS**:
   - Let's Encrypt (gratis)
   - AWS Certificate Manager (si usas AWS)

3. **Configurar proxy reverso** (nginx/ALB):
   - Terminar HTTPS
   - Agregar `X-Forwarded-Proto: https`

4. **Migrar base de datos**:
   ```bash
   alembic upgrade head
   ```

Ver [docs/SEGURIDAD_HTTPS.md](docs/SEGURIDAD_HTTPS.md) para guía completa de producción.

## Licencia

MIT © 2025
