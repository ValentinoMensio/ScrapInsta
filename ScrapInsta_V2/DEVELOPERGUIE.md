# DEVELOPERGUIE.md — ScrapInsta (Guía del Desarrollador)

> Esta guía consolida el estado actual del proyecto, la arquitectura, las tareas ejecutadas y el **roadmap** para llevar el producto a nivel profesional y escalable (multi-tenant, seguro y observable). 

---

## 1) Visión

* **Backend (workers):** scraping (followings, reels) y análisis (scores) en tu infraestructura.
* **Cliente (extensión navegador):** envío de DMs **desde la cuenta del cliente** (evita gestionar credenciales del cliente en backend, disminuye bloqueo).
* **Orquestación:** Jobs & Tasks en MySQL con **leasing atómico** para evitar colisiones, **ledger de deduplicación por cliente** para no recontactar.

---

## 2) Arquitectura (alto nivel)

```
Extensión Cliente ──(API Key/JWT)──► FastAPI (API)
                                       │
                                       ▼
                                   Job Store (MySQL)
                                       │
                           Dispatcher ─┴─ Router ──► Workers (Selenium)
                                       │
                                 Dedupe Ledger (MySQL)
```

* **API (FastAPI):**

  * `/ext/followings/enqueue` → crea job `fetch_followings` con “task semilla”.
  * `/api/send/pull` → la extensión hace pull (lease) de tasks `send_message`.
  * `/api/send/result` → reporta `ok/error`; si `ok`, actualiza **ledger (client+dest)**.
  * `/health` → ping DB.
* **Dispatcher:** escanea `jobs` (pending/running), reconstruye `Job` y lo registra en el **Router**.
* **Router/Workers:** el Router balancea por cuentas bot; cada **InstagramWorker** usa `deps_factory.get_factory()`.

---

## 3) Componentes relevantes

* `src/scrapinsta/infrastructure/db/job_store_sql.py`

  * Jobs/Tasks CRUD, `job_summary`, `all_tasks_finished`.
  * **Leasing**: `lease_tasks(account_id, limit)` con `SELECT … FOR UPDATE SKIP LOCKED`.
  * **Ledger**: `was_message_sent(client, dest)` y `register_message_sent(...)`.
* `src/scrapinsta/interface/api.py`

  * **Auth mínima**: `X-Api-Key` (luego JWT por cliente).
  * Endpoints: `/ext/followings/enqueue`, `/api/send/pull`, `/api/send/result`, `/health`.
* `src/scrapinsta/interface/dispatcher.py`

  * Inicia colas y workers como `main.py`.
  * Escanea DB → arma `Job(fetch_followings)` desde task semilla → `router.add_job`.
* `src/scrapinsta/interface/workers/*`

  * `InstagramWorker` procesa envelopes; usa `get_factory(account, settings)`.

---

## 4) Esquema de datos (MySQL)

* `jobs(id, kind, priority, batch_size, extra_json, total_items, status, created_at, updated_at)`
* `job_tasks(job_id, task_id, correlation_id, account_id, username, payload_json, status, sent_at, finished_at, error_msg, created_at, updated_at)`
* `messages_sent(id, client_username, dest_username, job_id, task_id, first_sent_at, last_sent_at)`
  `UNIQUE(client_username, dest_username)` → **dedupe por cliente**.

> Recomendado agregar índices:
> `job_tasks(account_id, status, created_at)`, `messages_sent(client_username, dest_username)`.

---

## 5) Contratos API (mínimos ya implementados)

* `POST /ext/followings/enqueue`

  * Body: `{ "target_username": "dr.larosa", "limit": 10 }`
  * Crea job `fetch_followings` + task semilla (`username=target`).
  * Respuesta: `{ "job_id": "..." }`

* `POST /api/send/pull`

  * Headers: `X-Api-Key`, `X-Account` (cuenta local del cliente).
  * Body: `{ "limit": 10 }`
  * **Lease atómico** de `queued` → `sent` para `account_id = X-Account`.
  * Respuesta: `{"items":[{ "job_id","task_id","dest_username","payload"}]}`

* `POST /api/send/result`

  * Body: `{ "job_id","task_id","ok":true|false,"error":null|"…","dest_username":"alice" }`
  * Marca `ok/error`; si `ok`, `register_message_sent(X-Account, dest_username, ...)`.
  * Si el job quedó sin pendientes, `mark_job_done`.

* `GET /health`

  * `{ "ok": true }` si hay conexión a DB.

---

## 6) Flujo end-to-end recomendado

1. **Extensión** → `enqueue` de **fetch** (`target_username`, `limit`).
2. **Dispatcher** encuentra job, crea `Job(fetch_followings)` con `items=[target]`.
3. **Workers** ejecutan scraping y guardan followings/perfiles.
4. (Opcional) API/Back crea **job analyze_profile** para los followings.
5. **API** crea **job send_message** con destinatarios elegibles (filtra con ledger).
6. **Extensión** hace `pull` + `result` y respeta pacing humano.
7. **Ledger** asegura **no recontactar** `(client, username)`.

---

## 7) Checklist Operativo

* [ ] DB levantada: `docker compose up -d db`.
* [ ] Esquema aplicado: `ops/db/schema.sql` (o `ops/db/reset.sh`).
* [ ] API corriendo:
  `API_SHARED_SECRET=… PYTHONPATH=src python -m uvicorn scrapinsta.interface.api:app --reload`.
* [ ] Dispatcher corriendo:
  `PYTHONPATH=src python -m scrapinsta.interface.dispatcher`.
