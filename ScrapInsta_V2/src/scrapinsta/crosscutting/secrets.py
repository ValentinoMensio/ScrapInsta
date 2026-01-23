"""
Gestión centralizada de secretos con soporte para múltiples proveedores.

Proveedores soportados:
- ENV: Variables de entorno (desarrollo)
- AWS: AWS Secrets Manager / Parameter Store
- VAULT: HashiCorp Vault
- AZURE: Azure Key Vault

El sistema permite:
- Carga dinámica de secretos desde diferentes fuentes
- Separación por ambiente (dev/staging/prod)
- Fallback automático a variables de entorno
- Cifrado de valores sensibles
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from enum import Enum

from scrapinsta.crosscutting.logging_config import get_logger

log = get_logger("secrets")


class SecretProvider(str, Enum):
    """Proveedores de secretos disponibles."""
    ENV = "env"
    AWS = "aws"
    VAULT = "vault"
    AZURE = "azure"


class SecretsManager(ABC):
    """Interfaz base para gestores de secretos."""
    
    @abstractmethod
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Obtiene un secreto por clave.
        
        Args:
            key: Nombre del secreto
            default: Valor por defecto si no se encuentra
            
        Returns:
            Valor del secreto o None
        """
        pass
    
    @abstractmethod
    def get_secrets(self, prefix: str) -> Dict[str, str]:
        """
        Obtiene múltiples secretos con un prefijo común.
        
        Args:
            prefix: Prefijo para filtrar secretos
            
        Returns:
            Diccionario con los secretos encontrados
        """
        pass
    
    @property
    @abstractmethod
    def is_external_provider(self) -> bool:
        """
        Indica si es un proveedor externo (no ENV).
        
        Returns:
            True si es un proveedor externo (AWS, Vault, Azure), False si es ENV
        """
        pass


class EnvSecretsManager(SecretsManager):
    """Gestor de secretos usando variables de entorno (desarrollo/local)."""
    
    def __init__(self, env_prefix: str = ""):
        """
        Args:
            env_prefix: Prefijo opcional para variables de entorno (ej: "SCRAPINSTA_")
        """
        self.env_prefix = env_prefix
        log.info("secrets_manager_initialized", provider="ENV", prefix=env_prefix)
    
    @property
    def is_external_provider(self) -> bool:
        return False
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        env_key = f"{self.env_prefix}{key}" if self.env_prefix else key
        value = os.getenv(env_key, default)
        if value is None:
            log.debug("secret_not_found", key=env_key)
        return value
    
    def get_secrets(self, prefix: str) -> Dict[str, str]:
        full_prefix = f"{self.env_prefix}{prefix}" if self.env_prefix else prefix
        result = {}
        for key, value in os.environ.items():
            if key.startswith(full_prefix):
                # Remover el prefijo del nombre de la clave
                clean_key = key[len(full_prefix):].lstrip("_")
                result[clean_key] = value
        return result


