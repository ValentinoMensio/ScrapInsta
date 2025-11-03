# 🔐 Security Policy

## Información Sensible

Este proyecto **NO incluye** información sensible en el repositorio:

- ✅ Credenciales reales de Instagram
- ✅ API keys de producción
- ✅ Passwords de base de datos reales
- ✅ Cookies o sesiones activas
- ✅ Datos de perfiles de usuarios

## Configuración

### Variables de Entorno

Copia `env.example` a `.env` y configura tus valores:

```bash
cp env.example .env
```

### Cuentas Instagram

Configura tus cuentas en `docker/secrets/instagram_accounts.json` (este archivo NO se sube a Git):

```json
[
  {
    "username": "tu_cuenta",
    "password": "tu_password"
  }
]
```

## Archivos Ignorados por Git

El `.gitignore` protege automáticamente:

- `.env` y todas las variantes `.env.*`
- `docker/secrets/instagram_accounts.json`
- `src/data/` (datos de scraping y cookies)
- `*.log` (logs con información sensible)
- Credenciales y certificados: `*.pem`, `*.key`, etc.

## Reportar Vulnerabilidades

Si encuentras un problema de seguridad, por favor:

1. **NO** crees un issue público
2. Contacta al mantenedor del proyecto
3. Incluye detalles sobre el problema encontrado

## Buenas Prácticas

- ❌ NUNCA subas credenciales reales a Git
- ✅ Usa siempre `env.example` como plantilla
- ✅ Cambia todas las contraseñas por defecto
- ✅ Usa variables de entorno para secrets
- ✅ Revisa `.gitignore` antes de commitear

## Producción

Para despliegues en producción:

1. Usa un gestor de secretos (AWS Secrets Manager, HashiCorp Vault, etc.)
2. Configura HTTPS obligatorio
3. Implementa rate limiting estricto
4. Usa autenticación JWT con expiración
5. Monitorea logs de accesos sospechosos