* [ ] Cuentas bot en `Settings` (workers).
* [ ] Cuentas cliente → **X-Account** (libre, no se valida en `Settings`).
* [ ] Extensión configurada con endpoint y `X-Api-Key`.

---

## 8) Seguridad (fase 1 → fase 2)

**Fase 1 (actual):**

* `X-Api-Key` compartida.
* `X-Account` libre (identifica cola de envío para leasing).

**Fase 2 (recomendada):**

* Tabla `clients(client_id, name, api_key_hash, status, limits)` y **API Keys por cliente**.
* **JWT de corta duración** emitido por `/api/auth/jwt?job_id=…` (claims: `client_id`, `scope`, `job_id`, `exp`).
* **Rate limiting** por cliente (`pulls/min`, `results/min`) y por envíos/día.

---

## 9) Observabilidad

* **Logs estructurados (JSON)**: `job_id`, `task_id`, `client`, `account_bot`, `latency_ms`.
* **Métricas** (Prometheus):

  * `tasks_queued/sent/ok/error`
  * `lease_duration_ms` y `result_lag_ms`
  * `dedupe_hits_total`
  * `api_rate_limited_total`
* **Alertas**: spikes de `error`, colas creciendo, DB lenta.

---

## 10) Anti-detección / pacing humano (extensión)

* Pausas aleatorias, “typing” delay, retry con **backoff**.
* Detectar banners/limit IG → pausar N minutos, registrar en logs.
* Límites por hora/día (del Job) aplicados por la extensión.
* Modo “dry-run” para QA.

---

## 11) Dedupe por cliente (ledger)

* **Al encolar** `send_message`: filtrar candidatos con
  `UNIQUE(client_username, dest_username)` y, si aplica, **cool-off** (recontacto tras X días).
* **Al result OK**: `register_message_sent(client, dest, job_id, task_id)` (UPSERT).
* **Idempotencia**: `task_id` determinístico por `{tenant/client, template_id, username_norm}`.

> Nota: hoy el ledger usa `client_username = X-Account`. Cuando agregues multi-tenant formal, cambia a `client_id`/`tenant_id`.

---

## 12) Testing

* **Unit tests**: store SQL (upserts, lease), servicios de texto, puertos del dominio.
* **Funcionales API** (pytest + TestClient): `enqueue → dispatcher → pull → result → ledger`.
* **Concurrencia**: doble `pull` simultáneo no debe devolver mismas tasks.
* **E2E local**: con extensión en modo “simulado”.

---

## 13) DevOps & despliegue

* **Dev**: Docker Compose (API, DB, dispatcher, workers).
* **Prod**: contenedores separados; orquestación (Kubernetes/Nomad).
  Healthchecks, readiness, autoscaling de workers, secrets (Vault/SSM).

---

## 14) Roadmap (priorizado)

### Fase A — “Producto vendible” (2–3 hitos)

1. **Multi-tenant básico**

   * `clients` + API Keys por cliente.
   * Guardar `client_id` en `jobs`/`job_tasks`.
   * Validar ownership en `/pull` y `/result`.
2. **Leasing con TTL**

   * Columna `leased_at` en `job_tasks`.
   * Reencolar expirados desde el dispatcher.
3. **Dedupe robusta**

   * Filtro de candidatos al **encolar** `send_message` (no solo al result).
   * Soporte de **cool-off** (configurable en `jobs.extra_json`).

### Fase B — “Escala y robustez”

4. **Rate limiting**

   * Bucket por `client_id` y por “envíos/día” (aplicado en API + extensión).
5. **Observabilidad**

   * Métricas Prometheus + logs JSON + dashboards.
6. **Autenticación mejorada**

   * JWT corto por job; revocación; scopes (pull/result/status).
7. **Migrations formales**

   * Alembic: `messages_sent`, índices, `leased_at`, `clients`.

### Fase C — “Producto enterprise”

8. **UI Admin & Dashboard**

   * Estado por job, SSE de progreso, retry, cancelar.
9. **Cola externa (opcional)**

   * SQS/Rabbit si la carga supera lo razonable para MySQL leasing.
10. **Packaging extensión**

    * MV3 estable, QA de selectores, publicación en Web Store.

---

## 15) Scripts útiles

* **Reset total de DB**: `ops/db/reset.sh`
  (Drop & Create desde `schema.sql`, muestra tablas al final)
* **Smoke test rápido**:

  1. `enqueue` (followings),
  2. arrancar `dispatcher`,
  3. verificar avance de `jobs/job_tasks`.

---

## 16) Decisiones y convenciones

* **DSN MySQL** via `Settings` (`mysql://user:pass@host:port/db?charset=utf8mb4`).
* **`username` normalizado** a minúsculas para keys/ledger.
* **`task_id`**: `"{job_id}:{kind}:{username_norm}"`.
* **Errores**: no bloquean el sistema (try/except guard en puntos críticos; registrar y continuar).
* **Extensión**: *no* maneja configuración sensible del backend (solo endpoint/API key/jwt).

---

## 17) Preguntas frecuentes (dev)

* **¿Por qué la extensión no usa `Settings`?**
  Porque `Settings` es para **bots/infra**. La extensión se identifica con `X-Api-Key` (+ JWT en v2) y su `X-Account` es la cola de envío cliente.
* **¿Leasing en MySQL?**
  Sí, con MySQL 8+ usamos `SELECT … FOR UPDATE SKIP LOCKED` y update transaccional para pasar `queued → sent`.
* **¿Qué pasa si la extensión se cae con tasks `sent`?**
  Con **TTL de lease**, el dispatcher reencola al expirar `leased_at`.

---

**Fin de guía** — mantener este documento junto al código y actualizar tras cada hito de roadmap.
