# ScrapInsta V2

Sistema profesional para scraping, análisis y envío de mensajes en Instagram con soporte multi-tenant.

## Estado actual
- Arquitectura modular con capas `application/domain/infrastructure/interface`.
- Refactorizaciones clave completadas: routers, autenticación/rate limiting, handler de excepciones, dispatcher y caché.
- Tests y cobertura disponibles en el repo (último estado reportado: suite estable).

## Características principales
- **Analizar perfiles** (seguidores, publicaciones, reels y engagement).
- **Extraer followings**.
- **Enviar mensajes** con soporte para IA.
- **Multi-tenancy**, **JWT**, **rate limiting**, **observabilidad**, **health checks**.
- **Colas**: local o SQS FIFO.
- **Leasing con TTL** para recuperación de tareas.

## Inicio rápido

```bash
cp env.example .env
./scripts/start_local.sh
```

Verificar:
```bash
curl http://localhost:8000/health
open http://localhost:8000/docs
```

## Uso de la API (mínimo)

Obtener token:
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"api_key": "TU_API_KEY"}'
```

Analizar perfiles:
```bash
curl -X POST http://localhost:8000/ext/analyze/enqueue \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"usernames": ["usuario1", "usuario2"]}'
```

## Configuración esencial
- `.env` basado en `env.example`.
- DB: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`.
- Seguridad: `API_SHARED_SECRET`, `REQUIRE_HTTPS`, `CORS_ORIGINS`.
- Colas: `QUEUES_BACKEND`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
- Observabilidad: `LOG_LEVEL`, `LOG_FORMAT`.
- IA: `OPENAI_API_KEY` (opcional).

Cuentas Instagram en `docker/secrets/instagram_accounts.json`.

## Operación y observabilidad
- Métricas: `GET /metrics`, `GET /metrics/json`, `GET /metrics/summary`.
- Health: `GET /health`, `GET /ready`, `GET /live`.
- Logs: `api.log` y `dispatcher.log` (formato JSON en prod).

## Arquitectura
- **Multi-tenant**: aislamiento por `client_id`.
- **Rate limiting** por cliente e IP.
- **Leasing con TTL** para tareas bloqueadas.
- **Cache** opcional con Redis.

## Testing
```bash
pytest -v
pytest tests/integration/ -v
pytest tests/unit/ -v
```

## Seguridad
Recomendaciones y prácticas en `SECURITY.md`.

## Comandos útiles
Ver `COMMANDS.md`.

## Licencia
MIT © 2025
