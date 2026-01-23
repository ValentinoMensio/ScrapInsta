#!/usr/bin/env python3
"""
Script de prueba para verificar el sistema de cifrado de contraseñas.

Uso:
    python scripts/test_encryption.py
    python scripts/test_encryption.py "mi_password_a_cifrar"
"""

import sys
import os
from pathlib import Path

# Agregar el directorio raíz al path para importar módulos
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from scrapinsta.crosscutting.encryption import (
    encrypt_password,
    decrypt_password,
    is_encrypted_password,
    get_encryption
)


def test_encryption():
    """Prueba básica del sistema de cifrado."""
    print("=" * 60)
    print("🔐 Prueba del Sistema de Cifrado")
    print("=" * 60)
    print()
    
    # Verificar que ENCRYPTION_KEY está configurada
    encryption_key = os.getenv("ENCRYPTION_KEY")
    if not encryption_key:
        print("❌ ERROR: ENCRYPTION_KEY no está configurada")
        print("   Configúrala en tu archivo .env:")
        print("   ENCRYPTION_KEY=tu_clave_de_al_menos_32_caracteres")
        return False
    
    if len(encryption_key) < 32:
        print(f"⚠️  ADVERTENCIA: ENCRYPTION_KEY tiene solo {len(encryption_key)} caracteres")
        print("   Se recomienda al menos 32 caracteres para seguridad")
    else:
        print(f"✅ ENCRYPTION_KEY configurada ({len(encryption_key)} caracteres)")
    
    print()
    
    # Contraseña de prueba
    if len(sys.argv) > 1:
        test_password = sys.argv[1]
    else:
        test_password = "mi_password_secreto_123"
    
    print(f"📝 Contraseña de prueba: {test_password}")
    print()
    
    # Test 1: Cifrar
    print("1️⃣  Cifrando contraseña...")
    try:
        encrypted = encrypt_password(test_password)
        print(f"   ✅ Cifrado exitoso")
        print(f"   📦 Contraseña cifrada (base64): {encrypted[:50]}...")
        print(f"   📏 Longitud del cifrado: {len(encrypted)} caracteres")
    except Exception as e:
        print(f"   ❌ Error al cifrar: {e}")
        return False
    
    print()
    
    # Test 2: Verificar que está cifrada
    print("2️⃣  Verificando detección de cifrado...")
    is_encrypted = is_encrypted_password(encrypted)
    is_plain = is_encrypted_password(test_password)
    
    if is_encrypted and not is_plain:
        print(f"   ✅ Detección correcta:")
        print(f"      - Contraseña cifrada detectada: {is_encrypted}")
        print(f"      - Contraseña en texto plano detectada: {is_plain}")
    else:
        print(f"   ❌ Error en detección:")
        print(f"      - Contraseña cifrada detectada: {is_encrypted}")
        print(f"      - Contraseña en texto plano detectada: {is_plain}")
        return False
    
    print()
    
    # Test 3: Descifrar
    print("3️⃣  Descifrando contraseña...")
    try:
        decrypted = decrypt_password(encrypted)
        print(f"   ✅ Descifrado exitoso")
        print(f"   📦 Contraseña descifrada: {decrypted}")
    except Exception as e:
        print(f"   ❌ Error al descifrar: {e}")
        return False
    
    print()
    
    # Test 4: Verificar que coincide
    print("4️⃣  Verificando que coincide con la original...")
    if decrypted == test_password:
        print(f"   ✅ ¡Perfecto! La contraseña descifrada coincide con la original")
    else:
        print(f"   ❌ ERROR: La contraseña descifrada NO coincide")
        print(f"      Original:  {test_password}")
        print(f"      Descifrada: {decrypted}")
        return False
    
    print()
    
    # Test 5: Probar con diferentes contraseñas
    print("5️⃣  Prueba con múltiples contraseñas...")
    test_passwords = [
        "password123",
        "contraseña_con_ñ_y_acentos",
        "P@ssw0rd!$#%",
        "muy_larga_" * 10,
        "corta"
    ]
    
    all_passed = True
    for pwd in test_passwords:
        try:
            enc = encrypt_password(pwd)
            dec = decrypt_password(enc)
            if dec == pwd:
                print(f"   ✅ '{pwd[:30]}...' - OK")
            else:
                print(f"   ❌ '{pwd[:30]}...' - NO coincide")
                all_passed = False
        except Exception as e:
            print(f"   ❌ '{pwd[:30]}...' - Error: {e}")
            all_passed = False
    
    print()
    
    # Resumen
    print("=" * 60)
    if all_passed:
        print("✅ TODAS LAS PRUEBAS PASARON - El sistema de cifrado funciona correctamente")
        print()
        print("💡 Ejemplo de uso en JSON de cuentas:")
        print(f'   {{"username": "test@example.com", "password": "{encrypted[:50]}..."}}')
    else:
        print("❌ ALGUNAS PRUEBAS FALLARON - Revisa la configuración")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    # Cargar variables de entorno desde .env
    from dotenv import load_dotenv
    load_dotenv()
    
    success = test_encryption()
    sys.exit(0 if success else 1)


