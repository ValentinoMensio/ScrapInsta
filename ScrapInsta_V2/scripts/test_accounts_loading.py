#!/usr/bin/env python3
"""
Script para verificar que el sistema carga correctamente las cuentas de Instagram,
incluyendo contraseñas cifradas.

Uso:
    python3 scripts/test_accounts_loading.py
"""

import sys
import os
from pathlib import Path

# Agregar el directorio raíz al path para importar módulos
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from dotenv import load_dotenv
from scrapinsta.config.settings import Settings
from scrapinsta.crosscutting.encryption import is_encrypted_password

load_dotenv()


def main():
    print("=" * 60)
    print("🔍 Verificación de Carga de Cuentas de Instagram")
    print("=" * 60)
    print()
    
    # Verificar ENCRYPTION_KEY
    encryption_key = os.getenv("ENCRYPTION_KEY")
    if encryption_key:
        print(f"✅ ENCRYPTION_KEY configurada ({len(encryption_key)} caracteres)")
    else:
        print("⚠️  ENCRYPTION_KEY no configurada (las contraseñas cifradas no funcionarán)")
    
    print()
    
    # Cargar Settings
    print("📦 Cargando configuración...")
    try:
        settings = Settings()
        print("   ✅ Settings cargado correctamente")
    except Exception as e:
        print(f"   ❌ Error al cargar Settings: {e}")
        sys.exit(1)
    
    print()
    
    # Obtener cuentas
    print("👤 Cargando cuentas de Instagram...")
    try:
        accounts = settings.get_accounts()
        print(f"   ✅ {len(accounts)} cuenta(s) encontrada(s)")
    except Exception as e:
        print(f"   ❌ Error al cargar cuentas: {e}")
        sys.exit(1)
    
    print()
    
    if not accounts:
        print("⚠️  No se encontraron cuentas de Instagram")
        print()
        print("💡 Verifica que tengas configurado uno de estos:")
        print("   - SECRET_ACCOUNTS_PATH apuntando a un archivo JSON")
        print("   - INSTAGRAM_ACCOUNTS_JSON con el JSON en la variable")
        print("   - INSTAGRAM_ACCOUNTS_PATH apuntando a un archivo JSON")
        return
    
    # Mostrar información de cada cuenta
    print("=" * 60)
    print("📋 Detalles de las Cuentas:")
    print("=" * 60)
    print()
    
    for i, account in enumerate(accounts, 1):
        print(f"Cuenta #{i}:")
        print(f"  👤 Username: {account.username}")
        
        # Verificar si la contraseña está cifrada (en el archivo original)
        # Nota: En este punto ya está descifrada por Settings
        password = account.password
        print(f"  🔑 Password: {'*' * min(len(password), 20)}...")
        print(f"  📏 Longitud: {len(password)} caracteres")
        
        if account.proxy:
            print(f"  🌐 Proxy: {account.proxy}")
        else:
            print(f"  🌐 Proxy: No configurado")
        
        print()
    
    # Verificar que las contraseñas se pueden usar
    print("=" * 60)
    print("✅ Verificación de Funcionamiento:")
    print("=" * 60)
    print()
    
    for account in accounts:
        username = account.username
        password = account.password
        
        # Intentar obtener la contraseña usando el método de Settings
        retrieved_password = settings.get_account_password(username)
        
        if retrieved_password == password:
            print(f"✅ Cuenta '{username}': Contraseña accesible correctamente")
        else:
            print(f"❌ Cuenta '{username}': Error al recuperar contraseña")
    
    print()
    print("=" * 60)
    print("✅ Verificación completada")
    print("=" * 60)
    print()
    print("💡 Si las contraseñas están cifradas en el JSON, el sistema las")
    print("   descifra automáticamente al cargar las cuentas.")


if __name__ == "__main__":
    main()


