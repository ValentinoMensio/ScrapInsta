# ScrapInsta V2

Sistema automatizado para scraping, análisis y envío de mensajes en Instagram.

## ¿Qué hace?

ScrapInsta te permite:
- **Analizar perfiles**: Obtener información de perfiles (seguidores, publicaciones, reels, engagement)
- **Extraer followings**: Obtener la lista de cuentas que sigue un usuario
- **Enviar mensajes**: Automatizar el envío de DMs con soporte para composición con IA

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

Todas las peticiones requieren el header:
```
X-Api-Key: TU_API_KEY
```

### Ejemplos

**Analizar un perfil:**
```bash
curl -X POST http://localhost:8000/ext/analyze/enqueue \
  -H "X-Api-Key: TU_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"usernames": ["usuario1", "usuario2"]}'
```

**Extraer followings:**
```bash
curl -X POST http://localhost:8000/ext/followings/enqueue \
  -H "X-Api-Key: TU_API_KEY" \
  -H "X-Account: tu_cuenta_cliente" \
  -H "Content-Type: application/json" \
  -d '{"target_username": "usuario_target", "limit": 50}'
```

**Consultar estado de un job:**
```bash
curl http://localhost:8000/jobs/JOB_ID/summary \
  -H "X-Api-Key: TU_API_KEY"
```

## Configuración

### Variables principales (.env)

- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`: Configuración de MySQL
- `API_SHARED_SECRET`: Clave secreta para autenticación API
- `OPENAI_API_KEY`: (Opcional) Para composición de mensajes con IA
- `LOG_LEVEL`: Nivel de logging (INFO, DEBUG, etc.)
- `LOG_FORMAT`: Formato de logs (text o json)

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

## Monitoreo

### Métricas

```bash
# Resumen legible de métricas
curl http://localhost:8000/metrics/summary | jq .

# Métricas en formato Prometheus
curl http://localhost:8000/metrics
```

### Health checks

```bash
# Health check básico
curl http://localhost:8000/health

# Readiness (listo para recibir tráfico)
curl http://localhost:8000/ready

# Liveness (proceso vivo)
curl http://localhost:8000/live
```

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
├── application/     # Casos de uso y lógica de negocio
├── domain/          # Modelos y puertos (interfaces)
├── infrastructure/  # Implementaciones (DB, browser, AI)
├── interface/       # API REST y workers
└── config/         # Configuración
```

## Documentación

- **Guía técnica**: [DEVELOPERGUIE.md](DEVELOPERGUIE.md)
- **Guía de métricas**: [docs/METRICAS_GUIA.md](docs/METRICAS_GUIA.md)
- **Migraciones de BD**: [docs/MIGRACIONES_BD.md](docs/MIGRACIONES_BD.md)

## Testing

```bash
# Ejecutar todos los tests
pytest -v

# Con cobertura
pytest --cov=src/scrapinsta --cov-report=html
```

## Seguridad

⚠️ **Importante**: 
- No incluyas credenciales reales en el repositorio
- Cambia todas las contraseñas por defecto
- Usa variables de entorno para secretos

Ver [SECURITY.md](SECURITY.md) para más detalles.

## Licencia

MIT © 2025
