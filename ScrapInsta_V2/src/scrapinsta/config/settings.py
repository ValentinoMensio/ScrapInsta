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
from scrapinsta.config.secrets_loader import SecretsLoader
from scrapinsta.crosscutting.password_decryptor import PasswordDecryptor

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


class DBSettings(BaseModel):
    host: str
    port: int
    user: str
    password: str
    name: str

    @property
    def dsn(self) -> str:
        user = quote_plus(self.user)
        pwd = quote_plus(self.password)
        return f"mysql://{user}:{pwd}@{self.host}:{self.port}/{self.name}?charset=utf8mb4"


class SecuritySettings(BaseModel):
    secrets_provider: Optional[str]
    encryption_key: Optional[str]
    enable_encrypted_passwords: bool


class WorkerSettings(BaseModel):
    queues_backend: str
    queue_maxsize: int
    worker_max_inflight_per_account: int
    worker_tokens_capacity: int
    worker_tokens_refill_per_sec: float
    worker_max_backoff_s: float
    worker_base_backoff_s: float
    worker_jitter_s: float
    worker_aging_step: float
    worker_aging_cap: float
    worker_load_balance_weight: float
    worker_token_availability_weight: float
    worker_urgency_weight: float
    worker_default_batch_size: int
    sqs_task_queue_url: Optional[str]
    sqs_result_queue_url: Optional[str]
    aws_region: Optional[str]


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
    db_connect_timeout: float = Field(default=5.0, env=["DB_CONNECT_TIMEOUT"])
    db_read_timeout: float = Field(default=10.0, env=["DB_READ_TIMEOUT"])
    db_write_timeout: float = Field(default=10.0, env=["DB_WRITE_TIMEOUT"])
    
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
            loader = SecretsLoader(secrets_manager)
            loader.load_into_settings(self)
        except Exception as e:
            # No fallar si el gestor de secretos no está disponible
            log.warning("secrets_load_failed", error=str(e)) 

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
    redis_socket_keepalive: bool = Field(default=True, env="REDIS_SOCKET_KEEPALIVE")
    redis_health_check_interval: int = Field(default=30, env="REDIS_HEALTH_CHECK_INTERVAL")
    
    # --- Redis Cache TTLs ---
    redis_cache_profile_ttl: int = Field(default=3600, env="REDIS_CACHE_PROFILE_TTL")  # 1 hora
    redis_cache_analysis_ttl: int = Field(default=3600, env="REDIS_CACHE_ANALYSIS_TTL")  # 1 hora
    
    # --- Secrets Management ---
    secrets_provider: Optional[str] = Field(default=None, env="SECRETS_PROVIDER")
    encryption_key: Optional[str] = Field(default=None, env="ENCRYPTION_KEY")
    enable_encrypted_passwords: bool = Field(default=True, env="ENABLE_ENCRYPTED_PASSWORDS")
    
    # Instancia de PasswordDecryptor (se inicializa después de la validación)
    _password_decryptor: Optional[PasswordDecryptor] = None
    _accounts_cache: Optional[List[AccountConfig]] = None
    _accounts_view_cache: Optional[AccountsView] = None
    _accounts_index_cache: Optional[Dict[str, AccountConfig]] = None
    _db_settings_cache: Optional[DBSettings] = None
    _security_settings_cache: Optional[SecuritySettings] = None
    _worker_settings_cache: Optional[WorkerSettings] = None

    @model_validator(mode='after')
    def _load_secrets_after_init(self):
        """
        Carga secretos desde el gestor de secretos después de la inicialización.
        Esto permite sobreescribir valores de entorno con secretos externos.
        """
        # Inicializar password decryptor
        self._password_decryptor = PasswordDecryptor(enabled=self.enable_encrypted_passwords)
        
        # Cargar secretos desde gestor
        self._load_secrets_from_manager()
        self._reset_accounts_cache()
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
        if self._password_decryptor is None:
            # Fallback si no está inicializado (no debería pasar)
            return password
        
        try:
            return self._password_decryptor.decrypt_if_needed(password)
        except Exception as e:
            log.error(
                "password_decrypt_failed",
                error=str(e),
                message="Error al descifrar contraseña, usando valor original"
            )
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
            # Usar polimorfismo en lugar de nombre de clase
            if secrets_manager.is_external_provider or os.getenv("SECRETS_PROVIDER"):
                accounts_data = secrets_manager.get_secret("instagram_accounts")
                if accounts_data:
                    try:
                        payload = json.loads(accounts_data)
                        normalized = self._normalize_accounts_payload(payload)
                        if normalized:
                            log.info(
                                "accounts_loaded_from_secrets_manager",
                                provider=secrets_manager.__class__.__name__
                            )
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

    def _reset_accounts_cache(self) -> None:
        self._accounts_cache = None
        self._accounts_view_cache = None
        self._accounts_index_cache = None

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

    def _get_accounts_cached(self) -> List[AccountConfig]:
        if self._accounts_cache is None:
            self._accounts_cache = self._build_accounts()
        return self._accounts_cache

    def _get_accounts_index(self) -> Dict[str, AccountConfig]:
        if self._accounts_index_cache is None:
            self._accounts_index_cache = {acc.username: acc for acc in self._get_accounts_cached()}
        return self._accounts_index_cache

    # ---------- API pública ----------
    model_config = SettingsConfigDict(case_sensitive=False)
    @property
    def accounts_view(self) -> AccountsView:
        if self._accounts_view_cache is None:
            self._accounts_view_cache = AccountsView(items=self._get_accounts_cached())
        return self._accounts_view_cache

    def get_accounts(self) -> List[AccountConfig]:
        return self._get_accounts_cached()

    def get_accounts_usernames(self) -> List[str]:
        return [a.username for a in self.get_accounts()]

    def get_account_password(self, username: str) -> Optional[str]:
        if not username:
            return None
        acc = self._get_accounts_index().get(username.strip().lower())
        return acc.password if acc else None

    def get_account_proxy(self, username: str) -> Optional[str]:
        if not username:
            return None
        acc = self._get_accounts_index().get(username.strip().lower())
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
        return self.db.dsn

    @property
    def db(self) -> DBSettings:
        if self._db_settings_cache is None:
            self._db_settings_cache = DBSettings(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_pass,
                name=self.db_name,
            )
        return self._db_settings_cache

    @property
    def security(self) -> SecuritySettings:
        if self._security_settings_cache is None:
            self._security_settings_cache = SecuritySettings(
                secrets_provider=self.secrets_provider,
                encryption_key=self.encryption_key,
                enable_encrypted_passwords=self.enable_encrypted_passwords,
            )
        return self._security_settings_cache

    @property
    def worker(self) -> WorkerSettings:
        if self._worker_settings_cache is None:
            self._worker_settings_cache = WorkerSettings(
                queues_backend=self.queues_backend,
                queue_maxsize=self.queue_maxsize,
                worker_max_inflight_per_account=self.worker_max_inflight_per_account,
                worker_tokens_capacity=self.worker_tokens_capacity,
                worker_tokens_refill_per_sec=self.worker_tokens_refill_per_sec,
                worker_max_backoff_s=self.worker_max_backoff_s,
                worker_base_backoff_s=self.worker_base_backoff_s,
                worker_jitter_s=self.worker_jitter_s,
                worker_aging_step=self.worker_aging_step,
                worker_aging_cap=self.worker_aging_cap,
                worker_load_balance_weight=self.worker_load_balance_weight,
                worker_token_availability_weight=self.worker_token_availability_weight,
                worker_urgency_weight=self.worker_urgency_weight,
                worker_default_batch_size=self.worker_default_batch_size,
                sqs_task_queue_url=self.sqs_task_queue_url,
                sqs_result_queue_url=self.sqs_result_queue_url,
                aws_region=self.aws_region,
            )
        return self._worker_settings_cache
    
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
