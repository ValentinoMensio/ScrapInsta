#!/usr/bin/env python3
"""
Script para inspeccionar el caché de análisis de perfiles.

Uso (desde el directorio raíz del proyecto):
    python scripts/inspect_cache.py                    # Lista todas las claves
    python scripts/inspect_cache.py cristiano          # Ver análisis de un perfil
    python scripts/inspect_cache.py --delete cristiano # Eliminar del caché
    python scripts/inspect_cache.py --stats            # Estadísticas del caché
"""
from __future__ import annotations

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# Agregar el directorio raíz al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scrapinsta.config.settings import Settings
from scrapinsta.infrastructure.redis import RedisClient, CacheService
from scrapinsta.application.dto.cache_serialization import deserialize_analyze_profile_response


def format_size(size_bytes: int) -> str:
    """Formatea bytes a formato legible."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


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
        
        print(f"✅ Datos en caché para: {username}")
        print(f"   Clave: {cache_key}")
        print(f"   Tamaño: {format_size(len(cached))}")
        
        # Intentar deserializar para validar
        try:
            response = deserialize_analyze_profile_response(data)
            print(f"\n📊 Contenido:")
            print(f"   - Snapshot: {'✅' if response.snapshot else '❌'}")
            print(f"   - Recent Reels: {len(response.recent_reels) if response.recent_reels else 0}")
            print(f"   - Recent Posts: {len(response.recent_posts) if response.recent_posts else 0}")
            print(f"   - Basic Stats: {'✅' if response.basic_stats else '❌'}")
            print(f"   - Skipped Recent: {response.skipped_recent}")
            
            if response.snapshot:
                print(f"\n👤 Snapshot:")
                print(f"   - Username: {response.snapshot.username}")
                print(f"   - Followers: {response.snapshot.followers or 'N/A'}")
                print(f"   - Privacy: {response.snapshot.privacy}")
                print(f"   - Verified: {response.snapshot.is_verified}")
            
            if response.basic_stats:
                print(f"\n📈 Basic Stats:")
                print(f"   - Avg Views: {response.basic_stats.avg_views_last_n or 'N/A'}")
                print(f"   - Avg Likes: {response.basic_stats.avg_likes_last_n or 'N/A'}")
                print(f"   - Engagement Score: {response.basic_stats.engagement_score or 'N/A'}")
                print(f"   - Success Score: {response.basic_stats.success_score or 'N/A'}")
        except Exception as e:
            print(f"⚠️  Error al deserializar: {e}")
            print(f"   Datos raw: {json.dumps(data, indent=2)[:500]}...")
    
    except Exception as e:
        print(f"❌ Error al leer caché: {e}")


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
            ttl_str = f"{ttl}s" if ttl > 0 else "sin expiración" if ttl == -1 else "expirado"
            
            # Obtener tamaño
            size = redis_client.memory_usage(key) or 0
            
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
            size = redis_client.memory_usage(key) or 0
            total_size += size
            
            ttl = redis_client.ttl(key)
            if ttl == -2:  # Key doesn't exist (shouldn't happen)
                expired_count += 1
            elif ttl == -1:  # No expiration
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
    parser = argparse.ArgumentParser(description="Inspeccionar caché de análisis de perfiles")
    parser.add_argument("username", nargs="?", help="Username del perfil a inspeccionar")
    parser.add_argument("--delete", action="store_true", help="Eliminar entrada del caché")
    parser.add_argument("--stats", action="store_true", help="Mostrar estadísticas del caché")
    parser.add_argument("--list", action="store_true", help="Listar todas las claves")
    
    args = parser.parse_args()
    
    # Inicializar Redis
    settings = Settings()
    redis_client_wrapper = RedisClient(settings)
    
    if not redis_client_wrapper.enabled:
        print("❌ Redis no está disponible")
        print("   Configura REDIS_URL en las variables de entorno")
        sys.exit(1)
    
    redis_client = redis_client_wrapper.client
    
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

