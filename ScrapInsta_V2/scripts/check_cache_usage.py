#!/usr/bin/env python3
"""
Script para verificar el uso de la caché de análisis de perfiles.

Muestra:
- Estadísticas de Redis (entradas, tamaño)
- Métricas Prometheus (hits, misses, tasa de aciertos)
- Logs recientes de cache hits/misses
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

try:
    import redis
    import requests
except ImportError:
    print("❌ Faltan dependencias. Instala con:")
    print("   pip install redis requests")
    sys.exit(1)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
API_URL = os.getenv("API_URL", "http://localhost:8000")
CACHE_PREFIX = "profile_analysis:"


def get_redis_client() -> Optional[redis.Redis]:
    """Conecta a Redis."""
    try:
        client = redis.from_url(REDIS_URL)
        client.ping()
        return client
    except redis.exceptions.ConnectionError as e:
        print(f"❌ No se puede conectar a Redis: {REDIS_URL}")
        print(f"   Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error al conectar a Redis: {e}")
        return None


def get_prometheus_metrics() -> Optional[Dict[str, Any]]:
    """Obtiene métricas de Prometheus desde la API."""
    try:
        response = requests.get(f"{API_URL}/metrics", timeout=5)
        if response.status_code != 200:
            return None
        
        metrics_text = response.text
        metrics = {}
        
        # Parsear métricas de caché
        for line in metrics_text.split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            
            # cache_operations_total{operation="get_profile_analysis", result="hit"} 42.0
            if "cache_operations_total" in line:
                parts = line.split()
                if len(parts) >= 2:
                    metric_name = parts[0].split("{")[0]
                    value = float(parts[-1])
                    
                    # Extraer labels
                    if "{" in parts[0] and "}" in parts[0]:
                        labels_str = parts[0].split("{")[1].split("}")[0]
                        labels = {}
                        for label_pair in labels_str.split(","):
                            if "=" in label_pair:
                                key, val = label_pair.split("=", 1)
                                labels[key.strip()] = val.strip().strip('"')
                        
                        key = f"{metric_name}_{labels.get('operation', '')}_{labels.get('result', '')}"
                        metrics[key] = value
            
            # cache_hit_rate{operation_type="profile_analysis"} 0.75
            elif "cache_hit_rate" in line and not line.startswith("#"):
                parts = line.split()
                if len(parts) >= 2:
                    value = float(parts[-1])
                    metrics["cache_hit_rate"] = value
        
        return metrics
    except requests.exceptions.RequestException as e:
        return None
    except Exception as e:
        return None


def get_redis_stats(r: redis.Redis) -> Dict[str, Any]:
    """Obtiene estadísticas de Redis."""
    stats = {
        "total_keys": 0,
        "valid_keys": 0,
        "expired_keys": 0,
        "total_size": 0,
        "avg_size": 0,
        "keys": [],
    }
    
    try:
        pattern = f"{CACHE_PREFIX}*"
        keys = list(r.scan_iter(match=pattern, count=100))
        stats["total_keys"] = len(keys)
        
        total_size = 0
        valid_count = 0
        
        for key in keys:
            try:
                ttl = r.ttl(key)
                size = r.memory_usage(key) or 0
                total_size += size
                
                if ttl > 0:
                    valid_count += 1
                    username = key.decode().replace(CACHE_PREFIX, "")
                    stats["keys"].append({
                        "username": username,
                        "ttl": ttl,
                        "size": size,
                    })
                else:
                    stats["expired_keys"] += 1
            except Exception:
                pass
        
        stats["valid_keys"] = valid_count
        stats["total_size"] = total_size
        stats["avg_size"] = total_size / valid_count if valid_count > 0 else 0
        
    except Exception as e:
        print(f"⚠️  Error al obtener estadísticas de Redis: {e}")
    
    return stats


def format_size(size_bytes: float) -> str:
    """Formatea bytes a formato legible."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def format_ttl(seconds: int) -> str:
    """Formatea TTL a formato legible."""
    if seconds < 0:
        return "expirado"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def print_redis_stats(stats: Dict[str, Any]):
    """Imprime estadísticas de Redis."""
    print("\n" + "=" * 60)
    print("📦 ESTADÍSTICAS DE REDIS")
    print("=" * 60)
    print(f"   Total de entradas: {stats['total_keys']}")
    print(f"   Entradas válidas: {stats['valid_keys']}")
    print(f"   Entradas expiradas: {stats['expired_keys']}")
    print(f"   Tamaño total: {format_size(stats['total_size'])}")
    if stats['valid_keys'] > 0:
        print(f"   Tamaño promedio: {format_size(stats['avg_size'])}")
    
    if stats['keys']:
        print(f"\n   Top 10 entradas más grandes:")
        sorted_keys = sorted(stats['keys'], key=lambda x: x['size'], reverse=True)[:10]
        for i, key_info in enumerate(sorted_keys, 1):
            print(f"   {i:2d}. {key_info['username']:30s} | "
                  f"TTL: {format_ttl(key_info['ttl']):10s} | "
                  f"Tamaño: {format_size(key_info['size'])}")


