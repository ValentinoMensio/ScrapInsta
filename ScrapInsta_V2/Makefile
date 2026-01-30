# Makefile para ScrapInsta V2
# Sistema de scraping de Instagram con arquitectura hexagonal

.PHONY: help install setup start stop test clean logs docker-up docker-down docker-logs db-reset lint format

# Variables
PYTHON := python3
VENV := .venv
PYTHON_VENV := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
DOCKER_COMPOSE := docker compose -f docker/docker-compose.yml
API_URL := http://localhost:8000
API_KEY := YOUR_API_KEY_HERE

# Colores para output
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
BLUE := \033[0;34m
NC := \033[0m

# Help
help: ## Mostrar ayuda
	@echo "$(BLUE)ScrapInsta V2 - Comandos disponibles:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Ejemplos de uso:$(NC)"
	@echo "  make setup     # Configurar entorno por primera vez"
	@echo "  make start     # Iniciar todos los servicios"
	@echo "  make test      # Ejecutar tests"
	@echo "  make logs      # Ver logs en tiempo real"

# =============================================================================
# CONFIGURACIÓN INICIAL
# =============================================================================

install: ## Instalar dependencias en entorno virtual
	@echo "$(BLUE)📦 Instalando dependencias...$(NC)"
	@$(PYTHON) -m venv $(VENV)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt
	@echo "$(GREEN)✓ Dependencias instaladas$(NC)"

setup: install ## Configurar proyecto por primera vez
	@echo "$(BLUE)🔧 Configurando proyecto...$(NC)"
	@if [ ! -f .env ]; then \
		cp env.example .env; \
		echo "$(YELLOW)⚠ Archivo .env creado desde env.example$(NC)"; \
		echo "$(YELLOW)⚠ Edita .env con tus configuraciones$(NC)"; \
	fi
	@if [ ! -f docker/secrets/instagram_accounts.json ]; then \
		mkdir -p docker/secrets; \
		echo '{"accounts": []}' > docker/secrets/instagram_accounts.json; \
		echo "$(YELLOW)⚠ Archivo de cuentas creado en docker/secrets/instagram_accounts.json$(NC)"; \
	fi
	@echo "$(GREEN)✓ Proyecto configurado$(NC)"

# =============================================================================
# DESARROLLO LOCAL
# =============================================================================

start: ## Iniciar todos los servicios localmente
	@echo "$(BLUE)🚀 Iniciando ScrapInsta V2...$(NC)"
	@./scripts/start_local.sh

stop: ## Detener todos los servicios
	@echo "$(YELLOW)🛑 Deteniendo servicios...$(NC)"
	@pkill -f "scrapinsta.interface.dispatcher" || true
	@pkill -f "uvicorn.*api" || true
	@$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Servicios detenidos$(NC)"

restart: stop start ## Reiniciar todos los servicios

# =============================================================================
# DOCKER
# =============================================================================

docker-up: ## Levantar servicios con Docker
	@echo "$(BLUE)🐳 Iniciando servicios con Docker...$(NC)"
	@$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Servicios Docker iniciados$(NC)"

docker-down: ## Detener servicios Docker
	@echo "$(YELLOW)🛑 Deteniendo servicios Docker...$(NC)"
	@$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Servicios Docker detenidos$(NC)"

docker-logs: ## Ver logs de Docker
	@$(DOCKER_COMPOSE) logs -f

docker-build: ## Construir imagen Docker
	@echo "$(BLUE)🔨 Construyendo imagen Docker...$(NC)"
	@$(DOCKER_COMPOSE) build
	@echo "$(GREEN)✓ Imagen construida$(NC)"

# =============================================================================
# BASE DE DATOS
# =============================================================================

db-up: ## Levantar solo la base de datos
	@echo "$(BLUE)🗄️ Iniciando base de datos...$(NC)"
	@$(DOCKER_COMPOSE) up -d db
	@echo "$(GREEN)✓ Base de datos iniciada$(NC)"

db-reset: ## Resetear base de datos (¡CUIDADO!)
	@echo "$(RED)⚠️ Reseteando base de datos...$(NC)"
	@read -p "¿Estás seguro? Esto borrará todos los datos (y/N): " confirm && \
	[ "$$confirm" = "y" ] || exit 1
	@$(DOCKER_COMPOSE) down -v
	@$(DOCKER_COMPOSE) up -d db
	@sleep 5
	@$(DOCKER_COMPOSE) exec -T db mysql -u app -papp_password scrapinsta < ops/db/schema.sql
	@echo "$(GREEN)✓ Base de datos reseteada$(NC)"

db-shell: ## Conectar a la base de datos
	@$(DOCKER_COMPOSE) exec db mysql -u app -papp_password scrapinsta

db-clear-except-clients: ## Borrar todos los datos excepto clients y client_limits
	@echo "$(RED)⚠️ Se borrarán jobs, job_tasks, messages_sent, profiles, profile_analysis, followings. Se mantienen clients y client_limits.$(NC)"
	@read -p "¿Continuar? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@$(DOCKER_COMPOSE) exec -T db mysql -u app -papp_password scrapinsta < ops/db/clear_except_clients.sql
	@echo "$(GREEN)✓ Base de datos limpiada (clientes conservados)$(NC)"

# =============================================================================
# TESTING
# =============================================================================

test: ## Ejecutar tests
	@echo "$(BLUE)🧪 Ejecutando tests...$(NC)"
	@$(PYTHON_VENV) -m pytest -v
	@echo "$(GREEN)✓ Tests completados$(NC)"

test-api: ## Probar API
	@echo "$(BLUE)🌐 Probando API...$(NC)"
	@./scripts/test_api.sh

test-coverage: ## Ejecutar tests con cobertura
	@echo "$(BLUE)📊 Ejecutando tests con cobertura...$(NC)"
	@$(PIP) install coverage
	@$(PYTHON_VENV) -m coverage run -m pytest
	@$(PYTHON_VENV) -m coverage report
	@$(PYTHON_VENV) -m coverage html
	@echo "$(GREEN)✓ Reporte de cobertura generado en htmlcov/$(NC)"

# =============================================================================
# DESARROLLO
# =============================================================================

lint: ## Ejecutar linter
	@echo "$(BLUE)🔍 Ejecutando linter...$(NC)"
	@$(PIP) install flake8 black isort
	@$(PYTHON_VENV) -m flake8 src/ --max-line-length=100 --ignore=E203,W503
	@echo "$(GREEN)✓ Linting completado$(NC)"

format: ## Formatear código
	@echo "$(BLUE)🎨 Formateando código...$(NC)"
	@$(PIP) install black isort
	@$(PYTHON_VENV) -m black src/ --line-length=100
	@$(PYTHON_VENV) -m isort src/ --profile black
	@echo "$(GREEN)✓ Código formateado$(NC)"

# =============================================================================
# LOGS Y MONITOREO
# =============================================================================

logs: ## Ver logs en tiempo real
	@echo "$(BLUE)📝 Mostrando logs...$(NC)"
	@echo "$(YELLOW)Presiona Ctrl+C para salir$(NC)"
	@tail -f api.log dispatcher.log

logs-api: ## Ver logs de la API
	@tail -f api.log

logs-dispatcher: ## Ver logs del dispatcher
	@tail -f dispatcher.log

logs-docker: ## Ver logs de Docker
	@$(DOCKER_COMPOSE) logs -f

# =============================================================================
# UTILIDADES
# =============================================================================

enqueue-fetch: ## Encolar tarea de fetch (uso: make enqueue-fetch USER=instagram LIMIT=50)
	@echo "$(BLUE)📤 Encolando tarea de fetch...$(NC)"
	@./scripts/enqueue_fetch.sh $(USER) $(LIMIT)

clean: ## Limpiar archivos temporales
	@echo "$(BLUE)🧹 Limpiando archivos temporales...$(NC)"
	@rm -rf __pycache__ src/**/__pycache__ src/**/**/__pycache__
	@rm -rf .pytest_cache .coverage htmlcov/
	@rm -f *.log
	@echo "$(GREEN)✓ Limpieza completada$(NC)"

clean-all: clean ## Limpiar todo incluyendo entorno virtual
	@echo "$(BLUE)🧹 Limpieza completa...$(NC)"
	@rm -rf $(VENV)
	@$(DOCKER_COMPOSE) down -v
	@echo "$(GREEN)✓ Limpieza completa realizada$(NC)"

status: ## Mostrar estado de los servicios
	@echo "$(BLUE)📊 Estado de los servicios:$(NC)"
	@echo ""
	@echo "$(YELLOW)Procesos Python:$(NC)"
	@ps aux | grep -E "(scrapinsta|uvicorn)" | grep -v grep || echo "  Ninguno corriendo"
	@echo ""
	@echo "$(YELLOW)Contenedores Docker:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(YELLOW)API Health:$(NC)"
	@curl -s $(API_URL)/health 2>/dev/null | jq . 2>/dev/null || echo "  API no disponible"

# =============================================================================
# DESARROLLO AVANZADO
# =============================================================================

dev-setup: setup ## Configuración completa para desarrollo
	@echo "$(BLUE)🛠️ Configuración de desarrollo...$(NC)"
	@$(PIP) install pytest-cov black flake8 isort
	@echo "$(GREEN)✓ Herramientas de desarrollo instaladas$(NC)"

migrate: ## Aplicar migraciones de base de datos
	@echo "$(BLUE)🔄 Aplicando migraciones...$(NC)"
	@$(DOCKER_COMPOSE) exec -T db mysql -u app -papp_password scrapinsta < ops/db/schema.sql
	@echo "$(GREEN)✓ Migraciones aplicadas$(NC)"

# =============================================================================
# PRODUCCIÓN
# =============================================================================

prod-build: ## Construir para producción
	@echo "$(BLUE)🏗️ Construyendo para producción...$(NC)"
	@$(DOCKER_COMPOSE) -f docker/docker-compose.yml build --no-cache
	@echo "$(GREEN)✓ Build de producción completado$(NC)"

prod-deploy: prod-build ## Desplegar a producción
	@echo "$(BLUE)🚀 Desplegando a producción...$(NC)"
	@$(DOCKER_COMPOSE) -f docker/docker-compose.yml up -d
	@echo "$(GREEN)✓ Despliegue completado$(NC)"

# =============================================================================
# INFORMACIÓN
# =============================================================================

info: ## Mostrar información del proyecto
	@echo "$(BLUE)📋 Información de ScrapInsta V2:$(NC)"
	@echo ""
	@echo "$(YELLOW)Estructura del proyecto:$(NC)"
	@echo "  src/scrapinsta/          - Código principal"
	@echo "  src/scrapinsta/domain/   - Modelos de dominio"
	@echo "  src/scrapinsta/application/ - Casos de uso"
	@echo "  src/scrapinsta/infrastructure/ - Implementaciones"
	@echo "  src/scrapinsta/interface/ - API y workers"
	@echo ""
	@echo "$(YELLOW)Servicios:$(NC)"
	@echo "  API: $(API_URL)"
	@echo "  Docs: $(API_URL)/docs"
	@echo "  Health: $(API_URL)/health"
	@echo ""
	@echo "$(YELLOW)Comandos útiles:$(NC)"
	@echo "  make start     - Iniciar todo"
	@echo "  make test      - Ejecutar tests"
	@echo "  make logs      - Ver logs"
	@echo "  make status    - Estado de servicios"

# Default target
.DEFAULT_GOAL := help
