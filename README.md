# ScrapInsta4 - Herramienta Avanzada de Scraping para Instagram

## 📋 Descripción

ScrapInsta4 es una herramienta profesional de scraping para Instagram que permite automatizar tareas como obtener seguidores, analizar perfiles y enviar mensajes de forma masiva. Está diseñada con **arquitectura modular**, **procesamiento concurrente mediante múltiples workers** y un **sistema de router inteligente** para distribuir las tareas de manera balanceada entre los workers disponibles.

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

#### 🎯 **Router (Balanceador de Carga)**
- **Token Bucket Algorithm** para rate limiting
- **Round-robin** con fairness real
- **Gestión de colas** por worker
- **Mapeo de tareas** para seguimiento

#### 👷 **Workers (Procesadores)**
- **Procesamiento paralelo** de tareas
- **Gestión de sesiones** independiente
- **Manejo de errores** robusto
- **Comunicación asíncrona** con el router

#### 🗄️ **Base de Datos**
- **MySQL** para persistencia
- **Tablas optimizadas** con índices
- **Gestión de conexiones** segura
- **Backup automático** de datos

## 📁 Estructura del Proyecto

### 📂 Directorios Principales

#### `/src/` - Código fuente principal
- **`main.py`** - Punto de entrada principal que coordina workers y router
- **`__init__.py`** - Archivo de inicialización del paquete

##### `/src/core/worker/` - Sistema de Workers
- **`instagram_worker.py`** - Lógica principal del worker de Instagram
- **`router.py`** - Router inteligente para balanceo de carga
- **`task_handlers.py`** - Manejadores de cada tipo de tarea
- **`messages.py`** - Definición de tipos de mensajes
- **`__init__.py`**

##### `/src/core/auth/` - Gestión de Autenticación
- **`session_controller.py`** - Controlador de sesiones de Instagram
- **`cookie_manager.py`** - Gestión de cookies y sesiones
- **`login.py`** - Login automático y validación de sesión
- **`__init__.py`**

##### `/src/core/browser/` - Gestión del Navegador
- **`driver_manager.py`** - Configuración avanzada de WebDriver
- **`proxy_extension.py`** - Extensiones y configuración de proxies
- **`__init__.py`**

##### `/src/core/profile/` - Análisis de Perfiles
- **`evaluator.py`** - Evaluación de perfiles (engagement, success_score)
- **`fetch_profile.py`** - Obtención de datos de perfiles
- **`fetch_followings.py`** - Obtención de listas de seguidos
- **`send_message.py`** - Envío de mensajes automáticos
- **`__init__.py`**
- **`utils/`** - Funciones auxiliares:
  - `text_analysis.py` - Análisis de texto
  - `reels.py` - Procesamiento de reels (metricas)
  - `basic_stats.py` - Estadísticas básicas
  - `detection.py` - Detección de restricciónes
  - `__init__.py`

##### `/src/core/resources/` - Gestión de Recursos
- **`resource_manager.py`** - Gestión de recursos y límites
- **`__init__.py`**

##### `/src/core/utils/` - Utilidades
- **`undetected.py`** - Utilidades anti detección de bots
- **`selenium_helpers.py`** - Helpers para Selenium
- **`parse.py`** - Utilidades de parsing
- **`chatgpt.py`** - Integración con ChatGPT
- **`humanize_helpers.py`** - Helpers de humanización
- **`__init__.py`**

#### `/src/config/` - Configuración
- **`settings.py`** - Configuración principal
- **`accounts.json`** - Lista de cuentas del sistema
- **`keywords.json`** - Palabras clave para análisis
- **`account_utils.py`** - Utilidades de cuentas
- **`config.py`** - Configuración adicional
- **`__init__.py`**

#### `/src/db/` - Base de Datos
- **`init_db.py`** - Inicialización de la base de datos
- **`repositories.py`** - Repositorios de datos
- **`connection.py`** - Gestión de conexiones
- **`__init__.py`**

### 📂 Directorios de Datos

#### `/data/`
- **`profiles/`** - Datos de perfiles analizados
- **`cookies/`** - Cookies de sesión persistentes

---

## 🚀 Instalación y Configuración

### Requisitos Previos

