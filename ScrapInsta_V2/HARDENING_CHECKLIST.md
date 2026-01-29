# Hardening checklist (ejecutable)

## 1) Secretos y autenticación (bloqueante)
- [ ] Definir `APP_ENV=production`.
```bash
export APP_ENV=production
```
- [ ] Definir `JWT_SECRET_KEY` y `API_SHARED_SECRET` en gestor de secretos o variables de entorno.
```bash
export JWT_SECRET_KEY="cambia-esto-por-un-secreto-largo"
export API_SHARED_SECRET="cambia-esto-por-un-secreto-largo"
```
- [ ] Rotar tokens si existían en entornos previos.

## 2) Transporte seguro (bloqueante)
- [ ] Forzar HTTPS en producción.
```bash
export REQUIRE_HTTPS=true
```
- [ ] Configurar proxy reverso con TLS y `X-Forwarded-Proto=https`.

## 3) Rate limiting distribuido (alto)
- [ ] Activar Redis y rate limiting distribuido.
```bash
export REDIS_URL="redis://:password@host:6379/0"
```
- [ ] Confiar en headers de proxy solo detrás de un proxy confiable.
```bash
export TRUST_PROXY_HEADERS=true
```

## 4) Seguridad API y abuso (alto)
- [ ] Definir `CORS_ORIGINS` con dominios permitidos.
```bash
export CORS_ORIGINS="https://app.tudominio.com"
```
- [ ] Limitar tamaño de requests.
```bash
export MAX_BODY_BYTES=1000000
```
- [ ] Validar `X-Account` contra cuentas configuradas.
```bash
export REQUIRE_ACCOUNT_IN_CONFIG=true
```
- [ ] Limitar tamaños por endpoint.
```bash
export MAX_FOLLOWINGS_LIMIT=100
export MAX_ANALYZE_USERNAMES=200
export MAX_ANALYZE_BATCH_SIZE=200
export MAX_PULL_LIMIT=100
export MAX_USERNAME_LENGTH=64
export MAX_ERROR_LENGTH=2000
export MAX_EXTRA_BYTES=20000
export MAX_ANALYZE_MAX_REELS=12
export MAX_ANALYZE_MAX_POSTS=30
export MAX_JOB_ID_LENGTH=64
export MAX_TASK_ID_LENGTH=160
export REQUIRE_JOB_ID_PREFIX=true
export USERNAME_REGEX="^[a-zA-Z0-9._]{2,30}$"
export ACCOUNT_REGEX="^[a-zA-Z0-9._-]{2,30}$"
export MIN_MESSAGE_LENGTH=3
export MAX_MESSAGE_LENGTH=1000
export MAX_MESSAGE_RETRIES=10
export MAX_CLIENT_MESSAGES_PER_DAY=100
export MAX_DMS_PER_DAY=50
export MAX_DMS_PER_TARGET_PER_DAY=1
export MAX_TARGET_USERNAME_LENGTH=30
export REQUIRE_REDIS_RATE_LIMITER=true
export DB_CONNECT_TIMEOUT=5
export DB_READ_TIMEOUT=10
export DB_WRITE_TIMEOUT=10
export REDIS_SOCKET_KEEPALIVE=true
export REDIS_HEALTH_CHECK_INTERVAL=30
export REDIS_INIT_RETRIES=2
export DB_CONNECT_RETRIES=2
export REDIS_RATE_LIMIT_RETRIES=1
export FAIL_CLOSED_ON_REDIS_ERROR=true
export WINDOW_SIZE="1200x800"
export HUMAN_BASE_APM=24
export HUMAN_APM_JITTER=0.35
export HUMAN_LONG_PAUSE_EVERY=20
export HUMAN_LONG_PAUSE_MIN=6
export HUMAN_LONG_PAUSE_MAX=12
export HUMAN_MIN_DELAY=0.1
export HUMAN_MAX_DELAY=15.0
```
- [ ] Revisar scopes por cliente en la DB y limitar los permisos.

## 5) Observabilidad y alertas (alto)
- [ ] Verificar métricas y logs.
```bash
curl http://localhost:8000/metrics
curl http://localhost:8000/metrics/summary | jq .
```
- [ ] Configurar alertas para 5xx, p95 latencia, rate_limit_hits.

## 6) Resiliencia y datos (medio)
- [ ] Configurar backups automáticos de DB y prueba de restore.
- [ ] Usar scripts de backup/restore.
```bash
./ops/db/backup.sh
./ops/db/restore.sh ./backups/scrapinsta_YYYYMMDD_HHMMSS.sql
```
- [ ] Verificar migraciones y rollback plan.

## 7) Operación y despliegue (medio)
- [ ] Pipeline CI mínimo.
```bash
pytest -v
```
- [ ] CI en GitHub Actions (`.github/workflows/ci.yml`).
- [ ] Entornos separados (dev/staging/prod).

## 8) Cumplimiento (medio)
- [ ] Política de retención de datos y TOS.
- [ ] Definir y revisar `POLICY.md`.

