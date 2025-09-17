# ScrapInsta4 - Herramienta de Scraping para Instagram

## 📋 Descripción

ScrapInsta4 es una herramienta profesional de scraping para Instagram que permite automatizar tareas como obtener seguidores, analizar perfiles y enviar mensajes de forma masiva. Está diseñada con **arquitectura modular**, **procesamiento concurrente mediante múltiples workers** y un **sistema de router inteligente** para distribuir las tareas de manera balanceada.

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

#### 2. **Configurar Variables de Entorno**

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

# Configuración del Pool de Conexiones
MYSQL_POOL_SIZE=10
MYSQL_CONNECTION_TIMEOUT=60

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
docker build -t scrapinsta4 .

# Ejecutar contenedor
docker run -v $(pwd)/data:/data scrapinsta4

# O usar docker-compose
docker-compose up
```

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

---

**⚠️ Descargo de Responsabilidad:** El uso indebido de esta herramienta es responsabilidad del usuario. Los desarrolladores no se hacen responsables del mal uso de la aplicación.