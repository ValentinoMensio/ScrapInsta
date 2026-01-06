# Sistema Multi-Tenant - Documentación Completa

## Tabla de Contenidos

1. [Introducción](#introducción)
2. [Arquitectura](#arquitectura)
3. [Componentes Implementados](#componentes-implementados)
4. [Base de Datos](#base-de-datos)
5. [Autenticación](#autenticación)
6. [API Endpoints](#api-endpoints)
7. [Uso Práctico](#uso-práctico)
8. [Configuración](#configuración)
9. [Migraciones](#migraciones)
10. [Seguridad y Aislamiento](#seguridad-y-aislamiento)

---

## Introducción

El sistema multi-tenant permite que múltiples clientes utilicen la misma instancia de ScrapInsta de forma aislada y segura. Cada cliente tiene:

- **Identidad única**: Cada cliente tiene un `client_id` único
- **Aislamiento de datos**: Los jobs, tareas y mensajes están asociados a un cliente específico
- **Autenticación independiente**: Cada cliente tiene su propia API key
- **Límites configurables**: Rate limits y límites de mensajes por cliente
- **Tokens JWT**: Autenticación moderna con tokens JWT

---

## Arquitectura

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   /api/auth  │  │  /ext/*      │  │  /api/send/* │       │
│  │    /login    │  │  /enqueue    │  │   /pull      │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
│         │                 │                  │                │
│         └─────────────────┼──────────────────┘                │
│                           │                                   │
│                  ┌────────▼────────┐                          │
│                  │  _auth_client() │                          │
│                  │  (JWT/API Key)  │                          │
│                  └────────┬────────┘                          │
└───────────────────────────┼───────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
        ┌───────▼────────┐    ┌────────▼────────┐
        │  ClientRepoSQL  │    │   JobStoreSQL   │
        │                 │    │                 │
        │ - get_by_id()   │    │ - create_job()  │
        │ - get_by_api_   │    │ - add_task()    │
        │   key()         │    │ - lease_tasks() │
        │ - get_limits()  │    │ - job_summary() │
        └───────┬─────────┘    └────────┬─────────┘
                │                       │
                └───────────┬───────────┘
                            │
                    ┌───────▼────────┐
                    │   MySQL DB      │
                    │                 │
                    │ - clients       │
                    │ - client_limits │
                    │ - jobs          │
                    │ - job_tasks     │
                    │ - messages_sent │
                    └─────────────────┘
```

### Flujo de Autenticación

```
Cliente → API Request
    │
    ├─ Con Bearer Token?
    │  └─→ Verificar JWT
    │      └─→ Obtener client_id del token
    │          └─→ Validar cliente en BD
    │              └─→ Retornar client_id
    │
    └─ Con X-Api-Key?
       └─→ Buscar cliente por API key
           └─→ Validar hash
               └─→ Retornar client_id

client_id → Filtrar/queries por cliente
```

---

## Componentes Implementados

### 1. Repositorio de Clientes (`ClientRepoSQL`)

**Ubicación**: `src/scrapinsta/infrastructure/db/client_repo_sql.py`

**Responsabilidades**:
- Gestión de clientes en la base de datos
- Autenticación por API key
- Gestión de límites de rate limiting

**Métodos principales**:

```python
# Obtener cliente por ID
client = client_repo.get_by_id("client123")
# Retorna: {"id": "client123", "name": "...", "status": "active", ...}

# Autenticación por API key
client = client_repo.get_by_api_key("api-key-here")
# Verifica el hash bcrypt y retorna el cliente si es válido

# Crear nuevo cliente
client_repo.create(
    client_id="new_client",
    name="Nuevo Cliente",
    email="cliente@example.com",
    api_key_hash=hashed_key,  # Hash bcrypt de la API key
    metadata={"custom": "data"}
)

# Actualizar estado
client_repo.update_status("client123", "suspended")  # o "active", "deleted"

# Gestión de límites
limits = client_repo.get_limits("client123")
# Retorna: {"requests_per_minute": 100, "requests_per_hour": 5000, ...}

client_repo.update_limits("client123", {
    "requests_per_minute": 200,
    "requests_per_hour": 10000,
    "requests_per_day": 100000,
    "messages_per_day": 2000
})
```

### 2. Autenticación JWT (`jwt_auth.py`)

**Ubicación**: `src/scrapinsta/infrastructure/auth/jwt_auth.py`

**Funcionalidades**:
- Creación de tokens JWT con expiración
- Verificación de tokens
- Extracción de `client_id` desde tokens

**Uso**:

```python
from scrapinsta.infrastructure.auth.jwt_auth import create_access_token, verify_token

# Crear token
token = create_access_token({
    "client_id": "client123",
    "scopes": ["fetch", "analyze", "send"]
})
# Token válido por 60 minutos por defecto

# Verificar token
payload = verify_token(token)
if payload:
    client_id = payload.get("client_id")
    scopes = payload.get("scopes")
```

**Configuración**:
- `JWT_SECRET_KEY`: Clave secreta para firmar tokens (default: `API_SHARED_SECRET`)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Tiempo de expiración (default: 60)

### 3. JobStoreSQL Actualizado

**Cambios principales**:
- Todos los métodos ahora requieren o filtran por `client_id`
- `create_job()` y `add_task()` incluyen `client_id`
- `lease_tasks()` filtra tareas por `client_id`
- `job_summary()` valida ownership antes de retornar datos

**Ejemplo**:

```python
# Crear job con client_id
job_store.create_job(
    job_id="job123",
    kind="fetch_followings",
    priority=5,
    batch_size=1,
    extra={},
    total_items=1,
    client_id="client123"  # ← Nuevo parámetro
)

# Agregar tarea con client_id
job_store.add_task(
    job_id="job123",
    task_id="task456",
    correlation_id="job123",
    account_id=None,
    username="target_user",
    payload={"username": "target_user"},
    client_id="client123"  # ← Nuevo parámetro
)

# Leasing de tareas (filtrado por client_id)
tasks = job_store.lease_tasks(
    account_id="worker_account",
    limit=10,
    client_id="client123"  # ← Solo tareas de este cliente
)

# Resumen de job (con validación de ownership)
summary = job_store.job_summary(
    job_id="job123",
    client_id="client123"  # ← Valida que el job pertenece al cliente
)
```

### 4. Dispatcher y Router Actualizados

**Dispatcher** (`src/scrapinsta/interface/dispatcher.py`):
- Cuando crea un job de análisis automático, obtiene el `client_id` del job original
- Propaga el `client_id` a todos los jobs y tareas derivados

**Router** (`src/scrapinsta/interface/workers/router.py`):
- Obtiene `client_id` desde la BD cuando registra jobs
- Asegura que todas las tareas tengan el `client_id` correcto

---

## Base de Datos

### Tablas Nuevas

#### Tabla `clients`

Almacena información de cada cliente:

```sql
CREATE TABLE clients (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    api_key_hash VARCHAR(255) NOT NULL,  -- Hash bcrypt de la API key
    status ENUM('active','suspended','deleted') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    metadata JSON NULL  -- Datos adicionales del cliente
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_clients_status ON clients(status);
```

**Campos importantes**:
- `id`: Identificador único del cliente (usado como `client_id`)
- `api_key_hash`: Hash bcrypt de la API key del cliente
- `status`: Estado del cliente (`active`, `suspended`, `deleted`)
- `metadata`: JSON con información adicional (opcional)

#### Tabla `client_limits`

Límites de rate limiting y mensajes por cliente:

```sql
CREATE TABLE client_limits (
    client_id VARCHAR(64) NOT NULL PRIMARY KEY,
    requests_per_minute INT NOT NULL DEFAULT 60,
    requests_per_hour INT NOT NULL DEFAULT 1000,
    requests_per_day INT NOT NULL DEFAULT 10000,
    messages_per_day INT NOT NULL DEFAULT 500,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Límites por defecto**:
- `requests_per_minute`: 60
- `requests_per_hour`: 1000
- `requests_per_day`: 10000
- `messages_per_day`: 500

### Tablas Modificadas

#### Tabla `jobs`

Agregado campo `client_id`:

```sql
ALTER TABLE jobs 
ADD COLUMN client_id VARCHAR(64) NOT NULL DEFAULT 'default';

CREATE INDEX idx_jobs_client_status ON jobs(client_id, status);
CREATE INDEX idx_jobs_client_created ON jobs(client_id, created_at);
```

#### Tabla `job_tasks`

Agregado campo `client_id`:

```sql
ALTER TABLE job_tasks 
ADD COLUMN client_id VARCHAR(64) NOT NULL DEFAULT 'default';

CREATE INDEX idx_job_tasks_client_status ON job_tasks(client_id, status);
CREATE INDEX idx_job_tasks_client_created ON job_tasks(client_id, created_at);
```

#### Tabla `messages_sent`

Agregado campo `client_id`:

```sql
ALTER TABLE messages_sent 
ADD COLUMN client_id VARCHAR(64) NOT NULL DEFAULT 'default';

CREATE INDEX idx_messages_sent_client_id ON messages_sent(client_id);
CREATE INDEX idx_messages_sent_client_id_dest ON messages_sent(client_id, dest_username);
```

### Cliente por Defecto

Se crea automáticamente un cliente `"default"` para compatibilidad con datos existentes:

```sql
INSERT IGNORE INTO clients (id, name, email, api_key_hash, status)
VALUES ('default', 'Default Client', NULL, '', 'active');
```

---

## Autenticación

### Métodos de Autenticación

El sistema soporta dos métodos de autenticación:

#### 1. API Key (Header `X-Api-Key`)

**Uso**:
```bash
curl -X POST "https://api.example.com/ext/followings/enqueue" \
  -H "X-Api-Key: tu-api-key-aqui" \
  -H "Content-Type: application/json" \
  -d '{"target_username": "usuario", "limit": 10}'
```

**Cómo funciona**:
1. El cliente envía su API key en el header `X-Api-Key`
2. El sistema busca en la BD un cliente con esa API key (hash bcrypt)
3. Si encuentra y está `active`, retorna el `client_id`
4. Si no encuentra o está `suspended`/`deleted`, retorna 401

#### 2. JWT Token (Header `Authorization: Bearer`)

**Uso**:
```bash
# Primero, obtener token
curl -X POST "https://api.example.com/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "tu-api-key-aqui"}'

# Respuesta:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "token_type": "bearer",
#   "expires_in": 3600,
#   "client_id": "client123"
# }

# Luego, usar el token
curl -X POST "https://api.example.com/ext/followings/enqueue" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{"target_username": "usuario", "limit": 10}'
```

**Cómo funciona**:
1. Cliente obtiene token con `/api/auth/login` usando su API key
2. Token JWT contiene `client_id` y `scopes`
3. Token válido por 60 minutos (configurable)
4. Cliente usa token en header `Authorization: Bearer <token>`
5. Sistema verifica token y extrae `client_id`

### Endpoint de Login

**POST** `/api/auth/login`

**Request**:
```json
{
  "api_key": "tu-api-key-aqui"
}
```

**Response (éxito)**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "client_id": "client123"
}
```

**Response (error)**:
```json
{
  "detail": "API key inválida"
}
```
Status: `401 Unauthorized`

**Response (cliente suspendido)**:
```json
{
  "detail": "Cliente suspendido o eliminado"
}
```
Status: `403 Forbidden`

---

## API Endpoints

### Endpoints Modificados

Todos los endpoints ahora validan el `client_id` y filtran datos por cliente.

#### POST `/ext/followings/enqueue`

**Autenticación**: `X-Api-Key` o `Authorization: Bearer`

**Request**:
```json
{
  "target_username": "usuario_instagram",
  "limit": 10
}
```

**Headers**:
- `X-Api-Key`: API key del cliente (o `Authorization: Bearer <token>`)
- `X-Account`: (Opcional) Cuenta worker a usar

**Response**:
```json
{
  "job_id": "job:abc123def456"
}
```

**Comportamiento**:
- Crea un job con `client_id` del cliente autenticado
- La tarea inicial también tiene el `client_id` correcto

#### POST `/ext/analyze/enqueue`

Similar a `/ext/followings/enqueue`, pero para análisis de perfiles.

#### GET `/jobs/{job_id}/summary`

**Autenticación**: `X-Api-Key` o `Authorization: Bearer`

**Validación de Ownership**:
- Verifica que el job pertenezca al cliente autenticado
- Si el job es de otro cliente, retorna `403 Forbidden`
- Si el job no existe, retorna `404 Not Found`

**Response**:
```json
{
  "queued": 5,
  "sent": 3,
  "ok": 2,
  "error": 1
}
```

#### POST `/api/send/pull`

**Autenticación**: `X-Api-Key` o `Authorization: Bearer`

**Request**:
```json
{
  "limit": 10
}
```

**Headers**:
- `X-Account`: Cuenta worker (requerido)

**Comportamiento**:
- Solo retorna tareas del cliente autenticado
- Filtra por `client_id` en la query SQL

**Response**:
```json
{
  "items": [
    {
      "job_id": "job:123",
      "task_id": "task:456",
      "dest_username": "target_user",
      "payload": {"message": "Hello"}
    }
  ]
}
```

---

## Uso Práctico

### Escenario 1: Cliente Nuevo

#### Paso 1: Crear Cliente en la BD

```python
from scrapinsta.infrastructure.db.client_repo_sql import ClientRepoSQL
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Crear repositorio
client_repo = ClientRepoSQL("mysql://user:pass@localhost/db")

# Generar API key (en producción, usar secrets)
api_key = "scrapinsta_abc123def456xyz789"
api_key_hash = pwd_context.hash(api_key)

# Crear cliente
client_repo.create(
    client_id="cliente_empresa_xyz",
    name="Empresa XYZ",
    email="contacto@empresa-xyz.com",
    api_key_hash=api_key_hash,
    metadata={
        "plan": "premium",
        "contact_person": "Juan Pérez"
    }
)

# Configurar límites
client_repo.update_limits("cliente_empresa_xyz", {
    "requests_per_minute": 200,
    "requests_per_hour": 10000,
    "requests_per_day": 100000,
    "messages_per_day": 5000
})
```

#### Paso 2: Cliente Usa la API

```bash
# Opción A: Con API Key directa
curl -X POST "https://api.example.com/ext/followings/enqueue" \
  -H "X-Api-Key: scrapinsta_abc123def456xyz789" \
  -H "Content-Type: application/json" \
  -d '{"target_username": "usuario_objetivo", "limit": 50}'

# Opción B: Con JWT Token (recomendado)
# 1. Obtener token
TOKEN=$(curl -X POST "https://api.example.com/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "scrapinsta_abc123def456xyz789"}' \
  | jq -r '.access_token')

# 2. Usar token
curl -X POST "https://api.example.com/ext/followings/enqueue" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_username": "usuario_objetivo", "limit": 50}'
```

### Escenario 2: Consultar Estado de Jobs

```bash
# Obtener resumen de un job
curl -X GET "https://api.example.com/jobs/job:abc123/summary" \
  -H "X-Api-Key: scrapinsta_abc123def456xyz789"

# Respuesta:
# {
#   "queued": 10,
#   "sent": 5,
#   "ok": 3,
#   "error": 2
# }
```

### Escenario 3: Worker Externo (Pull de Tareas)

```bash
# Worker obtiene tareas pendientes
curl -X POST "https://api.example.com/api/send/pull" \
  -H "X-Api-Key: scrapinsta_abc123def456xyz789" \
  -H "X-Account: worker_account_1" \
  -H "Content-Type: application/json" \
  -d '{"limit": 20}'

# Solo recibe tareas del cliente autenticado
```

### Escenario 4: Suspender Cliente

```python
# Suspender cliente (por ejemplo, por pago pendiente)
client_repo.update_status("cliente_empresa_xyz", "suspended")

# El cliente ya no puede autenticarse
# Todos los intentos de login retornan 403
```

---

## Configuración

### Variables de Entorno

```bash
# JWT Secret Key (para firmar tokens)
JWT_SECRET_KEY=tu-clave-secreta-muy-segura-aqui

# API Shared Secret (fallback si no hay clientes configurados)
API_SHARED_SECRET=clave-compartida-para-modo-simple

# Base de datos
DB_HOST=localhost
DB_PORT=3306
DB_USER=scrapinsta_user
DB_PASS=password_seguro
DB_NAME=scrapinsta_db
```

### Configuración de Clientes (Opcional)

Si quieres usar múltiples clientes con configuración JSON:

```bash
export API_CLIENTS_JSON='{
  "cliente1": {
    "key": "api-key-cliente1",
    "scopes": ["fetch", "analyze", "send"],
    "rate": {"rpm": 100}
  },
  "cliente2": {
    "key": "api-key-cliente2",
    "scopes": ["fetch"],
    "rate": {"rpm": 50}
  }
}'
```

**Nota**: En producción, es mejor usar la BD (`clients` table) en lugar de JSON.

---

## Migraciones

### Aplicar Migraciones

Las migraciones están en `alembic/versions/`:

```bash
# Ver estado actual
alembic current

# Aplicar todas las migraciones pendientes
alembic upgrade head

# Ver historial
alembic history

# Revertir última migración
alembic downgrade -1
```

### Migraciones del Sistema Multi-Tenant

1. **`4be063954351_add_clients_and_client_limits_tables.py`**
   - Crea tablas `clients` y `client_limits`
   - Crea índices necesarios

2. **`4854b6aaf779_add_client_id_to_existing_tables.py`**
   - Agrega `client_id` a `jobs`, `job_tasks`, `messages_sent`
   - Crea índices compuestos
   - Migra datos existentes al cliente `"default"`

### Migración de Datos Existentes

Si tienes datos en producción:

1. Las migraciones automáticamente asignan `client_id = 'default'` a todos los registros existentes
2. Se crea el cliente `"default"` automáticamente
3. No se pierden datos

**Verificación post-migración**:

```sql
-- Verificar que todos los jobs tienen client_id
SELECT COUNT(*) as total, 
       COUNT(client_id) as con_client_id,
       COUNT(DISTINCT client_id) as clientes_unicos
FROM jobs;

-- Verificar cliente default
SELECT * FROM clients WHERE id = 'default';
```

---

## Seguridad y Aislamiento

### Aislamiento de Datos

**Garantías**:
1. **Jobs**: Cada job tiene un `client_id`. Los clientes solo ven sus propios jobs
2. **Tareas**: Cada tarea tiene un `client_id`. `lease_tasks()` filtra por cliente
3. **Mensajes**: Cada mensaje enviado tiene un `client_id` para auditoría
4. **Validación de Ownership**: Endpoints validan que el recurso pertenezca al cliente

**Ejemplo de Aislamiento**:

```python
# Cliente A intenta acceder a job de Cliente B
# Request:
GET /jobs/job:123/summary
Headers: X-Api-Key: api_key_cliente_a

# Sistema:
# 1. Autentica Cliente A → client_id = "cliente_a"
# 2. Obtiene client_id del job → "cliente_b"
# 3. Compara: "cliente_a" != "cliente_b"
# 4. Retorna: 403 Forbidden
```

### Seguridad de API Keys

**Almacenamiento**:
- API keys se almacenan como **hash bcrypt** (no en texto plano)
- Hash bcrypt es resistente a fuerza bruta
- Cada hash es único (mismo salt por defecto)

**Generación Segura de API Keys**:

```python
import secrets

# Generar API key segura
api_key = f"scrapinsta_{secrets.token_urlsafe(32)}"
# Ejemplo: scrapinsta_abc123def456ghi789jkl012mno345pqr678stu901vwx234yz

# Hash para almacenar
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
api_key_hash = pwd_context.hash(api_key)
```

### Rate Limiting por Cliente

Cada cliente tiene límites configurables:

```python
# Obtener límites actuales
limits = client_repo.get_limits("cliente123")
# {
#   "requests_per_minute": 100,
#   "requests_per_hour": 5000,
#   "requests_per_day": 100000,
#   "messages_per_day": 2000
# }

# Actualizar límites
client_repo.update_limits("cliente123", {
    "requests_per_minute": 200,  # Aumentar límite
    "requests_per_hour": 10000,
    "requests_per_day": 100000,
    "messages_per_day": 5000
})
```

**Nota**: El rate limiting real se implementa en el middleware de FastAPI usando estos límites.

### Estados de Cliente

**`active`**: Cliente puede usar la API normalmente

**`suspended`**: Cliente no puede autenticarse (login retorna 403)

**`deleted`**: Cliente no aparece en búsquedas (soft delete)

**Cambiar estado**:

```python
# Suspender cliente
client_repo.update_status("cliente123", "suspended")

# Reactivar cliente
client_repo.update_status("cliente123", "active")

# Eliminar (soft delete)
client_repo.update_status("cliente123", "deleted")
```

---

## Ejemplos de Código

### Python: Cliente Completo

```python
import requests
from scrapinsta.infrastructure.auth.jwt_auth import create_access_token

class ScrapInstaClient:
    def __init__(self, api_key: str, base_url: str = "https://api.example.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.token = None
        self.token_expires = None
    
    def _get_token(self):
        """Obtener o renovar token JWT"""
        if self.token and self.token_expires > time.time():
            return self.token
        
        response = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"api_key": self.api_key}
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        self.token_expires = time.time() + data["expires_in"]
        return self.token
    
    def enqueue_followings(self, target_username: str, limit: int = 10):
        """Encolar extracción de followings"""
        token = self._get_token()
        response = requests.post(
            f"{self.base_url}/ext/followings/enqueue",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_username": target_username, "limit": limit}
        )
        response.raise_for_status()
        return response.json()["job_id"]
    
    def get_job_summary(self, job_id: str):
        """Obtener resumen de job"""
        token = self._get_token()
        response = requests.get(
            f"{self.base_url}/jobs/{job_id}/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return response.json()

# Uso
client = ScrapInstaClient(api_key="scrapinsta_abc123def456xyz789")
job_id = client.enqueue_followings("usuario_instagram", limit=50)
summary = client.get_job_summary(job_id)
print(f"Job {job_id}: {summary['ok']} completados, {summary['error']} errores")
```

### JavaScript/Node.js: Cliente Completo

```javascript
class ScrapInstaClient {
    constructor(apiKey, baseUrl = 'https://api.example.com') {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl;
        this.token = null;
        this.tokenExpires = null;
    }
    
    async getToken() {
        if (this.token && this.tokenExpires > Date.now()) {
            return this.token;
        }
        
        const response = await fetch(`${this.baseUrl}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: this.apiKey })
        });
        
        const data = await response.json();
        this.token = data.access_token;
        this.tokenExpires = Date.now() + (data.expires_in * 1000);
        return this.token;
    }
    
    async enqueueFollowings(targetUsername, limit = 10) {
        const token = await this.getToken();
        const response = await fetch(`${this.baseUrl}/ext/followings/enqueue`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                target_username: targetUsername,
                limit: limit
            })
        });
        
        const data = await response.json();
        return data.job_id;
    }
    
    async getJobSummary(jobId) {
        const token = await this.getToken();
        const response = await fetch(`${this.baseUrl}/jobs/${jobId}/summary`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        return await response.json();
    }
}

// Uso
const client = new ScrapInstaClient('scrapinsta_abc123def456xyz789');
const jobId = await client.enqueueFollowings('usuario_instagram', 50);
const summary = await client.getJobSummary(jobId);
console.log(`Job ${jobId}: ${summary.ok} completados`);
```

---

## Troubleshooting

### Error: "API key inválida"

**Causas posibles**:
1. API key incorrecta
2. Hash en BD no coincide con la API key
3. Cliente no existe en BD

**Solución**:
```python
# Verificar cliente en BD
client = client_repo.get_by_api_key("tu-api-key")
if not client:
    print("Cliente no encontrado o API key incorrecta")
    
# Verificar hash manualmente
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Obtener hash de BD y verificar
is_valid = pwd_context.verify("tu-api-key", hash_de_bd)
```

### Error: "Token inválido o expirado"

**Causas posibles**:
1. Token expirado (más de 60 minutos)
2. Token modificado o inválido
3. `JWT_SECRET_KEY` cambió

**Solución**:
- Obtener nuevo token con `/api/auth/login`
- Verificar que `JWT_SECRET_KEY` no haya cambiado

### Error: "No tienes acceso a este job"

**Causa**: Intentas acceder a un job de otro cliente

**Solución**:
- Verificar que el `job_id` pertenezca a tu cliente
- Usar el `client_id` correcto en la autenticación

### Cliente no puede autenticarse

**Verificar estado**:
```sql
SELECT id, name, status FROM clients WHERE id = 'tu_client_id';
```

Si `status != 'active'`, cambiar a `active`:
```python
client_repo.update_status("tu_client_id", "active")
```

---

## ⚠️ Mejoras Pendientes y Limitaciones Conocidas

### 1. ⚠️ DEFAULT 'default' en Columnas client_id (CRÍTICO)

**Estado Actual**:
- Las columnas `client_id` tienen `DEFAULT 'default'` para facilitar la migración
- Esto permite que si alguien olvida pasar `client_id`, se asigne al cliente default
- **Riesgo**: Ruptura silenciosa de aislamiento

**Solución Implementada**:
- ✅ Validación explícita en `create_job()` y `add_task()` que rechaza `client_id` vacío
- ✅ Migración `4fd85ff91943_remove_default_from_client_id.py` para quitar el DEFAULT después de migrar datos
- ⚠️ **Pendiente**: Aplicar la migración en producción después de verificar que todo el código pasa `client_id` explícitamente

**Recomendación**:
```bash
# 1. Verificar que no hay NULLs
SELECT COUNT(*) FROM jobs WHERE client_id IS NULL;
SELECT COUNT(*) FROM job_tasks WHERE client_id IS NULL;
SELECT COUNT(*) FROM messages_sent WHERE client_id IS NULL;

# 2. Aplicar migración para quitar DEFAULT
alembic upgrade head

# 3. Verificar que el código siempre pasa client_id explícitamente
# (ya está validado en create_job/add_task)
```

### 2. Rate Limiting: Enforcement Implementado ✅

**Estado Actual**:
- ✅ Rate limiting **SÍ está implementado** en `_rate_limit()`
- ✅ Se aplica en todos los endpoints que requieren autenticación
- ✅ Usa token bucket algorithm en memoria
- ✅ Límites se leen desde `client_limits` table
- ✅ Retorna `429 Too Many Requests` cuando se excede

**Cómo Funciona**:
```python
# En cada endpoint:
client = _auth_client(...)  # Obtiene límites del cliente
_rate_limit(client, request)  # Aplica rate limiting

# Si se excede:
# - Retorna HTTP 429
# - Logs el evento
# - Incrementa métrica rate_limit_hits_total
```

**Limitaciones**:
- ⚠️ Rate limiting es en memoria (no persiste entre reinicios)
- ⚠️ No hay rate limiting distribuido (cada instancia tiene su propio contador)
- ⚠️ No se cuenta `messages_per_day` automáticamente (solo `requests_per_minute`)

**Mejoras Futuras**:
- Usar Redis para rate limiting distribuido
- Implementar contador de `messages_per_day`
- Agregar rate limiting por hora y por día

### 3. Scopes JWT: Enforcement Implementado ✅

**Estado Actual**:
- ✅ Scopes **SÍ se validan** en los endpoints con `_check_scope()`
- ✅ Cada endpoint valida el scope requerido:
  - `/ext/followings/enqueue` → requiere scope `"fetch"`
  - `/ext/analyze/enqueue` → requiere scope `"analyze"`
  - `/api/send/pull` → requiere scope `"send"`
  - `/api/send/result` → requiere scope `"send"`

**Cómo Funciona**:
```python
# En cada endpoint:
client = _auth_client(...)  # Obtiene scopes del cliente/token
_check_scope(client, "fetch")  # Valida que tenga el scope requerido

# Si no tiene el scope:
# - Retorna HTTP 403 Forbidden
# - Mensaje: "scope insuficiente"
```

**Scopes Disponibles**:
- `"fetch"`: Permite crear jobs de extracción de followings
- `"analyze"`: Permite crear jobs de análisis de perfiles
- `"send"`: Permite hacer pull de tareas y reportar resultados

**Ejemplo de Uso**:
```python
# Cliente con scope limitado
client_repo.create(...)
# Token con scopes: ["fetch"]  # Solo puede hacer fetch, no analyze ni send

# Intento de usar endpoint analyze:
POST /ext/analyze/enqueue
# → 403 Forbidden: "scope insuficiente"
```

### 4. Workers Autenticados: Mejora Futura

**Estado Actual**:
- Workers usan la misma API key del cliente
- No hay separación entre credenciales de cliente y worker

**Mejora Recomendada (Futuro)**:
- Crear tabla `workers` con:
  - `worker_id`: Identificador único del worker
  - `client_id`: Cliente al que pertenece
  - `api_key_hash`: API key específica del worker
  - `scopes`: Limitados a `["pull_only"]`
- Workers autentican con su propia API key
- Permite revocar acceso de workers sin afectar al cliente

**No es crítico ahora**, pero mejora la seguridad si el sistema crece.

---

## Resumen

El sistema multi-tenant proporciona:

✅ **Aislamiento completo** de datos por cliente  
✅ **Autenticación segura** con API keys (bcrypt) y JWT  
✅ **Rate limiting** implementado y funcionando  
✅ **Scopes JWT** validados en todos los endpoints  
✅ **Validación de ownership** en todos los endpoints  
✅ **Validación explícita** de client_id (no permite valores vacíos)  
✅ **Migraciones seguras** sin pérdida de datos  
✅ **Compatibilidad** con datos existentes (cliente "default")  

### ⚠️ Mejoras Pendientes

1. **Quitar DEFAULT 'default'**: Migración `4fd85ff91943` lista para aplicar después de verificar que todo el código pasa `client_id` explícitamente
2. **Rate limiting distribuido**: Actualmente en memoria, considerar Redis para múltiples instancias
3. **Contador de messages_per_day**: Implementar enforcement automático
4. **Workers autenticados**: Separar credenciales de workers del cliente (mejora futura)

Para más información, consulta:
- `docs/MIGRACIONES_BD.md` - Detalles de migraciones
- `alembic/versions/` - Scripts de migración
- `tests/integration/test_auth_endpoints.py` - Ejemplos de uso en tests

