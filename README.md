# ScrapInsta - Herramienta de Scraping para Instagram

## 📋 Descripción

ScrapInsta es una herramienta profesional de scraping para Instagram que permite automatizar tareas como obtener seguidores, analizar perfiles y enviar mensajes de forma masiva. Está diseñada con **arquitectura modular**, **procesamiento concurrente mediante múltiples workers** y un **sistema de router inteligente** para distribuir las tareas de manera balanceada.

### ✨ Características Principales

- 🚀 **Procesamiento concurrente** con múltiples workers
- 🎯 **Router inteligente** con balanceo de carga y rate limiting
- 🗄️ **Base de datos MySQL** para persistencia de datos
- 🤖 **Integración con ChatGPT** para análisis de perfiles
- 🛡️ **Bypass de detección** con undetected-chromedriver
- 🐳 **Soporte Docker** para despliegue fácil
- 📊 **Sistema de logging** avanzado
- 🔄 **Gestión de sesiones** con cookies persistentes

## 🏗️ Arquitectura del Sistema

### 🎯 **Router (Balanceador de Carga)**
- **Token Bucket Algorithm** para rate limiting
- **Round-robin** con fairness real
- **Gestión de colas** por worker
- **Mapeo de tareas** para seguimiento

### 👷 **Workers (Procesadores)**
- **Procesamiento paralelo** de tareas
- **Gestión de sesiones** independiente
- **Manejo de errores** robusto
- **Comunicación asíncrona** con el router

### 🗄️ **Base de Datos**
- **MySQL** para persistencia
- **Connection pooling** para optimización
- **Tablas optimizadas** con índices
- **Gestión de conexiones** segura

### ⚡ **Sistema de Excepciones**
- **Excepciones personalizadas** por categoría
- **Manejo específico** de errores de DB, Selenium, validación
- **Logging detallado** con contexto
- **Recuperación automática** para errores recuperables

### 🔒 **Validación de Datos**
- **Esquemas Pydantic** para validación robusta
- **Validación de perfiles** de Instagram
- **Validación de tareas** del sistema
- **Validación de followings** y datos de DB

## 📁 Estructura del Proyecto

```
src/
├── main.py                    # Punto de entrada principal
├── core/
│   ├── worker/               # Sistema de Workers
│   ├── auth/                 # Gestión de Autenticación
│   ├── browser/              # Gestión del Navegador
│   ├── profile/              # Análisis de Perfiles
│   ├── resources/             # Gestión de Recursos
│   └── utils/                # Utilidades
├── config/                   # Configuración
├── db/                       # Base de Datos
├── exceptions/               # Sistema de Excepciones
├── schemas/                  # Validación de Esquemas
└── utils/                    # Utilidades Generales
```

## 🚀 Instalación y Configuración

### Requisitos Previos

- **Python 3.9+**
- **Google Chrome** (versión 136+)
- **MySQL 8.0+** (recomendado)
- **Git** (para clonar el repositorio)

### Dependencias Principales

El proyecto utiliza las siguientes dependencias principales:

- **selenium==4.34.2** - Automatización del navegador
- **undetected-chromedriver==3.5.5** - Driver Chrome sin detección
- **mysql-connector-python==8.0.33** - Conexión a base de datos MySQL
- **openai==1.98.0** - Integración con ChatGPT para análisis
- **python-dotenv==1.1.1** - Gestión de variables de entorno
- **beautifulsoup4==4.13.4** - Parsing de HTML
- **requests==2.32.4** - Cliente HTTP

### Instalación Paso a Paso

#### 1. **Clonar el Repositorio**
```bash
git clone <url-del-repositorio>
cd ScrapInsta
```

#### 2. **Crear Entorno Virtual**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate     # Windows
```

#### 3. **Instalar Dependencias**
```bash
pip install -r requirements.txt
```

#### 4. **Configurar Base de Datos MySQL**

**Crear usuario y base de datos:**
```sql
CREATE USER 'scrapinsta'@'localhost' IDENTIFIED BY '4312';
CREATE DATABASE scrapinsta_db;
GRANT ALL PRIVILEGES ON scrapinsta_db.* TO 'scrapinsta'@'localhost';
FLUSH PRIVILEGES;
```

**Inicializar tablas:**
```bash
python src/db/init_db.py
```

### Configuración

#### 1. **Configurar Cuentas (`src/config/accounts.json`)**
```json
{
  "accounts": [
    {
      "username": "tu_usuario_1",
      "password": "tu_password_1"
    },
    {
      "username": "tu_usuario_2", 
      "password": "tu_password_2"
    }
  ]
}
```

#### 2. **Configurar Variables de Entorno**

**Crear archivo .env:**
```bash
# Crear archivo .env desde cero (no hay .env.example incluido)
touch .env
```

**Editar .env con tus credenciales:**
```bash
# Configuración de API Keys
OPENAI_API_KEY=tu_api_key_de_openai_aqui

