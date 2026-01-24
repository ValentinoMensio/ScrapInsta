#!/usr/bin/env python3
"""
Script simple para inspeccionar el caché de análisis de perfiles usando Redis directamente.

Requisitos:
    pip install redis

Uso:
    python scripts/inspect_cache_simple.py                    # Lista todas las claves
    python scripts/inspect_cache_simple.py cristiano          # Ver análisis de un perfil
    python scripts/inspect_cache_simple.py --delete cristiano # Eliminar del caché
    python scripts/inspect_cache_simple.py --stats            # Estadísticas del caché
"""
import sys
import json
import argparse
import os
from redis import Redis
from redis.exceptions import ConnectionError


def format_size(size_bytes: int) -> str:
    """Formatea bytes a formato legible."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def get_redis_client():
    """Obtiene cliente Redis desde variables de entorno."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = Redis.from_url(redis_url, decode_responses=False)
        client.ping()
        return client
    except ConnectionError:
        print(f"❌ No se puede conectar a Redis: {redis_url}")
        print("   Configura REDIS_URL o asegúrate de que Redis esté corriendo")
        sys.exit(1)


def inspect_key(redis_client, username: str) -> None:
    """Inspecciona una clave específica del caché."""
    cache_key = f"profile_analysis:{username.lower()}"
    
    try:
        cached = redis_client.get(cache_key)
        if not cached:
            print(f"❌ No hay datos en caché para: {username}")
            print(f"   Clave: {cache_key}")
            return
        
        data = json.loads(cached)
        size = len(cached)
        
        print(f"✅ Datos en caché para: {username}")
        print(f"   Clave: {cache_key}")
        print(f"   Tamaño: {format_size(size)}")
        
        # Obtener TTL
        ttl = redis_client.ttl(cache_key)
        if ttl > 0:
            hours = ttl // 3600
            minutes = (ttl % 3600) // 60
            print(f"   TTL restante: {hours}h {minutes}m ({ttl}s)")
        elif ttl == -1:
            print(f"   TTL: sin expiración")
        else:
            print(f"   TTL: expirado")
        
        print(f"\n📊 Contenido (resumen):")
        print(f"   - Snapshot: {'✅' if data.get('snapshot') else '❌'}")
        print(f"   - Recent Reels: {len(data.get('recent_reels', []))}")
        print(f"   - Recent Posts: {len(data.get('recent_posts', []))}")
        print(f"   - Basic Stats: {'✅' if data.get('basic_stats') else '❌'}")
        print(f"   - Skipped Recent: {data.get('skipped_recent', False)}")
        
        if data.get('snapshot'):
            snap = data['snapshot']
            print(f"\n👤 Snapshot:")
            print(f"   - Username: {snap.get('username', 'N/A')}")
            print(f"   - Followers: {snap.get('followers', 'N/A')}")
            print(f"   - Privacy: {snap.get('privacy', 'N/A')}")
            print(f"   - Verified: {snap.get('is_verified', False)}")
        
        if data.get('basic_stats'):
            stats = data['basic_stats']
            print(f"\n📈 Basic Stats:")
            print(f"   - Avg Views: {stats.get('avg_views_last_n', 'N/A')}")
            print(f"   - Avg Likes: {stats.get('avg_likes_last_n', 'N/A')}")
            print(f"   - Engagement Score: {stats.get('engagement_score', 'N/A')}")
            print(f"   - Success Score: {stats.get('success_score', 'N/A')}")
        
        print(f"\n💾 Datos completos (JSON):")
        print(json.dumps(data, indent=2, default=str)[:1000])
        if len(json.dumps(data, default=str)) > 1000:
            print("   ... (truncado)")
    
    except json.JSONDecodeError as e:
        print(f"❌ Error al decodificar JSON: {e}")
        print(f"   Datos raw (primeros 500 chars): {cached[:500]}")
    except Exception as e:
        print(f"❌ Error: {e}")


