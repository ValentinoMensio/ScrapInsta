# 🧩 ScrapInsta — Clean/Hexagonal Instagram Scraper & Automation System

**ScrapInsta** es un sistema empresarial modular y escalable para **scraping, análisis, automatización y envío de mensajes** en Instagram.
Arquitectura **Hexagonal (Clean Architecture)**, **DTOs inmutables** (Pydantic v2), **SQL plano** (sin ORM), **Selenium (undetected + seleniumwire)** encapsulado en infraestructura.

---

## ✨ Feature set

### Core Features
* **Analyze Profile**: snapshot del perfil (bio, followers, **followings**, **posts**, verificado, privacidad), **reels** (views/likes/comments), **scores** (engagement y éxito) vía servicio puro con benchmarks de la industria.
* **Fetch Followings**: extrae y persiste followings del owner con **upsert** idempotente.
* **Send Messages**: envío automatizado de DMs con soporte para composición IA (OpenAI GPT).
* **Human-like automation**: hover/scroll con ritmo humano, jitter, rate limiting inteligente.
* **Multi-tenant**: sistema de accounts con autenticación, rate limiting por cliente y ledger de deduplicación.
* **Jobs & Tasks**: orquestación robusta con leasing atómico, balanceo de carga, backoff exponencial.

### Infrastructure
* **DB-first**: `INSERT ... ON DUPLICATE KEY UPDATE`, migraciones simples, schema versionado.
* **Workers System**: pool de workers con balanceo inteligente, token bucket rate limiting, anti-starvation.
* **API REST**: FastAPI con autenticación API Key/JWT, scopes, HTTPS enforcement.
* **Queue Backends**: soporte para local multiprocessing y AWS SQS.
* **Docker**: app + db + (opcional) selenium grid/headless con healthchecks.

---

## 🧱 Arquitectura

```
src/scrapinsta
├─ application
│  ├─ dto/                # Pydantic v2 (frozen=True)
│  │  ├─ profiles.py
│  │  ├─ followings.py
│  │  ├─ messages.py      # send_message DTOs
│  │  └─ tasks.py         # job/task envelopes
│  ├─ services/
│  │  ├─ evaluator.py     # engagement/success (funciones puras)
│  │  ├─ text_analysis.py # IA composition
│  │  └─ task_dispatcher.py
│  └─ use_cases/
│     ├─ analyze_profile.py
│     ├─ fetch_followings.py
│     └─ send_message.py
├─ domain
│  ├─ models/
│  │  └─ profile_models.py
│  └─ ports/
│     ├─ browser_port.py
│     ├─ profile_repo.py
│     ├─ followings_repo.py
│     ├─ job_store.py
│     └─ message_port.py
├─ infrastructure
│  ├─ browser/
│  │  ├─ pages/
│  │  │  ├─ profile_page.py  # snapshot de perfil
│  │  │  ├─ reels_page.py    # scraping de reels
│  │  │  └─ dm_page.py       # envío de mensajes
│  │  ├─ adapters/
│  │  │  ├─ selenium_browser_adapter.py
│  │  │  └─ selenium_message_sender.py
│  │  └─ core/
│  │     ├─ driver_factory.py
│  │     └─ browser_utils.py
│  ├─ db/
│  │  ├─ profile_repo_sql.py
│  │  ├─ followings_repo_sql.py
│  │  └─ job_store_sql.py    # Jobs/Tasks persistence
│  ├─ ai/
│  │  └─ chatgpt_openai.py
│  └─ auth/
│     ├─ session_service.py
│     └─ cookie_store.py
├─ interface
│  ├─ api.py              # FastAPI endpoints
│  ├─ dispatcher.py       # Long-running dispatcher
│  ├─ workers/
│  │  ├─ router.py        # Load balancer
│  │  ├─ instagram_worker.py
│  │  └─ deps_factory.py
│  └─ queues/
│     ├─ local_mp.py      # Multiprocessing queues
│     └─ sqs.py          # AWS SQS adapter
├─ crosscutting
│  ├─ human/              # tempo + acciones humanas
│  ├─ parse.py
│  ├─ retry.py
│  └─ rate_limit.py
└─ config/
   ├─ settings.py
   └─ keywords.json
```

