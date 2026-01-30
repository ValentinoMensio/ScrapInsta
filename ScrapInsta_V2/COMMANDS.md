# Comandos útiles

## Ayuda general
```bash
make help
```

## Configuración inicial
```bash
make setup
cp env.example .env
```

## Levantar entorno local
```bash
./scripts/start_local.sh
make start
```

## Docker
```bash
make docker-up
make docker-down
make docker-logs
make docker-build
```

## Base de datos
```bash
make db-up
make db-shell
make db-reset
make db-clear-except-clients   # Borra todo excepto clients y client_limits
./ops/db/reset.sh
alembic upgrade head
```

## Tests y calidad
```bash
make test
make test-coverage
pytest -v
pytest tests/integration/ -v
pytest tests/unit/ -v
```

## Lint y formato
```bash
make lint
make format
```

## Logs y estado
```bash
make logs
make logs-api
make logs-dispatcher
make status
tail -f api.log dispatcher.log
```

## Scripts de utilidad
```bash
./scripts/test_api.sh
./scripts/test_observability.sh
python scripts/create_client.py --help
python scripts/encrypt_password.py --help
python scripts/inspect_cache.py --help
python scripts/inspect_cache_simple.py --help
python scripts/check_cache_usage.py --help
python scripts/test_accounts_loading.py --help
python scripts/test_encryption.py --help
```

## Operación
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/live
curl http://localhost:8000/metrics
```

## Debug del envío de mensajes (DM)

Si el flujo “entra al perfil y no hace nada más”, el fallo suele estar en uno de estos pasos: **abrir perfil** → **clic en “Message”** → **escribir en el cuadro** → **clic en “Send”**.

### 1. Ver logs paso a paso

Los logs del flujo de envío incluyen `dm_step` y `dm_step_done` por cada paso. Busca en los logs:

- `dm_step step=open_profile` / `dm_step_done step=open_profile` → perfil abierto.
- `dm_step step=open_message_dialog` / `dm_step_done step=open_message_dialog` → clic en “Message”.
- `dm_step step=type_message` / `dm_step_done step=type_message` → texto escrito.
- `dm_step step=send_action` / `dm_step_done step=send_action` → envío.

Si ves `dm_step` de un paso pero no su `dm_step_done`, el fallo está en ese paso. Si aparece `dm_step_error` o `dm_all_selectors_failed`, el mensaje indica el problema (timeout, elemento no encontrado, etc.).

### 2. Más detalle (nivel DEBUG)

Para ver qué selectores se prueban y cuál falla:

```bash
LOG_LEVEL=DEBUG ./scripts/start_local.sh
# o en .env: LOG_LEVEL=DEBUG
```

En DEBUG verás `dm_selector_ok`, `dm_selector_fail`, `dm_page_selector_fail` y `dm_page_step_failed`.

### 3. Ejecutar con navegador visible

Si el envío lo hace un worker/script con Selenium, asegúrate de no usar `--headless` para ver qué hace el navegador. Revisa la config del driver (env o código que arranca el browser) y quita headless para depurar.

### 4. Si el envío lo hace la extensión (frontend)

Entonces el flujo que “entra al perfil” está en el código de la extensión. Revisa ahí:

- Después de abrir `instagram.com/<username>/`, ¿hay un paso que haga clic en “Message”?
- ¿Usa los mismos selectores que `dm_page.py` (`_BTN_MESSAGE_XPATHS`, `_TEXTAREA_XPATHS`, `_BTN_SEND_XPATHS`)? Instagram cambia el DOM a menudo; si la extensión usa selectores distintos, puede que fallen.
- Añade `console.log` (o equivalentes) antes y después de cada paso (abrir perfil, clic Message, escribir, clic Send) para ver en qué paso se queda.