def list_keys(redis_client, pattern: str = "profile_analysis:*") -> None:
    """Lista todas las claves del caché."""
    try:
        keys = redis_client.keys(pattern)
        if not keys:
            print("📭 No hay entradas en el caché")
            return
        
        print(f"📋 Encontradas {len(keys)} entradas en el caché:\n")
        
        for key in sorted(keys):
            key_str = key.decode() if isinstance(key, bytes) else key
            username = key_str.replace("profile_analysis:", "")
            
            # Obtener TTL
            ttl = redis_client.ttl(key)
            if ttl > 0:
                hours = ttl // 3600
                minutes = (ttl % 3600) // 60
                ttl_str = f"{hours}h {minutes}m"
            elif ttl == -1:
                ttl_str = "sin expiración"
            else:
                ttl_str = "expirado"
            
            # Obtener tamaño
            try:
                size = redis_client.memory_usage(key) or 0
            except:
                size = len(redis_client.get(key) or b"")
            
            print(f"  • {username:30} | TTL: {ttl_str:15} | Tamaño: {format_size(size)}")
    
    except Exception as e:
        print(f"❌ Error al listar claves: {e}")


def get_stats(redis_client) -> None:
    """Muestra estadísticas del caché."""
    try:
        keys = redis_client.keys("profile_analysis:*")
        total_keys = len(keys)
        
        if total_keys == 0:
            print("📭 No hay entradas en el caché")
            return
        
        total_size = 0
        expired_count = 0
        valid_count = 0
        
        for key in keys:
            try:
                size = redis_client.memory_usage(key) or 0
            except:
                size = len(redis_client.get(key) or b"")
            total_size += size
            
            ttl = redis_client.ttl(key)
            if ttl == -2:
                expired_count += 1
            elif ttl == -1:
                valid_count += 1
            elif ttl > 0:
                valid_count += 1
            else:
                expired_count += 1
        
        print("📊 Estadísticas del Caché:")
        print(f"   Total de entradas: {total_keys}")
        print(f"   Entradas válidas: {valid_count}")
        print(f"   Entradas expiradas: {expired_count}")
        print(f"   Tamaño total: {format_size(total_size)}")
        print(f"   Tamaño promedio: {format_size(total_size / total_keys) if total_keys > 0 else 0}")
    
    except Exception as e:
        print(f"❌ Error al obtener estadísticas: {e}")


def delete_key(redis_client, username: str) -> None:
    """Elimina una entrada del caché."""
    cache_key = f"profile_analysis:{username.lower()}"
    
    try:
        deleted = redis_client.delete(cache_key)
        if deleted:
            print(f"✅ Eliminado del caché: {username}")
            print(f"   Clave: {cache_key}")
        else:
            print(f"❌ No se encontró en el caché: {username}")
            print(f"   Clave: {cache_key}")
    except Exception as e:
        print(f"❌ Error al eliminar: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Inspeccionar caché de análisis de perfiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/inspect_cache_simple.py                    # Lista todas las claves
  python scripts/inspect_cache_simple.py cristiano              # Ver análisis de un perfil
  python scripts/inspect_cache_simple.py --delete cristiano     # Eliminar del caché
  python scripts/inspect_cache_simple.py --stats                 # Estadísticas del caché
        """
    )
    parser.add_argument("username", nargs="?", help="Username del perfil a inspeccionar")
    parser.add_argument("--delete", action="store_true", help="Eliminar entrada del caché")
    parser.add_argument("--stats", action="store_true", help="Mostrar estadísticas del caché")
    parser.add_argument("--list", action="store_true", help="Listar todas las claves")
    
    args = parser.parse_args()
    
    # Conectar a Redis
    redis_client = get_redis_client()
    
    # Ejecutar acción
    if args.stats:
        get_stats(redis_client)
    elif args.list:
        list_keys(redis_client)
    elif args.username:
        if args.delete:
            delete_key(redis_client, args.username)
        else:
            inspect_key(redis_client, args.username)
    else:
        # Por defecto, listar todas las claves
        list_keys(redis_client)


if __name__ == "__main__":
    main()

