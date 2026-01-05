"""
Tests para SendMessageUseCase.
"""
import pytest
from unittest.mock import Mock
from scrapinsta.application.use_cases.send_message import SendMessageUseCase
from scrapinsta.application.dto.messages import MessageRequest, MessageContext
from scrapinsta.domain.models.profile_models import ProfileSnapshot, PrivacyStatus
from scrapinsta.domain.ports.browser_port import BrowserNavigationError
from scrapinsta.domain.ports.message_port import (
    DMTransientUIBlock,
    DMInputTimeout,
    DMUnexpectedError,
)


class TestSendMessageUseCase:
    """Tests para SendMessageUseCase."""
    
    def test_send_message_success(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
        mock_profile_repo: Mock,
    ):
        """Envío exitoso de mensaje."""
        snapshot = ProfileSnapshot(
            username="targetuser",
            bio="Bio del target",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        mock_browser_port.get_profile_snapshot.return_value = snapshot
        mock_message_composer.compose_message.return_value = "Mensaje personalizado"
        mock_message_sender.send_direct_message.return_value = True
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
            profile_repo=mock_profile_repo,
        )
        
        request = MessageRequest(
            target_username="targetuser",
            message_text="Hello",
        )
        
        result = use_case(request)
        
        assert result.success is True
        assert result.target_username == "targetuser"
        assert result.error is None
        assert result.attempts >= 1
        assert result.generated_text is None
        
        mock_browser_port.get_profile_snapshot.assert_called_once_with("targetuser")
        mock_message_composer.compose_message.assert_not_called()
        mock_message_sender.send_direct_message.assert_called_once()
        
        send_call = mock_message_sender.send_direct_message.call_args
        assert send_call[0][0] == "targetuser"
        assert send_call[0][1] == "Hello"
    
    def test_send_message_without_repo(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
    ):
        """Envío sin repositorio (opcional)."""
        snapshot = ProfileSnapshot(
            username="targetuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        mock_browser_port.get_profile_snapshot.return_value = snapshot
        mock_message_composer.compose_message.return_value = "Mensaje"
        mock_message_sender.send_direct_message.return_value = True
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
            profile_repo=None,  # Sin repo
        )
        
        request = MessageRequest(target_username="targetuser", message_text=None)
        result = use_case(request)
        
        assert result.success is True
    
    def test_send_message_browser_error(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
    ):
        """Error al obtener snapshot del perfil."""
        error = BrowserNavigationError("Profile not found", username="targetuser")
        mock_browser_port.get_profile_snapshot.side_effect = error
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
        )
        
        request = MessageRequest(target_username="targetuser", message_text=None)
        
        result = use_case(request)
        assert result.success is False
        assert "snapshot failed" in result.error
    
    def test_send_message_composer_error(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
    ):
        """Error al componer mensaje."""
        snapshot = ProfileSnapshot(
            username="targetuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        mock_browser_port.get_profile_snapshot.return_value = snapshot
        mock_message_composer.compose_message.side_effect = Exception("Composer error")
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
        )
        
        # message_text=None para que se llame a compose_message
        request = MessageRequest(target_username="targetuser", message_text=None)
        
        result = use_case(request)
        assert result.success is False
        assert result.error == "compose failed"
        assert result.attempts == 0
    
    def test_send_message_transient_error(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
    ):
        """Error transitorio al enviar mensaje (retryable) que falla después de todos los reintentos."""
        snapshot = ProfileSnapshot(
            username="targetuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        mock_browser_port.get_profile_snapshot.return_value = snapshot
        mock_message_composer.compose_message.return_value = "Mensaje"
        
        # Error transitorio que se reintenta pero siempre falla
        error = DMTransientUIBlock("UI blocked")
        # DMTransientUIBlock ya tiene retryable=True por defecto
        mock_message_sender.send_direct_message.side_effect = error  # Siempre lanza el error
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
        )
        
        request = MessageRequest(target_username="targetuser", message_text=None, max_retries=2)
        
        result = use_case(request)
        
        assert result.success is False
        assert result.attempts >= 2
        assert result.error is not None
        assert "retry exhausted" in result.error.lower() or "ui block" in result.error.lower()
        assert result.target_username == "targetuser"
        assert mock_message_sender.send_direct_message.call_count >= 2
    
    def test_send_message_timeout_error(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
    ):
        """Error de timeout al enviar mensaje."""
        snapshot = ProfileSnapshot(
            username="targetuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        mock_browser_port.get_profile_snapshot.return_value = snapshot
        mock_message_composer.compose_message.return_value = "Mensaje"
        
        error = DMInputTimeout("Input timeout")
        mock_message_sender.send_direct_message.side_effect = error
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
        )
        
        request = MessageRequest(target_username="targetuser", message_text=None)
        
        result = use_case(request)
        assert result.success is False
    
    def test_send_message_unexpected_error(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
    ):
        """Error inesperado al enviar mensaje."""
        snapshot = ProfileSnapshot(
            username="targetuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        mock_browser_port.get_profile_snapshot.return_value = snapshot
        mock_message_composer.compose_message.return_value = "Mensaje"
        
        error = DMUnexpectedError("Unexpected error")
        mock_message_sender.send_direct_message.side_effect = error
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
        )
        
        request = MessageRequest(target_username="targetuser", message_text=None)
        
        result = use_case(request)
        assert result.success is False
    
    def test_send_message_normalizes_username(
        self,
        mock_browser_port: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
    ):
        """Normaliza el username antes de procesar."""
        snapshot = ProfileSnapshot(
            username="targetuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        mock_browser_port.get_profile_snapshot.return_value = snapshot
        mock_message_composer.compose_message.return_value = "Mensaje"
        mock_message_sender.send_direct_message.return_value = True
        
        use_case = SendMessageUseCase(
            browser=mock_browser_port,
            sender=mock_message_sender,
            composer=mock_message_composer,
        )
        
        # Username con espacios y @ (Pydantic lo normaliza)
        request = MessageRequest(target_username="targetuser", message_text=None)
        result = use_case(request)
        
        assert result.success is True
        # Verificar que se normalizó el username
        call_args = mock_browser_port.get_profile_snapshot.call_args
        assert call_args[0][0] == "targetuser"  # Normalizado a lowercase

