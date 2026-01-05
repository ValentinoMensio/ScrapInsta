# 📊 Guía de Métricas - Qué Puedes Leer

Esta guía explica qué información útil puedes extraer de las métricas del sistema.

## 🎯 Endpoints Disponibles

### 1. `/metrics/summary` ⭐ **RECOMENDADO**
Formato JSON legible con resumen de métricas clave.

### 2. `/metrics/json`
Todas las métricas en formato JSON estructurado (más detallado).

### 3. `/metrics`
Formato Prometheus estándar (para scraping con Prometheus/Grafana).

---

## 📈 Información que Puedes Leer

### 🔵 HTTP - Requests y Latencia

**Qué puedes ver:**
- **Total de requests** por endpoint
- **Requests por status code** (200, 404, 500, etc.)
- **Requests por método HTTP** (GET, POST, etc.)
- **Latencia promedio** por endpoint (en milisegundos)
- **Total de requests procesados** por endpoint

**Ejemplo de lectura:**
```json
{
  "http": {
    "requests_by_endpoint": {
      "/health": {
        "total": 15.0,
        "by_status": {"200": 15.0},
        "by_method": {"GET": 15.0}
      },
      "/api/send/pull": {
        "total": 42.0,
        "by_status": {"200": 40.0, "401": 2.0},
        "by_method": {"POST": 42.0}
      }
    },
    "latency_by_endpoint": {
      "/health": {
        "avg_ms": 2.68,
        "total_requests": 11
      },
      "/api/send/pull": {
        "avg_ms": 125.5,
        "total_requests": 40
      }
    }
  }
}
```

**Qué te dice:**
- ✅ El endpoint `/health` es rápido (2.68ms promedio)
- ⚠️ El endpoint `/api/send/pull` es más lento (125.5ms) - podría necesitar optimización
- ❌ Hay 2 requests con error 401 (autenticación fallida) en `/api/send/pull`

---

### 🟢 Tasks - Tareas Procesadas

**Qué puedes ver:**
- **Tareas procesadas por tipo** (analyze_profile, fetch_followings, send_message)
- **Estado de las tareas** (success, failed, pending)

**Ejemplo de lectura:**
```json
{
  "tasks": {
    "processed_by_kind": {
      "analyze_profile": {
        "success": 150.0,
        "failed": 5.0
      },
      "fetch_followings": {
        "success": 200.0,
        "failed": 2.0
      },
      "send_message": {
        "success": 1000.0,
        "failed": 10.0
      }
    }
  }
}
```

**Qué te dice:**
- ✅ `analyze_profile`: 150 exitosas, 5 fallidas (97% éxito)
- ✅ `fetch_followings`: 200 exitosas, 2 fallidas (99% éxito)
- ⚠️ `send_message`: 1000 exitosas, 10 fallidas (99% éxito, pero 10 fallos pueden ser preocupantes)

---

### 🟡 Jobs - Trabajos Activos

**Qué puedes ver:**
- **Jobs activos por estado** (pending, running, completed, failed)

**Ejemplo de lectura:**
```json
{
  "jobs": {
    "active_by_status": {
      "pending": 5.0,
      "running": 2.0,
      "completed": 100.0,
      "failed": 3.0
    }
  }
}
```

**Qué te dice:**
- 📊 Hay 5 jobs esperando procesamiento
- 🔄 Hay 2 jobs ejecutándose actualmente
- ✅ 100 jobs completados exitosamente
- ❌ 3 jobs fallaron (podría indicar un problema)

---

### 🔴 Database - Base de Datos

**Qué puedes ver:**
- **Conexiones activas** a la base de datos

**Ejemplo de lectura:**
```json
{
  "database": {
    "active_connections": 3.0
  }
}
```

**Qué te dice:**
- ✅ 3 conexiones activas (normal si hay workers procesando)
- ⚠️ Si es 0 constantemente, podría indicar que no hay actividad
- ❌ Si es muy alto (>50), podría indicar un problema de pooling

---

### 🟠 Rate Limiting - Límites de Velocidad

**Qué puedes ver:**
- **Total de hits de rate limit** (cuántas veces se bloqueó un request por límite de velocidad)

**Ejemplo de lectura:**
```json
{
  "rate_limiting": {
    "total_hits": 15.0
  }
}
```

**Qué te dice:**
- ✅ 0 hits = no hay problemas de rate limiting
- ⚠️ >0 hits = algunos requests fueron bloqueados (normal si hay protección activa)
- ❌ Muchos hits = podría necesitar ajustar los límites o la estrategia

