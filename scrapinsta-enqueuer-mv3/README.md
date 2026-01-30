# ScrapInsta Enqueuer (MV3)

Extensión mínima para encolar `fetch_followings` y `analyze_profile` hacia tu API, usando la cuenta del cliente en el header `X-Account`. Soporta la nueva autenticación con clientes, incluyendo `X-Client-Id` opcional y scopes.

## ✨ Características
- ✅ **Dos modos de operación**: Followings y Analyze
- ✅ **Autenticación flexible**: X-Api-Key, Bearer Token o JWT automático
- ✅ **Multi-tenant**: Soporte para X-Client-Id con scopes y rate limiting
- ✅ **Seguimiento de Jobs**: Ver progreso en tiempo real con auto-refresh
- ✅ **Interfaz moderna**: Popup tipo Instagram con gradientes y badges de estado
- ✅ **Validación robusta**: Errores claros y manejo de respuestas
- ✅ **Compatible con ScrapInsta V2**: Respeta 100% la API del backend

## 🎯 Qué hace

### Modo Followings
- Extrae `target_username` y `limit`
- Envía `POST /ext/followings/enqueue` con:
  ```json
  {
    "target_username": "usuario_objetivo",
    "limit": 50
  }
  ```
- Respuesta esperada: `{ "job_id": "job:..." }`

### Modo Analyze
- Extrae `usernames[]` (uno por línea o separados por coma) y `batch_size`
- Envía `POST /ext/analyze/enqueue` con:
  ```json
  {
    "usernames": ["user1", "user2"],
    "batch_size": 25
  }
  ```
- Respuesta esperada: `{ "job_id": "job:...", "total_items": 2 }`

### 📊 Seguimiento de Jobs
Después de encolar un trabajo, la extensión muestra automáticamente:
- **Barra de progreso** visual con porcentaje
- **Badges de estado** con contadores:
  - ⏳ **Queued**: Tareas en cola
  - 🚀 **Sent**: Tareas en ejecución
  - ✅ **OK**: Tareas completadas
  - ❌ **Error**: Tareas fallidas
- **Auto-refresh** cada 5 segundos mientras el job está en progreso
- **Persistencia**: Recuerda el último job al reabrir el popup

El estado se obtiene de `GET /jobs/{job_id}/summary`:
```json
{
  "queued": 10,
  "sent": 2,
  "ok": 5,
  "error": 1
}
```

### Headers enviados
- `X-Account: <usuario_instagram_cliente>` - **requerido**
- `X-Client-Id: <cliente>` - **opcional** (requerido si tu API usa múltiples clientes con scopes/rate limit)
- `X-Api-Key: <token>` **o** `Authorization: Bearer <token>`
- `Content-Type: application/json`

### Página de Opciones
- API Base URL: URL base de tu API
- Auth mode: `X-Api-Key` o `Bearer Token`
- Token: Tu token de autenticación
- X-Account: Tu usuario de Instagram
- X-Client-Id: (Opcional) ID del cliente
- Default limit: Límite por defecto para followings

## ⚙️ Permisos
- `host_permissions: "<all_urls>"` solo para desarrollo. En producción, reemplaza por tu dominio:
  ```json
  "host_permissions": ["https://api.tu-dominio.com/*"]
  ```

## 🚀 Instalación

### Cargar en Chrome/Edge/Brave
1. Abre `chrome://extensions`
2. Activa **Developer mode** (esquina superior derecha)
3. Click en **Load unpacked**
4. Selecciona la carpeta de este proyecto

## 📋 Flujo de uso

1. **Configurar** en **Opciones**:
   - API Base URL (ej: `https://api.tu-dominio.com`)
   - Modo de autenticación (X-Api-Key o Bearer)
   - Token de autenticación
   - X-Account (tu usuario Instagram)
   - (Opcional) X-Client-Id
   - Límite por defecto

2. **Probar conexión** con el botón "Probar" en Opciones (verifica `/health`)

3. **Encolar trabajo** desde el popup:
   - **Followings**: Ingresa username objetivo y límite → Click "Encolar"
   - **Analyze**: Pega usernames (uno por línea o coma) y batch_size → Click "Encolar analyze"

4. **Seguir progreso** en tiempo real:
   - Automáticamente se muestra el estado del job
   - Badges de colores indican: queued, sent, ok, error
   - Barra de progreso muestra % completado
   - Auto-refresh cada 5 segundos (se detiene al completar)
   - Botón "Ver Estado" para refrescar manualmente

