"""
Utilidades de cifrado para datos sensibles.

Proporciona cifrado AES-256-GCM para contraseñas y otros datos sensibles.
"""

from __future__ import annotations

import os
import base64
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from scrapinsta.crosscutting.logging_config import get_logger

log = get_logger("encryption")


class EncryptionError(Exception):
    """Error relacionado con cifrado/descifrado."""
    pass


class PasswordEncryption:
    """
    Utilidad para cifrar/descifrar contraseñas usando AES-256-GCM.
    
    Usa una clave derivada de una master key usando PBKDF2.
    """
    
    def __init__(self, master_key: Optional[str] = None):
        """
        Args:
            master_key: Clave maestra para cifrado. Si None, se usa ENCRYPTION_KEY env var.
                       Si tampoco existe, se genera una (NO recomendado para producción).
        """
        if master_key is None:
            master_key = os.getenv("ENCRYPTION_KEY")
            if not master_key:
                log.warning(
                    "encryption_key_not_set",
                    message="ENCRYPTION_KEY no configurada. Generando clave temporal (NO SEGURO para producción)"
                )
                # Generar clave temporal (NO usar en producción)
                master_key = os.urandom(32).hex()
        
        if len(master_key) < 32:
            raise EncryptionError(
                "La clave de cifrado debe tener al menos 32 caracteres"
            )
        
        self.master_key = master_key.encode() if isinstance(master_key, str) else master_key
    
    def _derive_key(self, salt: bytes) -> bytes:
        """
        Deriva una clave de cifrado usando PBKDF2.
        
        Args:
            salt: Salt para la derivación
            
        Returns:
            Clave derivada de 32 bytes
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(self.master_key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Cifra un texto plano usando AES-256-GCM.
        
        Args:
            plaintext: Texto a cifrar
            
        Returns:
            String codificado en base64 con formato: salt|nonce|ciphertext|tag
        """
        if not plaintext:
            raise EncryptionError("No se puede cifrar un texto vacío")
        
        # Generar salt y nonce aleatorios
        salt = os.urandom(16)
        nonce = os.urandom(12)  # 96 bits para GCM
        
        # Derivar clave
        key = self._derive_key(salt)
        
        # Cifrar
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        
        # Combinar salt|nonce|ciphertext
        combined = salt + nonce + ciphertext
        
        # Codificar en base64
        return base64.b64encode(combined).decode("utf-8")
    
    def decrypt(self, encrypted: str) -> str:
        """
        Descifra un texto cifrado.
        
        Args:
            encrypted: Texto cifrado en base64 con formato: salt|nonce|ciphertext|tag
            
        Returns:
            Texto descifrado
        """
        if not encrypted:
            raise EncryptionError("No se puede descifrar un texto vacío")
        
        try:
            # Decodificar base64
            combined = base64.b64decode(encrypted.encode("utf-8"))
            
            # Extraer componentes
            salt = combined[:16]
            nonce = combined[16:28]
            ciphertext = combined[28:]
            
            # Derivar clave
            key = self._derive_key(salt)
            
            # Descifrar
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            return plaintext.decode("utf-8")
        
        except Exception as e:
            raise EncryptionError(f"Error al descifrar: {str(e)}")
    
    def is_encrypted(self, value: str) -> bool:
        """
        Detecta si un valor está cifrado.
        
        Args:
            value: Valor a verificar
            
        Returns:
            True si parece estar cifrado
        """
        if not value:
            return False
        
        try:
            # Intentar decodificar base64
            decoded = base64.b64decode(value.encode("utf-8"))
            # Verificar que tenga el tamaño mínimo (salt + nonce + algo de ciphertext)
            return len(decoded) >= 28
        except Exception:
            return False


# Instancia global (se inicializa cuando se necesita)
_encryption: Optional[PasswordEncryption] = None


def get_encryption() -> PasswordEncryption:
    """
    Obtiene la instancia global de cifrado (singleton).
    
    Returns:
        Instancia de PasswordEncryption
    """
    global _encryption
    if _encryption is None:
        _encryption = PasswordEncryption()
    return _encryption


def encrypt_password(password: str) -> str:
    """
    Cifra una contraseña usando el cifrador global.
    
    Args:
        password: Contraseña a cifrar
        
    Returns:
        Contraseña cifrada en base64
    """
    enc = get_encryption()
    return enc.encrypt(password)


def decrypt_password(encrypted: str) -> str:
    """
    Descifra una contraseña usando el cifrador global.
    
    Args:
        encrypted: Contraseña cifrada
        
    Returns:
        Contraseña descifrada
    """
    enc = get_encryption()
    return enc.decrypt(encrypted)


def is_encrypted_password(value: str) -> bool:
    """
    Detecta si una contraseña está cifrada.
    
    Args:
        value: Valor a verificar
        
    Returns:
        True si está cifrada
    """
    enc = get_encryption()
    return enc.is_encrypted(value)

