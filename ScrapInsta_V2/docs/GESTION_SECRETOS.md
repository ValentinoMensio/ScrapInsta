# 🔐 Gestión de Secretos

Sistema completo de gestión de secretos con soporte para múltiples proveedores y cifrado de datos sensibles.

## Índice

1. [Descripción General](#descripción-general)
2. [Proveedores Soportados](#proveedores-soportados)
3. [Configuración](#configuración)
4. [Cifrado de Contraseñas](#cifrado-de-contraseñas)
5. [Uso en Código](#uso-en-código)
6. [Migración](#migración)
7. [Buenas Prácticas](#buenas-prácticas)

## Descripción General

El sistema de gestión de secretos proporciona:

- ✅ **Abstracción para múltiples proveedores**: AWS Secrets Manager, HashiCorp Vault, Azure Key Vault, Variables de Entorno
- ✅ **Cifrado AES-256-GCM**: Para contraseñas de Instagram almacenadas
- ✅ **Fallback automático**: A variables de entorno si el gestor externo no está disponible
- ✅ **Separación por ambiente**: Secretos diferentes para dev/staging/prod
- ✅ **Carga dinámica**: Los secretos se cargan automáticamente al inicio

## Proveedores Soportados

### 1. Variables de Entorno (ENV)

**Uso**: Desarrollo local y pruebas

**Configuración**:
```bash
SECRETS_PROVIDER=env
# Opcional: prefijo para variables de entorno
SECRETS_ENV_PREFIX=SCRAPINSTA_
```

**Ejemplo**:
```bash
DB_PASS=my_password
API_SHARED_SECRET=my_secret
OPENAI_API_KEY=sk-...
```

### 2. AWS Secrets Manager / Parameter Store

**Uso**: Producción en AWS

**Configuración**:
```bash
SECRETS_PROVIDER=aws
AWS_REGION=us-east-1
AWS_USE_PARAMETER_STORE=false  # true para Parameter Store, false para Secrets Manager
```

**Instalación**:
```bash
pip install boto3
```

**Configurar credenciales AWS**:
```bash
# Opción 1: Variables de entorno
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret

# Opción 2: AWS CLI
aws configure

# Opción 3: IAM Role (si ejecutas en EC2/ECS/Lambda)
```

**Ejemplo de uso**:

**Secrets Manager**:
```bash
# Crear secreto
aws secretsmanager create-secret \
  --name /scrapinsta/prod/db_pass \
  --secret-string "my_password"

# Obtener secreto (el código lo hace automáticamente)
aws secretsmanager get-secret-value \
  --secret-id /scrapinsta/prod/db_pass
```

**Parameter Store**:
```bash
# Crear parámetro cifrado
aws ssm put-parameter \
  --name "/scrapinsta/prod/db_pass" \
  --value "my_password" \
  --type "SecureString"

# Obtener parámetro (el código lo hace automáticamente)
aws ssm get-parameter \
  --name "/scrapinsta/prod/db_pass" \
  --with-decryption
```

**Rutas de secretos**:
- Las rutas siguen el formato: `/scrapinsta/{environment}/{secret_name}`
- El ambiente se toma de la variable `ENV` (local/dev/staging/prod)

### 3. HashiCorp Vault

**Uso**: Entornos con Vault ya instalado

**Configuración**:
```bash
SECRETS_PROVIDER=vault
VAULT_ADDR=http://vault.example.com:8200
VAULT_TOKEN=your-vault-token
```

**Instalación**:
```bash
pip install hvac
```

**Ejemplo de uso**:
```bash
# Autenticarse en Vault
export VAULT_TOKEN=$(vault auth -method=userpass username=myuser password=mypass -format=json | jq -r .auth.client_token)

# Escribir secreto
vault kv put secret/scrapinsta/prod/db_pass value=my_password

# El código lo lee automáticamente
```

**Rutas de secretos**:
- Las rutas siguen el formato: `scrapinsta/{environment}/{secret_name}`
- Usa el mount point `secret` por defecto (configurable)

### 4. Azure Key Vault

**Uso**: Producción en Azure

**Configuración**:
```bash
SECRETS_PROVIDER=azure
AZURE_VAULT_URL=https://my-vault.vault.azure.net/
```

**Instalación**:
```bash
pip install azure-keyvault-secrets azure-identity
```

**Autenticación**:
- Azure CLI: `az login`
- Managed Identity (si ejecutas en Azure)
- Service Principal: configurar variables `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`

**Ejemplo de uso**:
```bash
# Crear secreto
az keyvault secret set \
  --vault-name my-vault \
  --name db_pass \
  --value "my_password"

# El código lo lee automáticamente
```

## Configuración

### Variables de Entorno

Agrega estas variables a tu `.env` o configuración del sistema:

```bash
# Proveedor de secretos (env/aws/vault/azure)
SECRETS_PROVIDER=env

# Ambiente (dev/staging/prod)
ENV=local

# Cifrado de contraseñas
ENCRYPTION_KEY=your-32-char-minimum-master-key-here
ENABLE_ENCRYPTED_PASSWORDS=true
```

### Configuración por Proveedor

Ver secciones anteriores para configuración específica de cada proveedor.

## Cifrado de Contraseñas

El sistema soporta cifrado AES-256-GCM para contraseñas de Instagram almacenadas.

### Generar Clave de Cifrado

```python
import secrets
# Generar una clave segura de 32 bytes
key = secrets.token_hex(32)
print(key)
```

### Cifrar una Contraseña

```python
from scrapinsta.crosscutting.encryption import encrypt_password

# Cifrar contraseña
encrypted = encrypt_password("mi_password")
print(encrypted)
# Output: base64-encoded encrypted string
```

### Formato de Cuentas con Contraseñas Cifradas

**JSON con contraseñas cifradas**:
```json
[
  {
    "username": "cuenta1@example.com",
    "password": "eyJjaXBoZXJ0ZXh0IjogIi4uLiIsICJub25jZSI6ICIuLi4ifQ==",
    "proxy": null
  }
]
```

**JSON con contraseñas en texto plano** (se soporta para compatibilidad):
```json
[
  {
    "username": "cuenta1@example.com",
    "password": "mi_password",
    "proxy": null
  }
]
```

El sistema detecta automáticamente si una contraseña está cifrada y la descifra antes de usarla.

### Herramienta CLI para Cifrar

Puedes crear un script para cifrar contraseñas:

```python
#!/usr/bin/env python3
"""Script para cifrar contraseñas de Instagram."""

import sys
from scrapinsta.crosscutting.encryption import encrypt_password, is_encrypted_password

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python encrypt_password.py <password>")
        sys.exit(1)
    
    password = sys.argv[1]
    
    if is_encrypted_password(password):
        print("La contraseña ya está cifrada")
        sys.exit(0)
    
    encrypted = encrypt_password(password)
    print(f"Contraseña cifrada: {encrypted}")
```

## Uso en Código

### Obtener un Secreto

```python
from scrapinsta.crosscutting.secrets import get_secret

# Obtener secreto (usa el gestor configurado)
db_password = get_secret("db_pass")
api_key = get_secret("openai_api_key")
```

### Usar el Gestor Directamente

```python
from scrapinsta.crosscutting.secrets import get_secrets_manager

manager = get_secrets_manager()
password = manager.get_secret("db_pass")
all_secrets = manager.get_secrets("db_")  # Obtener todos con prefijo
```

### Cifrar/Descifrar en Código

```python
from scrapinsta.crosscutting.encryption import (
    encrypt_password,
    decrypt_password,
    is_encrypted_password
)

# Cifrar
encrypted = encrypt_password("mi_password")

# Verificar si está cifrada
if is_encrypted_password(value):
    decrypted = decrypt_password(value)
```

## Migración

### Migrar Contraseñas Existentes a Cifrado

1. **Generar clave de cifrado**:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

2. **Agregar a `.env`**:
```bash
ENCRYPTION_KEY=<clave-generada>
ENABLE_ENCRYPTED_PASSWORDS=true
```

3. **Cifrar contraseñas**:
```python
import json
from scrapinsta.crosscutting.encryption import encrypt_password

# Leer cuentas actuales
with open("docker/secrets/instagram_accounts.json") as f:
    accounts = json.load(f)

# Cifrar contraseñas
for account in accounts:
    if not is_encrypted_password(account["password"]):
        account["password"] = encrypt_password(account["password"])

# Guardar
with open("docker/secrets/instagram_accounts.json", "w") as f:
    json.dump(accounts, f, indent=2)
```

### Migrar a Gestor de Secretos Externo

1. **Configurar proveedor** (ver sección de configuración)
2. **Migrar secretos**:
   - AWS: Usar CLI o consola para crear secretos
   - Vault: Usar CLI para escribir secretos
   - Azure: Usar CLI o portal para crear secretos
3. **Actualizar `SECRETS_PROVIDER`** en `.env`
4. **Eliminar secretos de `.env`** (opcional, el sistema los busca primero en el gestor)

## Buenas Prácticas

### 🔒 Seguridad

1. **Nunca commitees secretos reales**:
   - Usa `.gitignore` para proteger `.env` y archivos de secretos
   - Usa `env.example` como plantilla sin valores reales

2. **Rotación de secretos**:
   - Rota contraseñas regularmente
   - Usa herramientas de rotación automática del gestor de secretos

3. **Separación por ambiente**:
   - Usa ambientes diferentes (dev/staging/prod)
   - No compartas secretos entre ambientes

4. **Protección de la clave de cifrado**:
   - Guarda `ENCRYPTION_KEY` en un gestor de secretos
   - Nunca la commitees ni la compartas

### 🏗️ Arquitectura

1. **Desarrollo local**:
   - Usa `SECRETS_PROVIDER=env` (variables de entorno)
   - Usa `.env` para secretos locales

2. **Producción**:
   - Usa gestor de secretos externo (AWS/Vault/Azure)
   - No uses variables de entorno en producción
   - Usa Managed Identity o IAM Roles cuando sea posible

3. **Tests**:
   - Usa `reset_secrets_manager()` en tests para aislar
   - Usa mocks para gestores externos

### 📝 Logging

El sistema registra automáticamente:
- Cuándo se carga un secreto desde el gestor
- Errores al acceder a secretos (sin exponer valores)
- Cambios de proveedor

## Secretos Soportados

Los siguientes secretos se cargan automáticamente desde el gestor:

- `db_pass`: Contraseña de base de datos
- `api_shared_secret`: Clave compartida de API
- `jwt_secret_key`: Clave para firmar tokens JWT
- `openai_api_key`: API key de OpenAI
- `redis_password`: Contraseña de Redis
- `instagram_accounts`: JSON con cuentas de Instagram (cifradas opcionalmente)

## Troubleshooting

### El gestor de secretos no se inicializa

- Verifica que `SECRETS_PROVIDER` esté configurado correctamente
- Para AWS/Vault/Azure, verifica las credenciales de autenticación
- Revisa los logs para ver errores específicos

### Las contraseñas cifradas no se descifran

- Verifica que `ENCRYPTION_KEY` esté configurada
- Asegúrate de usar la misma clave con la que se cifró
- Verifica que `ENABLE_ENCRYPTED_PASSWORDS=true`

### Los secretos no se cargan desde el gestor

- El sistema usa fallback automático a variables de entorno
- Verifica que los secretos existan en el gestor externo
- Revisa los logs para ver qué proveedor se está usando

## Referencias

- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [HashiCorp Vault](https://www.vaultproject.io/)
- [Azure Key Vault](https://azure.microsoft.com/services/key-vault/)
- [cryptography library](https://cryptography.io/)

