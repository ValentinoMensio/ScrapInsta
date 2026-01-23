"""
Descifrador de contraseñas con responsabilidad única.

Separa la lógica de descifrado de contraseñas de la clase Settings.
"""

from __future__ import annotations

from typing import Optional
from scrapinsta.crosscutting.encryption import (
    PasswordEncryption,
    EncryptionError,
    get_encryption
)
from scrapinsta.crosscutting.logging_config import get_logger

log = get_logger("password_decryptor")


class PasswordDecryptor:
    """
    Descifra contraseñas si están cifradas.
    
    Esta clase tiene la responsabilidad única de descifrar contraseñas,
    separándola de la lógica de configuración.
    """
    
    def __init__(
        self,
        encryption: Optional[PasswordEncryption] = None,
        enabled: bool = True
    ):
        """
        Args:
            encryption: Instancia de PasswordEncryption. Si None, usa la global
            enabled: Si False, no descifra (devuelve la contraseña tal cual)
        """
        self._encryption = encryption or get_encryption()
        self._enabled = enabled
    
    def decrypt_if_needed(self, password: str) -> str:
        """
        Descifra la contraseña si está cifrada y está habilitado.
        
        Args:
            password: Contraseña que puede estar cifrada o no
            
        Returns:
            Contraseña descifrada o original
            
        Raises:
            EncryptionError: Si hay un error al descifrar
        """
        if not password:
            return password
        
        if not self._enabled:
            return password
        
        if self._encryption.is_encrypted(password):
            try:
                decrypted = self._encryption.decrypt(password)
                log.debug("password_decrypted_successfully")
                return decrypted
            except EncryptionError as e:
                log.error(
                    "password_decrypt_failed",
                    error=str(e),
                    message="Error al descifrar contraseña"
                )
                # Re-lanzar para que el llamador pueda manejarlo
                raise
        
        return password
    
    def is_encrypted(self, password: str) -> bool:
        """
        Verifica si una contraseña está cifrada.
        
        Args:
            password: Contraseña a verificar
            
        Returns:
            True si está cifrada
        """
        if not password:
            return False
        return self._encryption.is_encrypted(password)