5. El **servidor/dispatcher** procesará según tu lógica configurada

## 🔌 API Backend Requerida

Esta extensión está diseñada para trabajar con **ScrapInsta V2**. Endpoints esperados:

- **GET** `/health` - Health check
- **POST** `/api/auth/login` - Login JWT (opcional, si usas autenticación JWT)
- **POST** `/ext/followings/enqueue` - Encolar fetch followings
- **POST** `/ext/analyze/enqueue` - Encolar análisis de perfiles
- **GET** `/jobs/{job_id}/summary` - Resumen de job (para seguimiento de progreso)

Ver [README del backend](../ScrapInsta_V2/README.md) para más detalles sobre la API.

---

## 📬 Envío de mensajes (DM)

El envío de DMs se hace desde **instagram.com/direct** (inbox), no desde el perfil:

1. La extensión abre **instagram.com/direct/**
2. Busca al usuario en el buscador (`input[placeholder="Search"]`)
3. Abre la conversación (enlace a `/direct/t/...` o botón "Message")
4. Escribe en la caja de mensaje (contenteditable / Lexical)
5. Pulsa **Send** (botón detectado por `svg[aria-label="Send"]` dentro de `div[role="button"]`)

Así se evita depender del botón "Message" del perfil, que cambia más a menudo en el DOM.

---

## 🐛 Cómo ver qué pasa al enviar mensajes (debug)

El envío de DMs usa **dos contextos**: el **Service Worker** (background) y el **content script** en la pestaña de Instagram. Para ver el error hay que abrir **dos consolas**.

### 1. Logs del Service Worker (background)

1. Abre `chrome://extensions`
2. Localiza **ScrapInsta Enqueuer** y haz clic en **“Service worker”** (o “Inspeccionar vistas: background page”)
3. Se abre DevTools con la consola del background
4. Ahí verás:
   - `[BG] Task obtenida:` cuando hay una tarea
   - `[BG] Enviando mensaje send_dm al content script...`
   - `[BG] Resultado del content script:` (éxito o fallo)
   - Si falla: `[BG] send_dm falló: <error> steps: [...]`

### 2. Logs del content script (pestaña Instagram)

1. **Abre una pestaña** en `https://www.instagram.com` (o el perfil donde se envía el DM)
2. Pulsa **F12** (o clic derecho → Inspeccionar) para abrir DevTools **en esa pestaña**
3. Ve a la pestaña **Console**
4. Cuando la extensión intente enviar un DM verás:
   - `[ScrapInsta] ========== sendDM INICIO ==========`
   - `[ScrapInsta] Paso 1: navegar al perfil`
   - `[ScrapInsta] Paso 2: click en botón Message`
   - Si algo falla: `[ScrapInsta] ERROR: ...` o `[ScrapInsta] TIMEOUT: no se encontró ...`
   - Al final: `[ScrapInsta] ========== sendDM FIN ========== success: false error: message_button_not_found steps: [...]`

### Qué mirar según el síntoma

| Síntoma | Dónde mirar | Qué suele ser |
|--------|-------------|----------------|
| “Entra al perfil y no hace nada” | Consola de **Instagram** (content script) | Si ves `Paso 2: click en botón Message` y luego `TIMEOUT: no se encontró botón Message` → Instagram cambió el DOM; hay que actualizar los selectores del botón “Message”. |
| No aparece ningún log `[ScrapInsta]` en Instagram | Service Worker + pestaña | El content script no se inyectó: comprueba que la URL sea `*://www.instagram.com/*` y recarga la pestaña de Instagram. |
| Error en el background al enviar mensaje | Consola del **Service Worker** | `Could not establish connection. Receiving end does not exist` → la pestaña se cerró o el content script no está listo; a veces ayuda aumentar la espera antes de `sendMessage`. |

### Orden recomendado al debugear

1. Abre **primero** la pestaña de Instagram y su DevTools (consola).
2. Abre **después** la consola del Service Worker.
3. Desde el popup, inicia el envío o usa “Procesar ahora”.
4. Observa en la consola de **Instagram** en qué paso se queda (Paso 1, Paso 2, etc.) y si aparece `ERROR` o `TIMEOUT`.
5. El `error` y `steps` del resultado en el Service Worker te dicen hasta qué paso llegó el content script.
