#!/usr/bin/env python3
"""
Script para cifrar/descifrar contraseñas de Instagram.

Uso:
    # Cifrar una contraseña
    python3 scripts/encrypt_password.py encrypt "mi_password"
    
    # Descifrar una contraseña
    python3 scripts/encrypt_password.py decrypt "MKGaZQNvH4oUaIfu3myHPd437jUQq+Oz9Zg4kctry2Px0Q2qI0..."
    
    # Verificar si está cifrada
    python3 scripts/encrypt_password.py check "MKGaZQNvH4oUaIfu3myHPd437jUQq+Oz9Zg4kctry2Px0Q2qI0..."
"""

import sys
import os
from pathlib import Path

# Agregar el directorio raíz al path para importar módulos
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from dotenv import load_dotenv
from scrapinsta.crosscutting.encryption import (
    encrypt_password,
    decrypt_password,
    is_encrypted_password
)

load_dotenv()


def main():
    if len(sys.argv) < 3:
        print("Uso:")
        print("  python3 scripts/encrypt_password.py encrypt <password>")
        print("  python3 scripts/encrypt_password.py decrypt <encrypted_password>")
        print("  python3 scripts/encrypt_password.py check <password>")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    value = sys.argv[2]
    
    # Verificar que ENCRYPTION_KEY está configurada
    encryption_key = os.getenv("ENCRYPTION_KEY")
    if not encryption_key:
        print("❌ ERROR: ENCRYPTION_KEY no está configurada en .env")
        print("   Agrega: ENCRYPTION_KEY=tu_clave_de_al_menos_32_caracteres")
        sys.exit(1)
    
    if command == "encrypt":
        try:
            encrypted = encrypt_password(value)
            print(f"✅ Contraseña cifrada:")
            print(encrypted)
            print()
            print("💡 Úsala en tu JSON de cuentas:")
            print(f'   "password": "{encrypted}"')
        except Exception as e:
            print(f"❌ Error al cifrar: {e}")
            sys.exit(1)
    
    elif command == "decrypt":
        try:
            decrypted = decrypt_password(value)
            print(f"✅ Contraseña descifrada:")
            print(decrypted)
        except Exception as e:
            print(f"❌ Error al descifrar: {e}")
            sys.exit(1)
    
    elif command == "check":
        is_enc = is_encrypted_password(value)
        if is_enc:
            print("✅ La contraseña está CIFRADA")
            try:
                decrypted = decrypt_password(value)
                print(f"   (Puede descifrarse correctamente)")
            except:
                print(f"   (Pero hay un error al descifrarla)")
        else:
            print("ℹ️  La contraseña está en TEXTO PLANO (no cifrada)")
    
    else:
        print(f"❌ Comando desconocido: {command}")
        print("   Comandos válidos: encrypt, decrypt, check")
        sys.exit(1)


if __name__ == "__main__":
    main()