class AWSSecretsManager(SecretsManager):
    """Gestor de secretos usando AWS Secrets Manager / Parameter Store."""
    
    def __init__(
        self,
        region: Optional[str] = None,
        use_parameter_store: bool = False,
        prefix: str = "/scrapinsta/"
    ):
        """
        Args:
            region: Región de AWS (default: usar AWS_DEFAULT_REGION o us-east-1)
            use_parameter_store: Si True usa Parameter Store, si False usa Secrets Manager
            prefix: Prefijo para rutas de secretos
        """
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 no está instalado. Instálalo con: pip install boto3"
            )
        
        self.region = region or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.use_parameter_store = use_parameter_store
        self.prefix = prefix
        
        if use_parameter_store:
            self._client = boto3.client("ssm", region_name=self.region)
        else:
            self._client = boto3.client("secretsmanager", region_name=self.region)
        
        log.info(
            "secrets_manager_initialized",
            provider="AWS",
            service="Parameter Store" if use_parameter_store else "Secrets Manager",
            region=self.region,
            prefix=prefix
        )
    
    @property
    def is_external_provider(self) -> bool:
        return True
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            if self.use_parameter_store:
                # AWS Parameter Store
                parameter_name = f"{self.prefix}{key}"
                response = self._client.get_parameter(
                    Name=parameter_name,
                    WithDecryption=True
                )
                return response["Parameter"]["Value"]
            else:
                # AWS Secrets Manager
                secret_name = f"{self.prefix}{key}"
                response = self._client.get_secret_value(SecretId=secret_name)
                return response["SecretString"]
        except self._client.exceptions.ResourceNotFoundException:
            log.debug("secret_not_found", key=key, provider="AWS")
            return default
        except Exception as e:
            log.error("secret_fetch_error", key=key, provider="AWS", error=str(e))
            return default
    
    def get_secrets(self, prefix: str) -> Dict[str, str]:
        result = {}
        full_prefix = f"{self.prefix}{prefix}"
        
        try:
            if self.use_parameter_store:
                # AWS Parameter Store - obtener parámetros por prefijo
                paginator = self._client.get_paginator("describe_parameters")
                for page in paginator.paginate(
                    ParameterFilters=[
                        {"Key": "Name", "Values": [f"{full_prefix}*"]}
                    ]
                ):
                    for param in page["Parameters"]:
                        param_name = param["Name"]
                        clean_key = param_name[len(full_prefix):]
                        value = self.get_secret(clean_key)
                        if value:
                            result[clean_key] = value
            else:
                # AWS Secrets Manager - listar secretos por prefijo
                paginator = self._client.get_paginator("list_secrets")
                for page in paginator.paginate(Filters=[{"Key": "name", "Values": [f"{full_prefix}*"]}]):
                    for secret in page["SecretList"]:
                        secret_name = secret["Name"]
                        clean_key = secret_name[len(full_prefix):]
                        value = self.get_secret(clean_key)
                        if value:
                            result[clean_key] = value
        except Exception as e:
            log.error("secrets_list_error", prefix=prefix, provider="AWS", error=str(e))
        
        return result


class VaultSecretsManager(SecretsManager):
    """Gestor de secretos usando HashiCorp Vault."""
    
    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        mount_point: str = "secret",
        prefix: str = "scrapinsta/"
    ):
        """
        Args:
            url: URL de Vault (default: VAULT_ADDR env var)
            token: Token de autenticación (default: VAULT_TOKEN env var)
            mount_point: Mount point del secret engine
            prefix: Prefijo para rutas de secretos
        """
        try:
            import hvac
        except ImportError:
            raise ImportError(
                "hvac no está instalado. Instálalo con: pip install hvac"
            )
        
        self.url = url or os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
        self.token = token or os.getenv("VAULT_TOKEN")
        self.mount_point = mount_point
        self.prefix = prefix
        
        self._client = hvac.Client(url=self.url, token=self.token)
        
        if not self._client.is_authenticated():
            raise ValueError("Vault no está autenticado. Verifica VAULT_TOKEN.")
        
        log.info(
            "secrets_manager_initialized",
            provider="VAULT",
            url=self.url,
            mount_point=mount_point,
            prefix=prefix
        )
    
    @property
    def is_external_provider(self) -> bool:
        return True
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            path = f"{self.prefix}{key}"
            response = self._client.secrets.kv.v2.read_secret_version(path=path, mount_point=self.mount_point)
            data = response.get("data", {}).get("data", {})
            # Si el secreto es un string simple, devolverlo directamente
            # Si es un dict, devolver el valor asociado a la clave
            if isinstance(data, str):
                return data
            elif isinstance(data, dict) and len(data) == 1:
                return list(data.values())[0]
            return data.get("value") or default
        except Exception as e:
            log.debug("secret_not_found", key=key, provider="VAULT", error=str(e))
            return default
    
    def get_secrets(self, prefix: str) -> Dict[str, str]:
        result = {}
        full_prefix = f"{self.prefix}{prefix}"
        
        try:
            # Listar secretos bajo el prefijo
            list_response = self._client.secrets.kv.v2.list_secrets(
                path=full_prefix.rstrip("/"),
                mount_point=self.mount_point
            )
            
            keys = list_response.get("data", {}).get("keys", [])
            for key in keys:
                value = self.get_secret(key)
                if value:
                    result[key] = value
        except Exception as e:
            log.error("secrets_list_error", prefix=prefix, provider="VAULT", error=str(e))
        
        return result