---

### 🟣 Workers - Trabajadores

**Qué puedes ver:**
- **Workers activos** por cuenta

**Ejemplo de lectura:**
```json
{
  "workers": {
    "total_active": 3.0
  }
}
```

**Qué te dice:**
- ✅ 3 workers activos procesando tareas
- ⚠️ 0 workers = no hay procesamiento activo
- ❌ Muchos workers = alto consumo de recursos

---

## 🎯 Casos de Uso Prácticos

### 1. **Monitoreo de Salud del Sistema**
```bash
curl http://localhost:8000/metrics/summary | jq '.http.latency_by_endpoint'
```
- Verifica que los endpoints respondan rápido
- Identifica endpoints lentos que necesitan optimización

### 2. **Detección de Errores**
```bash
curl http://localhost:8000/metrics/summary | jq '.http.requests_by_endpoint[].by_status'
```
- Encuentra endpoints con muchos errores (status 4xx, 5xx)
- Identifica problemas de autenticación (401) o servidor (500)

### 3. **Monitoreo de Carga**
```bash
curl http://localhost:8000/metrics/summary | jq '.jobs.active_by_status'
```
- Ve cuántos jobs están pendientes vs ejecutándose
- Identifica si el sistema está sobrecargado

### 4. **Análisis de Performance**
```bash
curl http://localhost:8000/metrics/summary | jq '.http.latency_by_endpoint | to_entries | sort_by(.value.avg_ms) | reverse'
```
- Ordena endpoints por latencia (más lentos primero)
- Identifica cuellos de botella

### 5. **Monitoreo de Tareas**
```bash
curl http://localhost:8000/metrics/summary | jq '.tasks.processed_by_kind'
```
- Ve qué tipos de tareas se procesan más
- Identifica tareas con alta tasa de fallos

---

## 📊 Comparación: Formato Prometheus vs JSON

### Formato Prometheus (difícil de leer):
```
http_requests_total{endpoint="/health",method="GET",status_code="200"} 15.0
http_request_duration_seconds_count{endpoint="/health",method="GET"} 15.0
http_request_duration_seconds_sum{endpoint="/health",method="GET"} 0.0402
```

### Formato JSON Summary (fácil de leer):
```json
{
  "http": {
    "requests_by_endpoint": {
      "/health": {
        "total": 15.0,
        "by_status": {"200": 15.0},
        "by_method": {"GET": 15.0}
      }
    },
    "latency_by_endpoint": {
      "/health": {
        "avg_ms": 2.68,
        "total_requests": 15
      }
    }
  }
}
```

---

## 🚀 Comandos Útiles

### Ver resumen completo:
```bash
curl http://localhost:8000/metrics/summary | jq .
```

### Solo HTTP:
```bash
curl http://localhost:8000/metrics/summary | jq '.http'
```

### Solo latencia:
```bash
curl http://localhost:8000/metrics/summary | jq '.http.latency_by_endpoint'
```

### Solo tareas:
```bash
curl http://localhost:8000/metrics/summary | jq '.tasks'
```

### Endpoints más lentos:
```bash
curl http://localhost:8000/metrics/summary | jq '.http.latency_by_endpoint | to_entries | sort_by(.value.avg_ms) | reverse | .[0:5]'
```

---

## ⚠️ Valores a Monitorear

### 🟢 Normal (Saludable):
- Latencia promedio < 100ms para endpoints simples
- 0 errores 5xx
- Workers activos > 0 (si hay trabajo)
- Rate limit hits bajo (< 10)

### 🟡 Atención (Revisar):
- Latencia promedio > 500ms
- Algunos errores 4xx/5xx (< 5%)
- Jobs pending acumulándose
- Rate limit hits moderados (10-50)

### 🔴 Crítico (Acción Inmediata):
- Latencia promedio > 2000ms
- Muchos errores 5xx (> 10%)
- Jobs pending creciendo sin procesarse
- Rate limit hits muy altos (> 100)
- Workers = 0 cuando hay trabajo pendiente

---

## 📝 Notas

- Las métricas se acumulan desde el inicio del proceso
- Para resetear métricas, reinicia la API
- El formato Prometheus (`/metrics`) es para scraping automático
- El formato JSON (`/metrics/summary`) es para lectura humana
- Usa `jq` para formatear y filtrar el JSON fácilmente

