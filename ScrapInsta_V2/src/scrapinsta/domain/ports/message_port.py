from __future__ import annotations
from typing import Protocol, runtime_checkable, Optional, Mapping, Any

from scrapinsta.domain.ports.browser_port import BrowserPortError


# ======================================================================
# Excepciones específicas de mensajería
# ======================================================================

class DMSendError(BrowserPortError):
    """Error base para operaciones de envío por DM."""
    retryable: bool = False


class DMTransientUIBlock(DMSendError):
    """Bloqueos temporales, overlays o rate limits blandos."""
    retryable = True


class DMInputTimeout(DMSendError):
    """No se logró interactuar con el textbox o botón a tiempo."""
    retryable = True


class DMUnexpectedError(DMSendError):
    """Errores no reintentables (e.g. usuario sin DM permitido)."""
    retryable = False


# ======================================================================
# Puertos
# ======================================================================

@runtime_checkable
class MessageSenderPort(Protocol):
    """
    Puerto para envío de mensajes directos (DM) vía UI.
    Implementaciones concretas (Selenium, API, etc.) deben manejar
    internamente la navegación, waits y errores.
    """

    def send_direct_message(self, username: str, text: str) -> bool:
        """
        Envía un mensaje directo al usuario indicado.
        Retorna True si fue exitoso, False o lanza DMSendError si falla.
        """
        ...


@runtime_checkable
class MessageComposerPort(Protocol):
    """
    Puerto para generar el texto del mensaje (usualmente mediante IA).
    Admite un contexto flexible y un ID de plantilla opcional.
    """

    def compose_message(
        self,
        ctx: Mapping[str, Any] | object,
        template_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """
        Genera el texto del mensaje según el contexto.
        - ctx: objeto o dict con atributos del perfil (username, rubro, followers, etc.)
        - template_id: identificador opcional de estilo o template
        - custom_prompt: instrucciones personalizadas del cliente (reemplaza el prompt por defecto)
        Debe devolver un string no vacío.
        """
        ...