**Principios clave**

* **Use cases** orquestan, no hacen IO.
* **Adapters finos**; scraping en *page modules*.
* **Servicios puros** en `application/services` (sin side-effects).
* **Nombres normalizados** en dominio/app: `followers`, `followings`, `posts`.
* **Separation of concerns**: Jobs/Tasks, API, Workers, Dispatcher.
* **Multi-account support**: worker pool con balanceo y rate limiting por cuenta.

---

## 🔁 Flujos principales

### Analyze Profile

```
[AnalyzeProfileUseCase]
  -> browser.get_profile_snapshot(username)       -> ProfileSnapshot
  -> browser.get_reel_metrics(username)           -> List[ReelMetrics]
  -> compute avg_* from reels                     -> BasicStats parcial
  -> build metrics_input {followers, posts, avg_*}
  -> evaluator.evaluate_profile(metrics_input)    -> scores
  -> repo.upsert_profile(snapshot)
  -> repo.save_analysis_snapshot(profile_id, response)
```

* Si el perfil es **privado**, se retorna sin reels/stats y se persiste el snapshot.
* `evaluator.py` recibe un **dict plano** (no DTOs) con claves:
  `followers`, `posts`, `avg_likes`, `avg_comments`, `avg_views`.
* **Benchmarks industriales**: engagement 2.66-6.08%, views 4-20% según rangos de followers.

### Fetch Followings

```
[FetchFollowingsUseCase]
  -> browser.get_followings(owner, max_n)         -> list[str]
  -> repo.upsert_for_owner(owner, followings)     -> int new_saved
  -> return DTO con owner, followings, new_saved
```

### Send Messages

```
[SendMessageUseCase]
  -> repo.get_message_context(username)           -> MessageContext (rubro, scores, etc.)
  -> (optional) ai.compose_message(context)       -> generated_text
  -> message_port.send_dm(username, message_text) -> success
  -> retry logic with backoff exponencial
```

### Dispatcher Orchestration

```
[Dispatcher Loop]
  -> scan DB for pending/running jobs
  -> load Job metadata (kind, priority, batch_size)
  -> router.add_job(job)
  -> router.dispatch_tick()                      -> balancea por account con aging
  -> worker receives TaskEnvelope
  -> worker executes use case
  -> worker sends ResultEnvelope
  -> dispatcher.on_result(result)
  -> (if fetch_followings done) FetchToAnalyzeOrchestrator creates analyze_profile job
```

---

## 🗃️ Base de datos

MySQL 8.4 con schema automático.

Tablas principales:
- **profiles**: información de perfiles analizados
- **profile_analysis**: métricas y scores de engagement
- **followings**: relaciones de seguimiento
- **jobs**: orquestación de trabajos
- **job_tasks**: tareas individuales
- **messages_sent**: ledger de deduplicación

Schema se aplica automáticamente en `./scripts/start_local.sh`

---

## ⚙️ Configuración

Configura tu `.env` basándote en `env.example`:

```bash
cp env.example .env
```

Variables principales:
- **Base de datos**: configuración de MySQL
- **API Authentication**: secret key para autenticación
- **OpenAI**: opcional, para composición IA de mensajes
- **Workers**: configuración de concurrencia y balanceo

### Cuentas Instagram

Configura tus cuentas en `docker/secrets/instagram_accounts.json`:

```json
[
  {
    "username": "tu_cuenta",
    "password": "tu_password"
  }
]
```

---

## 🐳 Docker

### Setup con Docker (opcional)

Si prefieres Docker en lugar del script local:

```bash
cd docker
docker compose up -d --build
docker compose logs -f
```

Para recrear desde cero (elimina datos):

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

---

## 🚀 Ejemplos de uso

### Iniciar el Sistema

**Recomendado**: Usar el script que configura todo automáticamente:

