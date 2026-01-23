"""
Cargador de secretos desde gestores externos hacia Settings.

Separa la responsabilidad de cargar secretos de la clase Settings.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from scrapinsta.crosscutting.secrets import SecretsManager
from scrapinsta.crosscutting.logging_config import get_logger

log = get_logger("secrets_loader")


class SecretsLoader:
    """
    Carga secretos desde un gestor y los aplica a Settings.
    
    Esta clase separa la responsabilidad de cargar secretos de Settings,
    permitiendo que Settings se enfoque solo en gestionar configuración.
    """
    
    def __init__(self, secrets_manager: SecretsManager):
        """
        Args:
            secrets_manager: Gestor de secretos a usar
        """
        self._manager = secrets_manager
        # Mapeo de nombres de secretos a atributos de Settings
        self._secret_mappings: Dict[str, str] = {
            "db_pass": "db_pass",
            "openai_api_key": "openai_api_key",
            "redis_password": "redis_password",
        }
    
    def add_mapping(self, secret_key: str, attr_name: str) -> None:
        """
        Agrega un mapeo de secreto a atributo.
        
        Args:
            secret_key: Nombre del secreto en el gestor
            attr_name: Nombre del atributo en Settings
        """
        self._secret_mappings[secret_key] = attr_name
        log.debug("secret_mapping_added", secret_key=secret_key, attr_name=attr_name)
    
    def load_into_settings(self, settings: Any) -> None:
        """
        Carga secretos desde el gestor y los aplica a settings.
        
        Args:
            settings: Instancia de Settings a actualizar
        """
        loaded_count = 0
        for secret_key, attr_name in self._secret_mappings.items():
            try:
                value = self._manager.get_secret(secret_key)
                if value:
                    # Solo actualizar si el valor actual está vacío o es el default
                    current_value = getattr(settings, attr_name, None)
                    if not current_value or self._should_override(current_value, attr_name):
                        setattr(settings, attr_name, value)
                        loaded_count += 1
                        log.debug(
                            "secret_loaded",
                            secret_key=secret_key,
                            attr_name=attr_name
                        )
            except Exception as e:
                log.warning(
                    "secret_load_failed",
                    secret_key=secret_key,
                    attr_name=attr_name,
                    error=str(e)
                )
        
        if loaded_count > 0:
            log.info("secrets_loaded_into_settings", count=loaded_count)
    
    def _should_override(self, current_value: Any, attr_name: str) -> bool:
        """
        Determina si se debe sobreescribir el valor actual.
        
        Args:
            current_value: Valor actual del atributo
            attr_name: Nombre del atributo
            
        Returns:
            True si se debe sobreescribir
        """
        # Valores por defecto que deben ser sobreescritos
        defaults_to_override = {
            "db_pass": ["app_password", ""],
            "openai_api_key": [None, ""],
            "redis_password": [None, ""],
        }
        
        defaults = defaults_to_override.get(attr_name, [])
        return current_value in defaults

