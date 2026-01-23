from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field, field_validator, model_validator
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, quote_plus
import json, os

from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.secrets import get_secrets_manager, get_secret
from scrapinsta.crosscutting.encryption import is_encrypted_password, decrypt_password

load_dotenv()
log = get_logger("settings")

# -----------------------------
# BASE_DIR: Raíz del proyecto
# -----------------------------
# Calcula la raíz del proyecto (sube dos niveles desde scrapinsta/config/settings.py)
BASE_DIR = Path(__file__).resolve().parents[2]

# -----------------------------
# Modelos auxiliares
# -----------------------------
class AccountConfig(BaseModel):
    username: str
    password: str
    proxy: Optional[str] = None

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, v: str) -> str:
        v = str(v).strip().lower()
        if not v:
            raise ValueError("username vacío")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not str(v):
            raise ValueError("password vacío")
        return str(v)

    @field_validator("proxy")
    @classmethod
    def _validate_proxy(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("proxy inválido (esperado: scheme://user:pass@host:puerto)")
        return v


class AccountsView(BaseModel):
    items: List[AccountConfig]


# -----------------------------
# Settings principal
# -----------------------------
class Settings(BaseSettings):
    """
    Config central de ScrapInsta.
    Lee variables si existen, pero NO depende de .env para rutas.
    """

    # --- DB ---
    db_host: str = Field(default="127.0.0.1", env=["DB_HOST"]) 
    db_port: int = Field(default=3307, env=["DB_PORT"]) 
    db_user: str = Field(default="app", env=["DB_USER"]) 
    db_pass: str = Field(default="app_password", env=["DB_PASS"]) 
    db_name: str = Field(default="scrapinsta", env=["DB_NAME"])
    
    def _load_secrets_from_manager(self) -> None:
        """
        Carga secretos desde el gestor de secretos si está configurado.
        Esto permite sobreescribir valores de entorno con secretos externos.
        """
        try:
            # Solo intentar si SECRETS_PROVIDER está configurado
            if not os.getenv("SECRETS_PROVIDER"):
                return
            
            secrets_manager = get_secrets_manager()
            
            # Cargar secretos de base de datos
            db_pass_secret = secrets_manager.get_secret("db_pass")
            if db_pass_secret:
                self.db_pass = db_pass_secret
                log.debug("db_pass_loaded_from_secrets_manager")
            
            # Cargar API key de OpenAI
            openai_key = secrets_manager.get_secret("openai_api_key")
            if openai_key and not self.openai_api_key:
                self.openai_api_key = openai_key
                log.debug("openai_api_key_loaded_from_secrets_manager")
            
            # Cargar contraseña de Redis
            redis_pass = secrets_manager.get_secret("redis_password")
            if redis_pass:
                self.redis_password = redis_pass
                log.debug("redis_password_loaded_from_secrets_manager")
        except Exception as e:
            # No fallar si el gestor de secretos no está disponible
            log.debug("secrets_load_failed", error=str(e)) 

    # --- Retry ---
    retry_max_retries: int = Field(default=3)
    retry_base_delay: float = Field(default=1.0)
    retry_backoff: float = Field(default=2.0)
    retry_jitter: float = Field(default=0.3)

    # --- Selenium / Infra ---
    selenium_url: str = Field(default="http://127.0.0.1:4444/wd/hub")
    headless: bool = Field(default=False)

    # --- IA ---
    openai_api_key: Optional[str] = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")

    # --- Archivos / Paths ---
    # Si quisieras sobreescribirlo, podrías usar DATA_DIR, pero no es necesario.
    data_dir: Optional[Path] = Field(default=None, env="DATA_DIR")
    profiles_path: Path = Field(
        # Guardamos los perfiles persistentes dentro de data/profiles/
        default_factory=lambda: Path("src/data/profiles").resolve(),
        env="PROFILES_PATH",
    )

    # --- Cuentas Instagram ---
    secret_accounts_path: Optional[str] = Field(default=None, env="SECRET_ACCOUNTS_PATH")
    instagram_accounts_json: Optional[str] = Field(default=None, env="INSTAGRAM_ACCOUNTS_JSON")
    accounts: Optional[List[Dict[str, Any]]] = Field(default=None)
    
    # --- Cola de tareas (workers) ---
    queues_backend: str = Field(default="local", env="QUEUES_BACKEND")
    queue_maxsize: int = Field(default=200, env="QUEUE_MAXSIZE")
    
    # --- Workers y Balanceo ---
    # Concurrencia y capacidad
    worker_max_inflight_per_account: int = Field(default=5, env="WORKER_MAX_INFLIGHT_PER_ACCOUNT")
    worker_tokens_capacity: int = Field(default=60, env="WORKER_TOKENS_CAPACITY")
    worker_tokens_refill_per_sec: float = Field(default=1.0, env="WORKER_TOKENS_REFILL_PER_SEC")
    
    # Backoff y retry
    worker_max_backoff_s: float = Field(default=900.0, env="WORKER_MAX_BACKOFF_S")  # 15 min
    worker_base_backoff_s: float = Field(default=15.0, env="WORKER_BASE_BACKOFF_S")
    worker_jitter_s: float = Field(default=5.0, env="WORKER_JITTER_S")
    
    # Anti-starvation y balanceo
    worker_aging_step: float = Field(default=0.05, env="WORKER_AGING_STEP")
    worker_aging_cap: float = Field(default=1.0, env="WORKER_AGING_CAP")
    worker_load_balance_weight: float = Field(default=0.7, env="WORKER_LOAD_BALANCE_WEIGHT")
    worker_token_availability_weight: float = Field(default=0.2, env="WORKER_TOKEN_AVAILABILITY_WEIGHT")
    worker_urgency_weight: float = Field(default=0.1, env="WORKER_URGENCY_WEIGHT")
    
    # Batch sizing
    worker_default_batch_size: int = Field(default=25, env="WORKER_DEFAULT_BATCH_SIZE")
    
    # --- AWS / SQS ---
    sqs_task_queue_url: Optional[str] = Field(default=None, env="SQS_TASK_QUEUE_URL")
    sqs_result_queue_url: Optional[str] = Field(default=None, env="SQS_RESULT_QUEUE_URL")
    aws_region: Optional[str] = Field(default=None, env="AWS_REGION")
    
    # --- Redis ---
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    redis_host: str = Field(default="127.0.0.1", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_socket_timeout: float = Field(default=5.0, env="REDIS_SOCKET_TIMEOUT")
    redis_socket_connect_timeout: float = Field(default=5.0, env="REDIS_SOCKET_CONNECT_TIMEOUT")
    redis_max_connections: int = Field(default=50, env="REDIS_MAX_CONNECTIONS")
    redis_decode_responses: bool = Field(default=True, env="REDIS_DECODE_RESPONSES")
    
    # --- Redis Cache TTLs ---
    redis_cache_profile_ttl: int = Field(default=3600, env="REDIS_CACHE_PROFILE_TTL")  # 1 hora
    redis_cache_analysis_ttl: int = Field(default=3600, env="REDIS_CACHE_ANALYSIS_TTL")  # 1 hora
    
    # --- Secrets Management ---
    secrets_provider: Optional[str] = Field(default=None, env="SECRETS_PROVIDER")
    encryption_key: Optional[str] = Field(default=None, env="ENCRYPTION_KEY")
    enable_encrypted_passwords: bool = Field(default=True, env="ENABLE_ENCRYPTED_PASSWORDS")

    @model_validator(mode='after')
    def _load_secrets_after_init(self):
        """
        Carga secretos desde el gestor de secretos después de la inicialización.
        Esto permite sobreescribir valores de entorno con secretos externos.
        """
        self._load_secrets_from_manager()
        return self

    # ---------- Helpers de cuentas ----------
    def _read_json_from_path(self, path_str: Optional[str]) -> Optional[Any]:
        if not path_str:
            return None
        p = Path(path_str)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("settings_json_file_read_failed", path=str(p), error=str(e))
            return None

    def _read_json_from_env(self, env_name: str) -> Optional[Any]:
        raw = os.getenv(env_name)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception as e:
            log.warning("settings_json_env_parse_failed", env_name=env_name, error=str(e))
            return None

    def _normalize_accounts_payload(self, payload: Any) -> List[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [{"username": str(k), "password": str(v)} for k, v in payload.items()]
        return []
    
    def _decrypt_password_if_needed(self, password: str) -> str:
        """
        Descifra una contraseña si está cifrada.
        
        Args:
            password: Contraseña (puede estar cifrada o no)
            
        Returns:
            Contraseña descifrada o original
        """
        if not self.enable_encrypted_passwords:
            return password
        
        if is_encrypted_password(password):
            try:
                return decrypt_password(password)
            except Exception as e:
                log.error(
                    "password_decrypt_failed",
                    error=str(e),
                    message="Error al descifrar contraseña, usando valor original"
                )
                return password
        
        return password

    def _load_accounts_payload(self) -> List[dict]:
        """
        Carga las cuentas de Instagram desde múltiples fuentes.
        Prioridad:
        1. Gestor de secretos (si está configurado)
        2. Archivo explícito (INSTAGRAM_ACCOUNTS_PATH)
        3. Variable de entorno JSON (INSTAGRAM_ACCOUNTS_JSON)
        4. Archivo de secretos Docker (SECRET_ACCOUNTS_PATH)
        5. Atributo en Settings (tests)
        """
        # 1) Intentar cargar desde gestor de secretos
        try:
            secrets_manager = get_secrets_manager()
            if secrets_manager and hasattr(secrets_manager, '__class__'):
                provider_name = secrets_manager.__class__.__name__
                if provider_name != "EnvSecretsManager" or os.getenv("SECRETS_PROVIDER"):
                    # Solo intentar si no es ENV o si está configurado explícitamente
                    accounts_data = secrets_manager.get_secret("instagram_accounts")
                    if accounts_data:
                        try:
                            payload = json.loads(accounts_data)
                            normalized = self._normalize_accounts_payload(payload)
                            if normalized:
                                log.info("accounts_loaded_from_secrets_manager", provider=provider_name)
                                return normalized
                        except Exception as e:
                            log.debug("accounts_load_from_secrets_failed", error=str(e))
        except Exception as e:
            log.debug("secrets_manager_unavailable", error=str(e))
        
        # 2) Archivo explícito
        payload = self._read_json_from_path(os.getenv("INSTAGRAM_ACCOUNTS_PATH"))
        if payload is not None:
            return self._normalize_accounts_payload(payload)
        
        # 3) ENV JSON
        payload = self._read_json_from_env("INSTAGRAM_ACCOUNTS_JSON")
        if payload is not None:
            return self._normalize_accounts_payload(payload)
        
        # 4) Secret por archivo (Docker)
        path = self.secret_accounts_path or os.getenv("SECRET_ACCOUNTS_PATH")
        payload = self._read_json_from_path(path)
        if payload is not None:
            return self._normalize_accounts_payload(payload)
        
        # 5) Fallback: atributo en Settings (tests)
        if self.accounts:
            return self._normalize_accounts_payload(self.accounts)
        
        return []

    def _build_accounts(self) -> List[AccountConfig]:
        raw_list = self._load_accounts_payload()
        if not raw_list:
            return []
        valid: List[AccountConfig] = []
        errors: List[str] = []
        for i, item in enumerate(raw_list, start=1):
            try:
                # Descifrar contraseña si está cifrada
                if "password" in item:
                    item["password"] = self._decrypt_password_if_needed(item["password"])
                valid.append(AccountConfig(**item))
            except Exception as e:
                errors.append(f"item #{i}: {e}")
        if errors:
            raise ValueError("Errores en configuración de cuentas:\n- " + "\n- ".join(errors))
        return valid

    # ---------- API pública ----------
    model_config = SettingsConfigDict(case_sensitive=False)
    @property
    def accounts_view(self) -> AccountsView:
        return AccountsView(items=self._build_accounts())

    def get_accounts(self) -> List[AccountConfig]:
        return self.accounts_view.items

    def get_accounts_usernames(self) -> List[str]:
        return [a.username for a in self.get_accounts()]

    def get_account_password(self, username: str) -> Optional[str]:
        if not username:
            return None
        index = {acc.username: acc for acc in self.get_accounts()}
        acc = index.get(username.strip().lower())
        return acc.password if acc else None

    def get_account_proxy(self, username: str) -> Optional[str]:
        if not username:
            return None
        index = {acc.username: acc for acc in self.get_accounts()}
        acc = index.get(username.strip().lower())
        return acc.proxy if acc else None

    def get_data_dir(self) -> Path:
        """
        Devuelve <repo>/data (creándolo si no existe), sin depender de .env.
        Dentro se esperan:
          - data/cookies
          - data/profile
        """
        # sube dos niveles desde scrapinsta/config/ hasta la raíz del repo
        repo_root = Path(__file__).resolve().parents[2]
        base = (Path(self.data_dir).resolve() if self.data_dir else (repo_root / "data"))
        base.mkdir(parents=True, exist_ok=True)
        return base

    # ---------- DSN de base de datos ----------
    @property
    def db_dsn(self) -> str:
        """
        DSN listo para tu fábrica de conexiones MySQL.
        Formato compatible con PyMySQL / mysqlclient:
          mysql://user:pass@host:port/dbname?charset=utf8mb4
        """
        user = quote_plus(self.db_user)
        pwd = quote_plus(self.db_pass)
        host = self.db_host
        port = self.db_port
        db   = self.db_name
        return f"mysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"
    
    def get_router_config(self) -> Any:
        """
        Crea una configuración de Router desde Settings.
        
        Returns:
            RouterConfig: Configuración para el sistema de workers y balanceo.
        """
        from scrapinsta.interface.workers.router import RouterConfig
        
        return RouterConfig(
            max_inflight_per_account=self.worker_max_inflight_per_account,
            tokens_capacity=self.worker_tokens_capacity,
            tokens_refill_per_sec=self.worker_tokens_refill_per_sec,
            max_backoff_s=self.worker_max_backoff_s,
            base_backoff_s=self.worker_base_backoff_s,
            jitter_s=self.worker_jitter_s,
            aging_step=self.worker_aging_step,
            aging_cap=self.worker_aging_cap,
            load_balance_weight=self.worker_load_balance_weight,
            token_availability_weight=self.worker_token_availability_weight,
            urgency_weight=self.worker_urgency_weight,
            default_batch_size=self.worker_default_batch_size,
        )
