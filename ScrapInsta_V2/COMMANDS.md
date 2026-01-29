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

