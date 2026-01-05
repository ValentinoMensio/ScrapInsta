from __future__ import annotations

import logging
import time
import re
from typing import Optional, Protocol

from scrapinsta.application.dto.messages import (
    MessageRequest,
    MessageResult,
    MessageContext,
)
from scrapinsta.domain.models.profile_models import ProfileSnapshot

from scrapinsta.domain.ports.browser_port import BrowserPort, BrowserPortError
from scrapinsta.domain.ports.profile_repo import ProfileRepository
from scrapinsta.domain.ports.message_port import (
    MessageSenderPort, 
    MessageComposerPort,
    DMTransientUIBlock,
    DMInputTimeout,
    DMUnexpectedError,
)

from scrapinsta.crosscutting.retry import retry_auto, RetryError

logger = logging.getLogger(__name__)


class SendMessageUseCase:
    """
    Caso de uso: envío de mensajes directos (DM) en Instagram.

    Flujo:
        1. Obtener snapshot del perfil (BrowserPort)
        2. Generar texto personalizado (MessageComposerPort)
        3. Enviar DM (MessageSenderPort) con política de retry
        4. Registrar resultado en repositorio (opcional)
    """

    def __init__(
        self,
        browser: BrowserPort,
        *,
        sender: MessageSenderPort,
        composer: MessageComposerPort,
        profile_repo: Optional[ProfileRepository] = None,
    ) -> None:
        self._browser = browser
        self._sender = sender
        self._composer = composer
        self._repo = profile_repo

    def __call__(self, req: MessageRequest) -> MessageResult:
        # Usar el username normalizado del DTO (ya validado por Pydantic)
        username = req.target_username  # Ya viene normalizado a lowercase y validado

        # Inicio de timing para métricas
        start_total = time.time()
        
        # 1) Obtener snapshot actual del perfil (BrowserPort)
        try:
            start = time.time()
            snap: ProfileSnapshot = self._browser.get_profile_snapshot(username)
            snapshot_duration = time.time() - start
            logger.info("[send_message] snapshot obtenido", extra={"username": username, "duration_ms": snapshot_duration * 1000})
        except BrowserPortError as e:
            logger.exception("[send_message] snapshot error (username=%s): %s", username, e)
            return MessageResult(
                success=False, 
                error=f"snapshot failed: {e}", 
                attempts=0,
                target_username=username
            )

        # Upsert opcional del snapshot
        try:
            if self._repo:
                self._repo.upsert_profile(snap)
        except Exception as e:
            logger.warning("[send_message] upsert_profile falló (no fatal): %s", e)

        # 2) Componer o usar mensaje proporcionado
        start = time.time()
        if req.message_text and req.message_text.strip():
            # Usuario proporciona texto directamente
            text = req.message_text.strip()
            logger.info("[send_message] usando message_text proporcionado", extra={"username": username, "text_length": len(text)})
        else:
            # Componer mensaje personalizado con IA
            ctx = MessageContext(
                username=snap.username,
                rubro=snap.rubro,
                followers=snap.followers,
                posts=snap.posts,
            )
            try:
                text = (self._composer.compose_message(ctx, req.template_id) or "").strip()
            except Exception as e:
                logger.exception("[send_message] compose_message error: %s", e)
                return MessageResult(
                    success=False, 
                    error="compose failed", 
                    attempts=0,
                    target_username=username
                )
            
            compose_duration = time.time() - start
            logger.info("[send_message] mensaje compuesto", extra={"username": username, "duration_ms": compose_duration * 1000})

        if not text:
            return MessageResult(
                success=False, 
                error="mensaje vacío", 
                attempts=0,
                target_username=username
            )
        
        if len(text) < 3:
            return MessageResult(
                success=False, 
                error="mensaje muy corto (min 3 caracteres)", 
                attempts=0,
                target_username=username
            )

        # Modo dry-run (solo genera texto, no envía)
        if req.dry_run:
            total_duration = time.time() - start_total
            logger.info("[send_message] dry_run completado", extra={
                "username": username, 
                "total_ms": total_duration * 1000,
                "text_length": len(text)
            })
            return MessageResult(
                success=True, 
                attempts=0, 
                error=None, 
                screenshot_path=None,
                generated_text=text,
                target_username=username
            )

        # 3) Enviar con retry_auto sobre errores retryable
        max_retries = req.max_retries if req.max_retries and req.max_retries > 0 else 3
        attempts = 0
        
        logger.info("[send_message] iniciando envío", extra={
            "username": username,
            "max_retries": max_retries,
            "text_length": len(text)
        })

        @retry_auto(max_retries=max_retries)
        def _send_with_retry() -> bool:
            nonlocal attempts
            attempts += 1
            logger.debug("[send_message] intento %d de %d", attempts, max_retries)
            return self._sender.send_direct_message(username, text)

        try:
            ok = _send_with_retry()
            total_duration = time.time() - start_total
            
            if ok:
                logger.info("[send_message] envío exitoso", extra={
                    "username": username,
                    "attempts": attempts,
                    "total_ms": total_duration * 1000
                })
                return MessageResult(success=True, attempts=attempts, target_username=username)
            
            logger.warning("[send_message] sender retornó False", extra={
                "username": username,
                "attempts": attempts
            })
            return MessageResult(
                success=False, 
                attempts=attempts, 
                error="sender returned False",
                target_username=username
            )
            
        except RetryError as re:
            logger.error("[send_message] retry agotado al enviar DM", extra={
                "username": username,
                "attempts": attempts,
                "error": str(re)
            })
            return MessageResult(
                success=False, 
                attempts=attempts, 
                error="send retry exhausted",
                target_username=username
            )
            
        except DMTransientUIBlock as e:
            logger.error("[send_message] UI block después de retries", extra={
                "username": username,
                "attempts": attempts,
                "error": str(e)
            })
            return MessageResult(
                success=False, 
                attempts=attempts, 
                error=f"UI block: {e}",
                target_username=username
            )
            
        except DMUnexpectedError as e:
            logger.error("[send_message] error no-reintentable", extra={
                "username": username,
                "attempts": max(1, attempts),
                "error": str(e)
            })
            return MessageResult(
                success=False, 
                attempts=max(1, attempts), 
                error=str(e),
                target_username=username
            )
            
        except Exception as e:
            logger.exception("[send_message] error inesperado al enviar DM", extra={
                "username": username,
                "attempts": max(1, attempts)
            })
            return MessageResult(
                success=False, 
                attempts=max(1, attempts), 
                error="unexpected error",
                target_username=username
            )