```bash
./scripts/start_local.sh
```

Este script:
1. Configura el entorno virtual Python
2. Levanta MySQL en Docker
3. Aplica el schema de base de datos
4. Inicia la API FastAPI (puerto 8000)
5. Inicia el Dispatcher con workers

### API REST

```bash
# Health check
curl http://localhost:8000/health

# Crear job de fetch followings
curl -X POST http://localhost:8000/ext/followings/enqueue \
  -H "X-Api-Key: TU_API_KEY" \
  -H "X-Account: tu_cuenta_cliente" \
  -H "Content-Type: application/json" \
  -d '{"target_username": "target_user", "limit": 10}'

# Consultar estado de un job
curl http://localhost:8000/jobs/JOB_ID/summary \
  -H "X-Api-Key: TU_API_KEY"

# Documentación interactiva
open http://localhost:8000/docs
```

### Programático

```python
from scrapinsta.application.use_cases.analyze_profile import AnalyzeProfileUseCase
from scrapinsta.application.use_cases.fetch_followings import FetchFollowingsUseCase

# Analizar perfil
uc = AnalyzeProfileUseCase(browser, profile_repo=repo)
resp = uc(AnalyzeProfileRequest(username="target_user", fetch_reels=True, max_reels=12))

# Fetch followings
uc = FetchFollowingsUseCase(browser, repo)
resp = uc(FetchFollowingsRequest(username="owner_user", max_followings=200))
```

---

## 🧪 Testing

```bash
# Ejecutar tests
pytest -v

# Con Docker
docker compose exec app pytest -v
```

---

## 🔧 Desarrollo

### Setup Inicial

```bash
# 1. Clonar y configurar
git clone <repo>
cd ScrapInsta_V2
cp env.example .env

# 2. Configurar cuentas Instagram en:
# docker/secrets/instagram_accounts.json

# 3. Iniciar sistema
./scripts/start_local.sh
```

### Ver Logs

```bash
tail -f api.log dispatcher.log
```

### Probar API

```bash
# Suite de tests
./scripts/test_api.sh

# Documentación interactiva
open http://localhost:8000/docs
```

📖 **Documentación técnica**: [DEVELOPERGUIE.md](DEVELOPERGUIE.md)

---

## 📚 API Reference

### Endpoints

- **GET `/health`**: Health check del sistema
- **POST `/ext/followings/enqueue`**: Crear job de fetch followings
- **POST `/ext/analyze/enqueue`**: Crear job de análisis de perfil
- **GET `/jobs/{job_id}/summary`**: Estado de un job
- **POST `/api/send/pull`**: Obtener tareas para extensión
- **POST `/api/send/result`**: Reportar resultado de envío

### Autenticación

Header requerido: `X-Api-Key: TU_API_KEY`

### Documentación completa

Documentación interactiva disponible en:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🏗️ Roadmap

Ver [DEVELOPERGUIE.md](DEVELOPERGUIE.md#roadmap) para detalles completos.

**Completado:**
- ✅ Hexagonal Architecture
- ✅ Use cases: analyze_profile, fetch_followings, send_message
- ✅ Jobs & Tasks orquestación
- ✅ Worker pool con balanceo inteligente
- ✅ API REST con autenticación
- ✅ Ledger de deduplicación
- ✅ Dispatcher long-running
- ✅ Docker setup

**Pendiente:**
- 🔲 JWT tokens para multi-tenant
- 🔲 AWS SQS integration
- 🔲 CI/CD pipeline

---

## 🔐 Seguridad

Este proyecto NO incluye información sensible:
- ✅ Sin credenciales reales de Instagram
- ✅ Sin API keys de producción
- ✅ Sin cookies o sesiones activas

**Configuración segura:**
1. Copia `env.example` a `.env`
2. Configura tus cuentas en `docker/secrets/instagram_accounts.json`
3. Cambia todas las contraseñas por defecto

Ver [SECURITY.md](SECURITY.md) para más detalles.

---

## 📄 Licencia

MIT © 2025
 