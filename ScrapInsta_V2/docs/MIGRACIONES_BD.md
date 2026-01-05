# Guía de Migraciones de Base de Datos con Alembic

Esta guía explica cómo usar Alembic para gestionar las migraciones de base de datos en ScrapInsta V2.

## ¿Qué es Alembic?

Alembic es una herramienta de migraciones de base de datos para SQLAlchemy. Permite:
- **Versionar el schema** de forma incremental
- **Aplicar cambios** de forma segura y controlada
- **Hacer rollback** si algo falla
- **Trabajar en equipo** con historial de cambios

## Estructura

```
alembic/
├── env.py              # Configuración de Alembic (conexión a BD)
├── versions/           # Migraciones (archivos Python)
│   └── 075fb1b4ff0e_initial_schema.py
└── script.py.mako      # Template para nuevas migraciones

alembic.ini             # Configuración principal
```

## Configuración

Alembic está configurado para usar automáticamente las credenciales de `Settings`:
- Lee variables de entorno desde `.env`
- Conecta a MySQL usando PyMySQL
- Usa el mismo DSN que el resto de la aplicación

## Comandos Básicos

### Ver estado actual

```bash
alembic current
```

Muestra la versión de migración actualmente aplicada.

### Ver historial

```bash
alembic history
```

Muestra todas las migraciones disponibles.

### Aplicar migraciones

```bash
# Aplicar todas las migraciones pendientes
alembic upgrade head

# Aplicar hasta una versión específica
alembic upgrade <revision_id>

# Aplicar una migración hacia adelante
alembic upgrade +1
```

### Rollback (revertir)

```bash
# Revertir una migración
alembic downgrade -1

# Revertir hasta una versión específica
alembic downgrade <revision_id>

# Revertir todas las migraciones
alembic downgrade base
```

### Crear nueva migración

```bash
# Crear migración vacía (escribir manualmente)
alembic revision -m "descripción del cambio"

# Auto-generar migración desde modelos SQLAlchemy (si los tienes)
alembic revision --autogenerate -m "descripción"
```

## Flujo de Trabajo

### 1. Desarrollo Local

```bash
# 1. Crear nueva migración
alembic revision -m "add_client_id_to_jobs"

# 2. Editar el archivo en alembic/versions/xxx_add_client_id_to_jobs.py
#    Agregar código en upgrade() y downgrade()

# 3. Aplicar la migración
alembic upgrade head

# 4. Verificar que funciona
alembic current
```

### 2. Resetear Base de Datos

Si necesitas empezar desde cero:

```bash
./ops/db/reset.sh
```

Este script:
- Elimina y recrea la base de datos
- Aplica todas las migraciones automáticamente
- Verifica que las tablas se crearon correctamente

### 3. Inicio Local

El script `./scripts/start_local.sh` aplica automáticamente las migraciones si la BD está vacía.

## Ejemplo: Agregar Nueva Columna

### 1. Crear la migración

```bash
alembic revision -m "add_client_id_to_jobs"
```

### 2. Editar el archivo generado

```python
def upgrade() -> None:
    # Agregar columna
    op.add_column('jobs', sa.Column('client_id', sa.String(length=64), nullable=True))
    
    # Agregar índice
    op.create_index('idx_jobs_client_id', 'jobs', ['client_id'])
    
    # Migrar datos existentes (opcional)
    op.execute("UPDATE jobs SET client_id = 'default' WHERE client_id IS NULL")
    
    # Hacer NOT NULL después de migrar datos
    op.alter_column('jobs', 'client_id', nullable=False)

def downgrade() -> None:
    # Revertir en orden inverso
    op.drop_index('idx_jobs_client_id', table_name='jobs')
    op.drop_column('jobs', 'client_id')
```

### 3. Aplicar

```bash
alembic upgrade head
```

## Mejores Prácticas

### ✅ Hacer

- **Siempre probar** `downgrade()` antes de hacer commit
- **Revisar el SQL generado** antes de aplicar en producción
- **Hacer backup** antes de migraciones en producción
- **Usar transacciones** cuando sea posible (MySQL las soporta para DDL)
- **Documentar** cambios importantes en el mensaje de la migración

### ❌ Evitar

- **No modificar** migraciones ya aplicadas en producción
- **No mezclar** cambios de schema con datos en la misma migración
- **No hacer** cambios destructivos sin backup
- **No aplicar** migraciones automáticamente en producción sin revisar

## Migraciones en Producción

### Proceso Recomendado

1. **Backup de la base de datos**
   ```bash
   mysqldump -u user -p database > backup_$(date +%Y%m%d).sql
   ```

2. **Revisar la migración**
   ```bash
   alembic upgrade head --sql  # Ver SQL sin ejecutar
   ```

3. **Aplicar en staging primero**
   ```bash
   alembic upgrade head
   ```

4. **Verificar funcionamiento**

5. **Aplicar en producción** (con aprobación manual)

6. **Verificar estado**
   ```bash
   alembic current
   ```

## Troubleshooting

### Error: "Target database is not up to date"

La BD tiene migraciones aplicadas que no están en el código.

**Solución:**
```bash
# Ver qué versión tiene la BD
alembic current

# Marcar como aplicada (si es seguro)
alembic stamp head
```

### Error: "Can't locate revision identified by 'xxx'"

Falta una migración en el historial.

**Solución:**
- Verificar que todas las migraciones estén en `alembic/versions/`
- Si falta, restaurar desde git o crear una nueva

### Error de conexión

**Solución:**
- Verificar que `.env` tenga las credenciales correctas
- Verificar que el contenedor de BD esté corriendo
- Probar conexión manual: `mysql -u user -p database`

## Migración Inicial

La migración inicial (`075fb1b4ff0e_initial_schema.py`) contiene:
- Todas las tablas del schema base
- Todos los índices
- Foreign keys y constraints

Esta migración es equivalente a ejecutar `ops/db/schema.sql` pero de forma versionada.

## Integración con Scripts

### reset.sh

El script `./ops/db/reset.sh` ahora usa Alembic:
- Elimina y recrea la BD
- Aplica todas las migraciones con `alembic upgrade head`
- Verifica que las tablas se crearon

### start_local.sh

El script `./scripts/start_local.sh`:
- Verifica si la BD tiene datos
- Si está vacía, aplica migraciones automáticamente
- Si tiene datos, asume que ya están aplicadas

## Referencias

- [Documentación oficial de Alembic](https://alembic.sqlalchemy.org/)
- [Tutorial de Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Operaciones disponibles](https://alembic.sqlalchemy.org/en/latest/ops.html)