class AzureSecretsManager(SecretsManager):
    """Gestor de secretos usando Azure Key Vault."""
    
    def __init__(
        self,
        vault_url: Optional[str] = None,
        credential: Optional[Any] = None
    ):
        """
        Args:
            vault_url: URL del Key Vault (default: AZURE_VAULT_URL env var)
            credential: Credencial de Azure (default: DefaultAzureCredential)
        """
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
        except ImportError:
            raise ImportError(
                "azure-keyvault-secrets y azure-identity no están instalados. "
                "Instálalos con: pip install azure-keyvault-secrets azure-identity"
            )
        
        self.vault_url = vault_url or os.getenv("AZURE_VAULT_URL")
        if not self.vault_url:
            raise ValueError("AZURE_VAULT_URL debe estar configurado")
        
        if credential is None:
            credential = DefaultAzureCredential()
        
        self._client = SecretClient(vault_url=self.vault_url, credential=credential)
        
        log.info(
            "secrets_manager_initialized",
            provider="AZURE",
            vault_url=self.vault_url
        )
    
    @property
    def is_external_provider(self) -> bool:
        return True
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            secret = self._client.get_secret(key)
            return secret.value
        except Exception as e:
            log.debug("secret_not_found", key=key, provider="AZURE", error=str(e))
            return default
    
    def get_secrets(self, prefix: str) -> Dict[str, str]:
        result = {}
        try:
            secrets = self._client.list_properties_of_secrets()
            for secret_props in secrets:
                if secret_props.name.startswith(prefix):
                    clean_key = secret_props.name[len(prefix):]
                    value = self.get_secret(secret_props.name)
                    if value:
                        result[clean_key] = value
        except Exception as e:
            log.error("secrets_list_error", prefix=prefix, provider="AZURE", error=str(e))
        
        return result


class SecretsManagerRegistry:
    """Registry para proveedores de secretos usando el patrón Registry."""
    
    _providers: Dict[SecretProvider, Callable[..., SecretsManager]] = {}
    
    @classmethod
    def register(
        cls,
        provider: SecretProvider,
        factory: Callable[..., SecretsManager]
    ) -> None:
        """
        Registra un proveedor de secretos.
        
        Args:
            provider: Tipo de proveedor
            factory: Función factory que crea el gestor
        """
        cls._providers[provider] = factory
        log.debug("secrets_provider_registered", provider=provider.value)
    
    @classmethod
    def create(
        cls,
        provider: SecretProvider,
        **kwargs
    ) -> SecretsManager:
        """
        Crea un gestor usando el proveedor registrado.
        
        Args:
            provider: Tipo de proveedor
            **kwargs: Argumentos para el factory
            
        Returns:
            Instancia del gestor de secretos
            
        Raises:
            ValueError: Si el proveedor no está registrado
        """
        factory = cls._providers.get(provider)
        if not factory:
            raise ValueError(f"Proveedor no registrado: {provider}")
        return factory(**kwargs)
    
    @classmethod
    def is_registered(cls, provider: SecretProvider) -> bool:
        """Verifica si un proveedor está registrado."""
        return provider in cls._providers


def _create_env_manager(environment: Optional[str] = None, **kwargs) -> EnvSecretsManager:
    """Factory para EnvSecretsManager."""
    env_prefix = kwargs.get("env_prefix", os.getenv("SECRETS_ENV_PREFIX", ""))
    return EnvSecretsManager(env_prefix=env_prefix)


def _create_aws_manager(environment: Optional[str] = None, **kwargs) -> AWSSecretsManager:
    """Factory para AWSSecretsManager."""
    region = kwargs.get("region") or os.getenv("AWS_REGION")
    use_parameter_store = kwargs.get(
        "use_parameter_store",
        os.getenv("AWS_USE_PARAMETER_STORE", "false").lower() == "true"
    )
    prefix = kwargs.get("prefix") or f"/scrapinsta/{environment or 'local'}/"
    return AWSSecretsManager(
        region=region,
        use_parameter_store=use_parameter_store,
        prefix=prefix
    )


def _create_vault_manager(environment: Optional[str] = None, **kwargs) -> VaultSecretsManager:
    """Factory para VaultSecretsManager."""
    url = kwargs.get("url") or os.getenv("VAULT_ADDR")
    token = kwargs.get("token") or os.getenv("VAULT_TOKEN")
    mount_point = kwargs.get("mount_point", "secret")
    prefix = kwargs.get("prefix") or f"scrapinsta/{environment or 'local'}/"
    return VaultSecretsManager(
        url=url,
        token=token,
        mount_point=mount_point,
        prefix=prefix
    )


