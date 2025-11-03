# ScrapInsta Enqueuer (MV3)

Extensión mínima para encolar `fetch_followings` y `analyze_profile` hacia tu API, usando la cuenta del cliente en el header `X-Account`. Soporta la nueva autenticación con clientes, incluyendo `X-Client-Id` opcional y scopes.

## ✨ Características
- ✅ **Dos modos de operación**: Followings y Analyze
- ✅ **Autenticación flexible**: X-Api-Key o Bearer Token
- ✅ **Multi-tenant**: Soporte para X-Client-Id con scopes y rate limiting
- ✅ **Interfaz moderna**: Popup tipo Instagram con gradientes
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

4. El **servidor/dispatcher** procesará según tu lógica configurada

## 🔌 API Backend Requerida

Esta extensión está diseñada para trabajar con **ScrapInsta V2**. Endpoints esperados:

- **GET** `/health` - Health check
- **POST** `/ext/followings/enqueue` - Encolar fetch followings
- **POST** `/ext/analyze/enqueue` - Encolar análisis de perfiles
- **GET** `/jobs/{job_id}/summary` - Resumen de job (no usado por extensión)

Ver [README del backend](../ScrapInsta_V2/README.md) para más detalles sobre la API.
