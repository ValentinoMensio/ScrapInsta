"""
Servicio de caché usando Redis para perfiles y análisis.
"""
from __future__ import annotations

import json
import time
from typing import Optional, Any, Dict
from redis import Redis
from redis.exceptions import RedisError

from scrapinsta.config.settings import Settings
from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.metrics import (
    cache_operations_total,
    cache_hit_rate,
    redis_operations_total,
    redis_operation_duration_seconds,
)

logger = get_logger(__name__)


class CacheService:
    """
    Servicio de caché para perfiles analizados y resultados.
    Usa Redis con TTL configurables.
    """
    
    def __init__(self, redis_client: Optional[Redis], settings: Settings) -> None:
        """
        Inicializa el servicio de caché.
        
        Args:
            redis_client: Cliente Redis (puede ser None para deshabilitar caché)
            settings: Configuración de la aplicación
        """
        self.redis = redis_client
        self.settings = settings
        self.enabled = redis_client is not None
        
        if self.enabled:
            try:
                redis_client.ping()
                logger.info("cache_service_initialized", enabled=True)
            except Exception as e:
                logger.warning("redis_cache_init_failed", error=str(e))
                self.enabled = False
                self.redis = None
        else:
            logger.info("cache_service_initialized", enabled=False, mode="no_cache")
    
    def get_profile_analysis(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el análisis de un perfil desde caché.
        
        Args:
            username: Username del perfil (normalizado a lowercase)
            
        Returns:
            Diccionario con el análisis o None si no está en caché
        """
        if not self.enabled or not self.redis:
            cache_operations_total.labels(operation="get_profile_analysis", result="disabled").inc()
            return None
        
        cache_key = f"profile_analysis:{username.lower()}"
        start_time = time.time()
        
        try:
            cached = self.redis.get(cache_key)
            duration = time.time() - start_time
            redis_operations_total.labels(operation="get", status="success").inc()
            redis_operation_duration_seconds.labels(operation="get").observe(duration)
            
            if cached:
                data = json.loads(cached)
                logger.debug("cache_hit", key=cache_key, username=username)
                cache_operations_total.labels(operation="get_profile_analysis", result="hit").inc()
                cache_hit_rate.labels(operation_type="profile_analysis").observe(1.0)
                return data
            logger.debug("cache_miss", key=cache_key, username=username)
            cache_operations_total.labels(operation="get_profile_analysis", result="miss").inc()
            cache_hit_rate.labels(operation_type="profile_analysis").observe(0.0)
            return None
        except RedisError as e:
            duration = time.time() - start_time
            redis_operations_total.labels(operation="get", status="error").inc()
            redis_operation_duration_seconds.labels(operation="get").observe(duration)
            logger.warning("cache_get_error", key=cache_key, error=str(e))
            cache_operations_total.labels(operation="get_profile_analysis", result="error").inc()
            return None
        except json.JSONDecodeError as e:
            logger.warning("cache_decode_error", key=cache_key, error=str(e))
            cache_operations_total.labels(operation="get_profile_analysis", result="decode_error").inc()
            # Limpiar entrada corrupta
            try:
                self.redis.delete(cache_key)
            except Exception:
                pass
            return None
    
    def set_profile_analysis(
        self,
        username: str,
        analysis_data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Guarda el análisis de un perfil en caché.
        
        Args:
            username: Username del perfil (normalizado a lowercase)
            analysis_data: Datos del análisis a cachear
            ttl: TTL en segundos (usa settings por defecto)
            
        Returns:
            True si se guardó exitosamente, False en caso contrario
        """
        if not self.enabled or not self.redis:
            return False
        
        cache_key = f"profile_analysis:{username.lower()}"
        ttl = ttl or self.settings.redis_cache_profile_ttl
        start_time = time.time()
        
        try:
            serialized = json.dumps(analysis_data, default=str)
            self.redis.setex(cache_key, ttl, serialized)
            duration = time.time() - start_time
            redis_operations_total.labels(operation="setex", status="success").inc()
            redis_operation_duration_seconds.labels(operation="setex").observe(duration)
            logger.debug("cache_set", key=cache_key, username=username, ttl=ttl)
            cache_operations_total.labels(operation="set_profile_analysis", result="success").inc()
            return True
        except RedisError as e:
            duration = time.time() - start_time
            redis_operations_total.labels(operation="setex", status="error").inc()
            redis_operation_duration_seconds.labels(operation="setex").observe(duration)
            logger.warning("cache_set_error", key=cache_key, error=str(e))
            cache_operations_total.labels(operation="set_profile_analysis", result="error").inc()
            return False
        except (TypeError, ValueError) as e:
            logger.error("cache_serialize_error", key=cache_key, error=str(e))
            cache_operations_total.labels(operation="set_profile_analysis", result="serialize_error").inc()
            return False
    
    def invalidate_profile(self, username: str) -> bool:
        """
        Invalida el caché de un perfil.
        
        Args:
            username: Username del perfil
            
        Returns:
            True si se invalidó exitosamente, False en caso contrario
        """
        if not self.enabled or not self.redis:
            return False
        
        cache_key = f"profile_analysis:{username.lower()}"
        
        try:
            deleted = self.redis.delete(cache_key)
            logger.debug("cache_invalidated", key=cache_key, deleted=bool(deleted))
            return bool(deleted)
        except RedisError as e:
            logger.warning("cache_invalidate_error", key=cache_key, error=str(e))
            return False
    
    def get_profile_snapshot(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el snapshot de un perfil desde caché.
        
        Args:
            username: Username del perfil
            
        Returns:
            Diccionario con el snapshot o None si no está en caché
        """
        if not self.enabled or not self.redis:
            return None
        
        cache_key = f"profile_snapshot:{username.lower()}"
        
        try:
            cached = self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                logger.debug("cache_hit", key=cache_key, username=username)
                return data
            return None
        except Exception as e:
            logger.debug("cache_get_snapshot_error", key=cache_key, error=str(e))
            return None
    
    def set_profile_snapshot(
        self,
        username: str,
        snapshot_data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Guarda el snapshot de un perfil en caché.
        
        Args:
            username: Username del perfil
            snapshot_data: Datos del snapshot a cachear
            ttl: TTL en segundos (usa settings por defecto)
            
        Returns:
            True si se guardó exitosamente
        """
        if not self.enabled or not self.redis:
            return False
        
        cache_key = f"profile_snapshot:{username.lower()}"
        ttl = ttl or self.settings.redis_cache_profile_ttl
        
        try:
            serialized = json.dumps(snapshot_data, default=str)
            self.redis.setex(cache_key, ttl, serialized)
            logger.debug("cache_set_snapshot", key=cache_key, username=username, ttl=ttl)
            return True
        except Exception as e:
            logger.debug("cache_set_snapshot_error", key=cache_key, error=str(e))
            return False
    
    def get(
        self,
        key: str,
        prefix: str = "cache",
    ) -> Optional[Any]:
        """
        Obtiene un valor genérico del caché.
        
        Args:
            key: Clave del caché
            prefix: Prefijo para la clave (default: "cache")
            
        Returns:
            Valor deserializado o None
        """
        if not self.enabled or not self.redis:
            return None
        
        cache_key = f"{prefix}:{key}"
        
        try:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.debug("cache_get_generic_error", key=cache_key, error=str(e))
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: int,
        prefix: str = "cache",
    ) -> bool:
        """
        Guarda un valor genérico en el caché.
        
        Args:
            key: Clave del caché
            value: Valor a cachear
            ttl: TTL en segundos
            prefix: Prefijo para la clave (default: "cache")
            
        Returns:
            True si se guardó exitosamente
        """
        if not self.enabled or not self.redis:
            return False
        
        cache_key = f"{prefix}:{key}"
        
        try:
            serialized = json.dumps(value, default=str)
            self.redis.setex(cache_key, ttl, serialized)
            return True
        except Exception as e:
            logger.debug("cache_set_generic_error", key=cache_key, error=str(e))
            return False
    
    def delete(self, key: str, prefix: str = "cache") -> bool:
        """
        Elimina una clave del caché.
        
        Args:
            key: Clave del caché
            prefix: Prefijo para la clave
            
        Returns:
            True si se eliminó exitosamente
        """
        if not self.enabled or not self.redis:
            return False
        
        cache_key = f"{prefix}:{key}"
        
        try:
            return bool(self.redis.delete(cache_key))
        except Exception as e:
            logger.debug("cache_delete_error", key=cache_key, error=str(e))
            return False