def _create_azure_manager(environment: Optional[str] = None, **kwargs) -> AzureSecretsManager:
    """Factory para AzureSecretsManager."""
    vault_url = kwargs.get("vault_url") or os.getenv("AZURE_VAULT_URL")
    return AzureSecretsManager(vault_url=vault_url)


# Registrar proveedores por defecto
SecretsManagerRegistry.register(SecretProvider.ENV, _create_env_manager)
SecretsManagerRegistry.register(SecretProvider.AWS, _create_aws_manager)
SecretsManagerRegistry.register(SecretProvider.VAULT, _create_vault_manager)
SecretsManagerRegistry.register(SecretProvider.AZURE, _create_azure_manager)


def create_secrets_manager(
    provider: Optional[str] = None,
    environment: Optional[str] = None,
    **kwargs
) -> SecretsManager:
    """
    Factory para crear un gestor de secretos según configuración.
    
    Args:
        provider: Proveedor a usar (env/aws/vault/azure). Si None, se usa SECRETS_PROVIDER env var
        environment: Ambiente (dev/staging/prod). Se agrega como prefijo en las rutas
        **kwargs: Argumentos adicionales para el proveedor específico
    
    Returns:
        Instancia del gestor de secretos
    """
    # Determinar proveedor
    if provider is None:
        provider = os.getenv("SECRETS_PROVIDER", "env").lower()
    
    # Determinar ambiente
    if environment is None:
        environment = os.getenv("ENV", "local").lower()
    
    # Normalizar provider
    try:
        provider_enum = SecretProvider(provider.lower())
    except ValueError:
        log.warning(
            "unknown_secrets_provider",
            provider=provider,
            fallback="ENV"
        )
        provider_enum = SecretProvider.ENV
    
    # Crear usando registry
    try:
        return SecretsManagerRegistry.create(
            provider_enum,
            environment=environment,
            **kwargs
        )
    except ValueError:
        # Fallback a ENV si el proveedor no está registrado
        log.warning("provider_not_registered_fallback", provider=provider_enum.value)
        return EnvSecretsManager()


class SecretsManagerFactory:
    """
    Factory para crear y gestionar instancias de SecretsManager.
    Permite dependency injection mientras mantiene compatibilidad con singleton.
    """
    
    def __init__(self, provider: Optional[str] = None, **kwargs):
        """
        Args:
            provider: Proveedor a usar (env/aws/vault/azure)
            **kwargs: Argumentos adicionales para el proveedor
        """
        self._provider = provider
        self._kwargs = kwargs
        self._instance: Optional[SecretsManager] = None
    
    def get_manager(self) -> SecretsManager:
        """
        Obtiene el gestor de secretos (lazy initialization).
        
        Returns:
            Instancia del gestor de secretos
        """
        if self._instance is None:
            self._instance = create_secrets_manager(
                provider=self._provider,
                **self._kwargs
            )
        return self._instance
    
    def reset(self) -> None:
        """
        Resetea la instancia (útil para testing).
        """
        self._instance = None
    
    def set_manager(self, manager: SecretsManager) -> None:
        """
        Establece un gestor específico (útil para testing con mocks).
        
        Args:
            manager: Instancia del gestor a usar
        """
        self._instance = manager


# Factory por defecto (singleton para compatibilidad)
_default_factory = SecretsManagerFactory()


def get_secrets_manager() -> SecretsManager:
    """
    Obtiene el gestor de secretos global (singleton).
    Se inicializa la primera vez que se llama.
    
    Returns:
        Instancia del gestor de secretos
    """
    return _default_factory.get_manager()


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Obtiene un secreto usando el gestor global.
    
    Args:
        key: Nombre del secreto
        default: Valor por defecto si no se encuentra
        
    Returns:
        Valor del secreto o None
    """
    manager = get_secrets_manager()
    return manager.get_secret(key, default)


def reset_secrets_manager() -> None:
    """
    Resetea el gestor de secretos global (útil para tests).
    """
    _default_factory.reset()

