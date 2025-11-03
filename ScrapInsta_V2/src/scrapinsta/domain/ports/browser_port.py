from __future__ import annotations

from typing import Protocol, runtime_checkable, Optional, Sequence, Iterable
from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    ReelMetrics,
    PostMetrics,
    BasicStats,
    Username,
)

# =========================
# Excepciones de dominio
# =========================

class BrowserPortError(Exception):
    """
    Error base para operaciones del navegador/adaptador web.
    
    Atributos:
        retryable (bool): True si un reintento/backoff podría resolver el error.
        username (str|None): Cuenta o usuario relacionado al error (si aplica).
        code (str|None): Código o tipo categorizado del error.
        cause (BaseException|None): Excepción original que causó el error (opcional).
    """

    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        username: Optional[str] = None,
        code: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.username = username
        self.code = code
        self.cause = cause


class BrowserAuthError(BrowserPortError):
    """Error de autenticación o inicio de sesión en Instagram."""
    retryable = False


class BrowserConnectionError(BrowserPortError):
    """Error de conexión o acceso al navegador remoto/local."""
    retryable = True


class BrowserNavigationError(BrowserPortError):
    """Error al navegar entre páginas (timeout, redirect, etc.)."""
    retryable = True


class BrowserDOMError(BrowserPortError):
    """Error al interactuar con el DOM o localizar elementos."""
    retryable = False


class BrowserRateLimitError(BrowserPortError):
    """Error por límite de peticiones o bloqueos temporales."""
    retryable = True


# =========================
# Puerto: BrowserPort
# =========================

@runtime_checkable
class BrowserPort(Protocol):
    """
    Puerto de alto nivel para operaciones de navegación y scraping en Instagram.
    
    Los adaptadores concretos (p. ej. Selenium) deben implementar esta interfaz.
    Define operaciones de:
    - Obtención de snapshots de perfiles
    - Scraping de reels con métricas
    - Scraping de posts con métricas
    - Obtención de followings
    """

    def get_profile_snapshot(self, username: str) -> ProfileSnapshot:
        """
        Obtiene un snapshot completo de un perfil de Instagram.
        
        Args:
            username: Username del perfil a analizar
        
        Returns:
            ProfileSnapshot con información completa del perfil
        
        Raises:
            BrowserNavigationError: Si falla la navegación
            BrowserDOMError: Si falla el scraping del DOM
            BrowserPortError: Para otros errores
        """
        ...

    def get_followings(self, username: str, max_followings: int) -> Sequence[str]:
        """
        Obtiene la lista de usuarios seguidos por el perfil dado.
        
        Args:
            username: Username del perfil a consultar
            max_followings: Número máximo de followings a retornar
        
        Returns:
            Lista de usernames seguidos, deduplicados
        
        Raises:
            BrowserNavigationError: Si falla la navegación al perfil
            BrowserDOMError: Si falla el scraping del modal de followings
        """
        ...

    def get_reel_metrics(
        self,
        username: str,
        *,
        max_reels: int = 12,
    ) -> tuple[Sequence[ReelMetrics], BasicStats]:
        """
        Obtiene métricas de reels de un perfil.
        
        Args:
            username: Username del perfil
            max_reels: Número máximo de reels a analizar
        
        Returns:
            Tupla (lista de ReelMetrics, BasicStats)
        
        Raises:
            BrowserNavigationError: Si falla la navegación a reels
            BrowserDOMError: Si falla el scraping
        """
        ...

    def get_post_metrics(
        self,
        username: str,
        *,
        max_posts: int = 30,
    ) -> Sequence[PostMetrics]:
        """
        Obtiene métricas de posts regulares de un perfil.
        
        Args:
            username: Username del perfil
            max_posts: Número máximo de posts a analizar
        
        Returns:
            Lista de PostMetrics
        
        Raises:
            BrowserNavigationError: Si falla la navegación
            BrowserDOMError: Si falla el scraping
        """
        ...

    def fetch_followings(
        self,
        owner: Username,
        max_items: Optional[int] = None,
    ) -> Iterable[Username]:
        """
        Obtiene la lista de usuarios seguidos como Value Objects.
        
        Este método es el preferido para casos de uso del dominio,
        ya que retorna directamente Value Objects (Username).
        
        Args:
            owner: Username del perfil a consultar
            max_items: Número máximo de followings a retornar (opcional)
        
        Returns:
            Iterable de Username seguidos
        
        Raises:
            BrowserNavigationError: Si falla la navegación
            BrowserDOMError: Si falla el scraping
        
        Note:
            Implementaciones pueden usar get_followings() internamente
            y convertir los strings a Username.
        """
        ...