# Configuración de Base de Datos
MYSQL_HOST=localhost
MYSQL_USER=scrapinsta
MYSQL_PASSWORD=tu_password_mysql
MYSQL_DATABASE=scrapinsta_db
MYSQL_PORT=3306
MYSQL_CONNECTION_TIMEOUT=60

# Configuración del Pool de Conexiones
MYSQL_POOL_SIZE=10

# Configuración de Instagram
INSTAGRAM_TARGET_PROFILE=perfil_objetivo
INSTAGRAM_MAX_FOLLOWINGS=1000
INSTAGRAM_COOKIE_REFRESH_INTERVAL=15
```

### Ejecución

#### **Ejecución Local**
```bash
python src/main.py
```

#### **Ejecución con Docker**
```bash
# Construir imagen
docker build -t scrapinsta .

# Ejecutar contenedor
docker run -v $(pwd)/data:/data --env-file .env scrapinsta

# O usar docker-compose (recomendado)
docker-compose up
```

**Nota:** El contenedor Docker incluye:
- Python 3.9-slim
- Google Chrome instalado automáticamente
- Xvfb para ejecución headless
- Todas las dependencias preinstaladas

## 🔧 Funcionalidades Principales

### 1. **Sistema de Router Inteligente**
- ✅ **Balanceo de carga** automático entre workers
- ✅ **Rate limiting** con algoritmo Token Bucket
- ✅ **Fairness real** en distribución de tareas
- ✅ **Gestión de colas** por worker individual
- ✅ **Seguimiento de tareas** en tiempo real
- ✅ **Mapeo de tareas** para seguimiento completo

### 2. **Análisis Avanzado de Perfiles**
- ✅ **Extracción de métricas** (seguidores, seguidos, posts)
- ✅ **Análisis de engagement** con IA
- ✅ **Clasificación por rubro** automática
- ✅ **Detección de perfiles privados/verificados**
- ✅ **Análisis de contenido** con ChatGPT
- ✅ **Validación de datos** con esquemas Pydantic

### 3. **Obtención de Seguidores**
- ✅ **Extracción masiva** de listas de seguidores
- ✅ **Persistencia en base de datos** MySQL
- ✅ **Recuperación de datos** desde DB
- ✅ **Filtrado inteligente** de perfiles
- ✅ **Connection pooling** para optimización

### 4. **Sistema de Mensajería**
- ✅ **Envío automático** de mensajes personalizados
- ✅ **Personalización con IA** usando ChatGPT
- ✅ **Control de límites** y rate limiting
- ✅ **Seguimiento de mensajes** enviados

### 5. **Gestión de Sesiones Avanzada**
- ✅ **Cookies persistentes** por cuenta
- ✅ **Rotación automática** de cuentas
- ✅ **Renovación de sesiones** automática
- ✅ **Gestión de proxies** (opcional)

## 🔄 Flujo de Trabajo

### **Proceso Principal**

1. **Inicialización**
   - Carga de cuentas desde `accounts.json`
   - Inicio de workers por cuenta
   - Configuración del router inteligente

2. **Obtención de Seguidores**
   - Worker designado extrae seguidores del perfil objetivo
   - Datos se almacenan en base de datos MySQL
   - Fallback a datos existentes si la extracción falla

3. **Análisis de Perfiles**
   - Router distribuye perfiles entre workers disponibles
   - Cada worker analiza perfiles asignados
   - Resultados se almacenan con métricas detalladas

4. **Procesamiento Concurrente**
   - Múltiples workers procesan tareas en paralelo
   - Rate limiting previene bloqueos de Instagram
   - Sistema de reintentos automático para errores recuperables

5. **Finalización**
   - KPIs y métricas de rendimiento
   - Limpieza de recursos y conexiones
   - Logs detallados del proceso completo

## 🛡️ Características de Seguridad

### **Bypass de Detección**
- ✅ **undetected-chromedriver** para evitar detección
- ✅ **Rotación de User-Agents** realista
- ✅ **Comportamiento humano** simulado
- ✅ **Delays aleatorios** entre acciones

### **Rate Limiting**
- ✅ **Token Bucket** por cuenta
- ✅ **Límites configurables** por tipo de acción
- ✅ **Backoff exponencial** en caso de errores
- ✅ **Pausas inteligentes** entre requests

## 📊 Monitoreo y Logging

### **Sistema de Logs Avanzado**
- ✅ **Logs estructurados** por worker
- ✅ **Niveles configurables** (DEBUG, INFO, WARNING, ERROR)
- ✅ **Rotación automática** de archivos de log
- ✅ **Filtrado de logs** de Selenium

### **Métricas en Tiempo Real**
- ✅ **Tareas procesadas** por worker
- ✅ **Tiempo de ejecución** por tarea
- ✅ **Errores y reintentos** por worker
- ✅ **Estado de la base de datos**

## 🚀 **Mejoras Implementadas (v2.0)**

### ⚡ **Sistema de Manejo Específico de Excepciones**

#### **Excepciones Categorizadas:**
- **`DatabaseExceptions`** - Errores de conexión, consultas, transacciones
- **`SeleniumExceptions`** - Timeouts, elementos no encontrados, navegación
- **`ValidationExceptions`** - Errores de validación de datos con Pydantic
- **`BusinessExceptions`** - Lógica de negocio (perfiles privados, rate limits)
- **`NetworkExceptions`** - Problemas de conectividad y API

### 🛠️ **Connection Pooling para MySQL**

#### **Optimizaciones de Base de Datos:**
- ✅ **Pool de conexiones** - Reutilización eficiente de conexiones
- ✅ **Gestión automática** - Context managers para manejo seguro
- ✅ **Configuración flexible** - Tamaño de pool y timeouts configurables
- ✅ **Manejo de errores** - Excepciones específicas para problemas de DB

### 🔒 **Validación de Esquemas con Pydantic**

#### **Esquemas Implementados:**
- **`ProfileSchemas`** - Validación de perfiles de Instagram
- **`TaskSchemas`** - Validación de tareas del sistema
- **`DatabaseSchemas`** - Validación de datos de base de datos

#### **Características:**
- ✅ **Validación robusta** - Tipos, rangos, formatos
- ✅ **Mensajes claros** - Errores de validación descriptivos
- ✅ **Fallbacks seguros** - Valores por defecto para datos inválidos
- ✅ **Filtrado inteligente** - Solo campos relevantes para cada contexto

### 🔐 **Gestión Segura de Configuración**

#### **Variables de Entorno:**
- ✅ **API Keys** - OpenAI y otras APIs externas
- ✅ **Base de Datos** - Credenciales y configuración de MySQL
- ✅ **Instagram** - Configuración de scraping y rate limiting
- ✅ **Pool de Conexiones** - Configuración de performance

#### **Seguridad:**
- ✅ **Archivo .env** - Configuración local no versionada
- ✅ **Gitignore completo** - Protección de archivos sensibles
- ✅ **Validación de configuración** - Verificación de valores requeridos

## 🔧 Solución de Problemas Comunes

### **Problemas de Instalación**

#### **Error: Chrome no encontrado**
```bash
# En Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y google-chrome-stable