- **Python 3.9+**
- **Google Chrome** (versión 136+)
- **MySQL 8.0+** (recomendado)
- **Git** (para clonar el repositorio)

### Instalación Paso a Paso

#### 1. **Clonar el Repositorio**
```bash
git clone <url-del-repositorio>
cd ScrapInsta4
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

#### 2. **Ajustar Configuración (`src/config/settings.py`)**
```python
# Configuración de Instagram
INSTAGRAM_CONFIG = {
    'target_profile': 'perfil_objetivo',
    'max_followings': 1000,
    'cookie_refresh_interval': 15,  # minutos
}

# Configuración de Rate Limiting
BROWSER_CONFIG = {
    'timeouts': {
        'page_load': 90,
        'script': 30,
        'implicit': 2,
        'explicit': 20
    }
}
```

#### 3. **Configurar Variables de Entorno**

**Crear archivo .env:**
```bash
cp .env.example .env
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

# Configuración de Instagram
INSTAGRAM_TARGET_PROFILE=perfil_objetivo
INSTAGRAM_MAX_FOLLOWINGS=1000
INSTAGRAM_COOKIE_REFRESH_INTERVAL=15
```

**⚠️ Importante:** 
- El archivo `.env` contiene información sensible y NO debe subirse al repositorio
- Usa `.env.example` como plantilla para configurar tu `.env` local

### Ejecución

#### **Ejecución Local**
```bash
python src/main.py
```

#### **Ejecución con Docker**
```bash
# Construir imagen
docker build -t scrapinsta4 .

# Ejecutar contenedor
docker run -v $(pwd)/data:/data scrapinsta4

# O usar docker-compose
docker-compose up
```

---

## 🔧 Funcionalidades Principales

### 1. **Sistema de Router Inteligente**
- ✅ **Balanceo de carga** automático entre workers
- ✅ **Rate limiting** con algoritmo Token Bucket
- ✅ **Fairness real** en distribución de tareas
- ✅ **Gestión de colas** por worker individual
- ✅ **Seguimiento de tareas** en tiempo real

### 2. **Análisis Avanzado de Perfiles**
- ✅ **Extracción de métricas** (seguidores, seguidos, posts)
- ✅ **Análisis de engagement** con IA
- ✅ **Clasificación por rubro** automática
- ✅ **Detección de perfiles privados/verificados**
- ✅ **Análisis de contenido** con ChatGPT

### 3. **Obtención de Seguidores**
- ✅ **Extracción masiva** de listas de seguidores
- ✅ **Persistencia en base de datos** MySQL
- ✅ **Recuperación de datos** desde DB
- ✅ **Filtrado inteligente** de perfiles

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

### 6. **Base de Datos MySQL**
- ✅ **Tabla `filtered_profiles`** - Perfiles analizados
- ✅ **Tabla `followings`** - Relaciones de seguimiento
- ✅ **Índices optimizados** para consultas rápidas
- ✅ **Gestión de conexiones** segura

---

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

### **Gestión de Recursos**
- ✅ **Límites de memoria** por worker
- ✅ **Timeouts configurables** para todas las operaciones
- ✅ **Cleanup automático** de recursos
- ✅ **Monitoreo de salud** de workers

---

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
---

## 🐳 Docker y Despliegue

### **Dockerfile Optimizado**
```dockerfile
FROM python:3.9-slim
# Instalación de Chrome y dependencias
# Configuración de Xvfb para headless
# Optimizaciones de seguridad
```

### **Docker Compose**
```yaml
version: '3.8'
services:
  scraper:
    build: .
    volumes:
      - ./data:/data
    env_file:
      - .env
```

### **Variables de Entorno**
```bash
# .env
OPENAI_API_KEY=tu_api_key_de_openai
MYSQL_HOST=localhost
MYSQL_USER=scrapinsta
MYSQL_PASSWORD=4312
MYSQL_DATABASE=scrapinsta_db
INSTAGRAM_TARGET_PROFILE=perfil_objetivo
INSTAGRAM_MAX_FOLLOWINGS=1000
INSTAGRAM_COOKIE_REFRESH_INTERVAL=15
```
---

**⚠️ Descargo de Responsabilidad:** El uso indebido de esta herramienta es responsabilidad del usuario. Los desarrolladores no se hacen responsables del mal uso de la aplicación.