def print_prometheus_metrics(metrics: Dict[str, Any]):
    """Imprime métricas de Prometheus."""
    print("\n" + "=" * 60)
    print("📊 MÉTRICAS DE USO (Prometheus)")
    print("=" * 60)
    
    if not metrics:
        print("   ⚠️  No se pudieron obtener métricas de la API")
        print(f"   Verifica que la API esté corriendo en {API_URL}")
        return
    
    hits = metrics.get("cache_operations_total_get_profile_analysis_hit", 0)
    misses = metrics.get("cache_operations_total_get_profile_analysis_miss", 0)
    errors = metrics.get("cache_operations_total_get_profile_analysis_error", 0)
    disabled = metrics.get("cache_operations_total_get_profile_analysis_disabled", 0)
    
    total_ops = hits + misses + errors
    hit_rate = (hits / total_ops * 100) if total_ops > 0 else 0
    
    print(f"   Cache Hits:     {hits:>10}")
    print(f"   Cache Misses:  {misses:>10}")
    print(f"   Errores:        {errors:>10}")
    print(f"   Deshabilitado: {disabled:>10}")
    print(f"   Total:          {total_ops:>10}")
    
    if total_ops > 0:
        print(f"\n   📈 Tasa de Aciertos: {hit_rate:.1f}%")
        
        if hit_rate >= 70:
            print("   ✅ Excelente: La caché está funcionando muy bien")
        elif hit_rate >= 50:
            print("   ✅ Bueno: La caché está siendo útil")
        elif hit_rate >= 30:
            print("   ⚠️  Regular: La caché podría mejorar con más uso")
        else:
            print("   ⚠️  Bajo: La caché no se está usando mucho")
    
    hit_rate_metric = metrics.get("cache_hit_rate")
    if hit_rate_metric is not None:
        print(f"\n   Tasa de aciertos (métrica): {hit_rate_metric * 100:.1f}%")


def print_logs_tips():
    """Imprime tips para ver logs."""
    print("\n" + "=" * 60)
    print("📝 VER LOGS EN TIEMPO REAL")
    print("=" * 60)
    print("   Para ver cache hits en los logs del dispatcher:")
    print("   $ tail -f dispatcher.log | grep cache_hit")
    print()
    print("   Para ver cache misses:")
    print("   $ tail -f dispatcher.log | grep cache_miss")
    print()
    print("   Para ver todos los eventos de caché:")
    print("   $ tail -f dispatcher.log | grep -E 'cache_(hit|miss|saved)'")


def main():
    parser = argparse.ArgumentParser(
        description="Verificar uso de la caché de análisis de perfiles",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--redis-only",
        action="store_true",
        help="Solo mostrar estadísticas de Redis (sin métricas Prometheus)",
    )
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="Solo mostrar métricas Prometheus (sin estadísticas de Redis)",
    )
    parser.add_argument(
        "--api-url",
        default=API_URL,
        help=f"URL de la API (default: {API_URL})",
    )
    
    args = parser.parse_args()
    
    print("🔍 Verificando uso de la caché...")
    print(f"   Redis: {REDIS_URL}")
    if not args.redis_only:
        print(f"   API: {args.api_url}")
    
    # Estadísticas de Redis
    if not args.metrics_only:
        r = get_redis_client()
        if r:
            stats = get_redis_stats(r)
            print_redis_stats(stats)
        else:
            print("\n⚠️  No se pudo conectar a Redis")
    
    # Métricas de Prometheus
    if not args.redis_only:
        metrics = get_prometheus_metrics()
        print_prometheus_metrics(metrics)
    
    # Tips para logs
    if not args.redis_only and not args.metrics_only:
        print_logs_tips()
    
    print("\n" + "=" * 60)
    print("✅ Verificación completada")
    print("=" * 60)


if __name__ == "__main__":
    main()