# Verificar instalación
google-chrome --version
```

#### **Error: MySQL connection failed**
- Verificar que MySQL esté ejecutándose: `sudo systemctl status mysql`
- Confirmar credenciales en el archivo `.env`
- Verificar que la base de datos existe: `mysql -u scrapinsta -p -e "SHOW DATABASES;"`

#### **Error: OpenAI API Key**
- Verificar que la API key esté configurada en `.env`
- Confirmar que la key tenga créditos disponibles
- Verificar permisos de la API key

### **Problemas de Ejecución**

#### **Workers no inician**
- Verificar que las cuentas en `accounts.json` sean válidas
- Revisar logs para errores específicos
- Confirmar que Chrome esté instalado correctamente

#### **Rate limiting de Instagram**
- Reducir `INSTAGRAM_MAX_FOLLOWINGS` en `.env`
- Aumentar `INSTAGRAM_COOKIE_REFRESH_INTERVAL`
- Verificar que las cuentas no estén bloqueadas

#### **Problemas de Docker**
```bash
# Limpiar contenedores e imágenes
docker system prune -a

# Reconstruir imagen
docker build --no-cache -t scrapinsta .

# Verificar logs del contenedor
docker logs <container_id>
```

### **Problemas de Base de Datos**

#### **Tablas no se crean**
```bash
# Ejecutar inicialización manual
python src/db/init_db.py

# Verificar conexión
python -c "from src.db.connection import get_db_connection_context; print('DB OK')"
```

#### **Pool de conexiones agotado**
- Aumentar `MYSQL_POOL_SIZE` en `.env`
- Verificar configuración de MySQL: `max_connections`

### **Logs y Debugging**

#### **Habilitar logs detallados**
Modificar `src/config/settings.py`:
```python
LOGGING_CONFIG = {
    'root': {
        'level': 'DEBUG',  # Cambiar de INFO a DEBUG
        'handlers': ['console'],
    },
}
```

#### **Verificar estado de workers**
Los logs muestran el estado de cada worker:
```
[INFO] Worker 1 (PID: 1234) iniciado
[INFO] Workers listos: 1/3
[INFO] FOLLOWINGS (perfil_origen): 150
```

---

**⚠️ Descargo de Responsabilidad:** El uso indebido de esta herramienta es responsabilidad del usuario. Los desarrolladores no se hacen responsables del mal uso de la aplicación.