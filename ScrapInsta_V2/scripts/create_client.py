#!/usr/bin/env python3
"""
Script para crear un nuevo cliente en la base de datos.

Uso:
    python scripts/create_client.py --client-id cliente_xyz --name "Empresa XYZ" --email contacto@empresa.com

O con configuración interactiva:
    python scripts/create_client.py
"""
import argparse
import secrets
import sys
from pathlib import Path
import bcrypt

# Agregar el directorio src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scrapinsta.infrastructure.db.client_repo_sql import ClientRepoSQL
from scrapinsta.config.settings import Settings


def generate_api_key(prefix: str = "scrapinsta_") -> str:
    """
    Genera una API key segura.
    
    Nota: bcrypt tiene un límite de 72 bytes, así que limitamos
    la longitud total a ~60 caracteres para estar seguros.
    """
    # Generar 24 bytes (32 caracteres en base64url) + prefijo = ~43 caracteres total
    # Esto está bien bajo el límite de 72 bytes de bcrypt
    random_part = secrets.token_urlsafe(24)
    return f"{prefix}{random_part}"


def create_client(
    client_id: str,
    name: str,
    email: str = None,
    api_key: str = None,
    metadata: dict = None,
    limits: dict = None,
) -> dict:
    """
    Crea un nuevo cliente en la base de datos.
    
    Returns:
        dict con client_id y api_key generada
    """
    settings = Settings()
    client_repo = ClientRepoSQL(settings.db_dsn)
    
    # Generar API key si no se proporciona
    if not api_key:
        api_key = generate_api_key()
    
    # Validar que la API key no exceda el límite de bcrypt (72 bytes)
    # Convertir a bytes para verificar la longitud real
    api_key_bytes = api_key.encode('utf-8')
    if len(api_key_bytes) > 72:
        # Truncar si es necesario (aunque no debería pasar con nuestra generación)
        # Necesitamos truncar de manera segura para no romper caracteres UTF-8
        while len(api_key.encode('utf-8')) > 72:
            api_key = api_key[:-1]
        print(f"⚠️  Advertencia: API key truncada a 72 bytes")
    
    # Hashear la API key usando bcrypt directamente
    # Esto evita problemas de compatibilidad con passlib durante la inicialización
    # El hash generado es compatible con passlib para verificación
    api_key_bytes = api_key.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)  # 12 rondas (mismo que passlib por defecto)
    api_key_hash = bcrypt.hashpw(api_key_bytes, salt).decode('utf-8')
    
    # Crear cliente
    try:
        client_repo.create(
            client_id=client_id,
            name=name,
            email=email,
            api_key_hash=api_key_hash,
            metadata=metadata,
        )
        print(f"✅ Cliente '{client_id}' creado exitosamente")
    except Exception as e:
        if "Duplicate entry" in str(e) or "UNIQUE constraint" in str(e):
            print(f"❌ Error: El cliente '{client_id}' o email ya existe")
            sys.exit(1)
        raise
    
    # Configurar límites si se proporcionan
    if limits:
        try:
            client_repo.update_limits(client_id, limits)
            print(f"✅ Límites configurados para '{client_id}'")
        except Exception as e:
            print(f"⚠️  Advertencia: No se pudieron configurar límites: {e}")
    else:
        # Límites por defecto
        default_limits = {
            "requests_per_minute": 60,
            "requests_per_hour": 1000,
            "requests_per_day": 10000,
            "messages_per_day": 500,
        }
        try:
            client_repo.update_limits(client_id, default_limits)
            print(f"✅ Límites por defecto configurados para '{client_id}'")
        except Exception as e:
            print(f"⚠️  Advertencia: No se pudieron configurar límites por defecto: {e}")
    
    return {
        "client_id": client_id,
        "api_key": api_key,
        "name": name,
        "email": email,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Crear un nuevo cliente en ScrapInsta",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Crear cliente con todos los parámetros
  python scripts/create_client.py --client-id cliente_xyz --name "Empresa XYZ" \\
      --email contacto@empresa.com --api-key mi_api_key_secreta

  # Crear cliente con API key generada automáticamente
  python scripts/create_client.py --client-id cliente_abc --name "Cliente ABC"

  # Crear cliente con límites personalizados
  python scripts/create_client.py --client-id cliente_premium --name "Cliente Premium" \\
      --rpm 200 --rph 10000 --rpd 100000 --mpd 5000

  # Modo interactivo
  python scripts/create_client.py
        """,
    )
    
    parser.add_argument("--client-id", help="ID único del cliente (requerido)")
    parser.add_argument("--name", help="Nombre del cliente (requerido)")
    parser.add_argument("--email", help="Email del cliente (opcional)")
    parser.add_argument(
        "--api-key",
        help="API key del cliente (si no se proporciona, se genera automáticamente)",
    )
    
    # Límites
    parser.add_argument("--rpm", type=int, help="Requests por minuto (default: 60)")
    parser.add_argument("--rph", type=int, help="Requests por hora (default: 1000)")
    parser.add_argument("--rpd", type=int, help="Requests por día (default: 10000)")
    parser.add_argument("--mpd", type=int, help="Mensajes por día (default: 500)")
    
    args = parser.parse_args()
    
    # Modo interactivo si no se proporcionan argumentos
    if not args.client_id or not args.name:
        print("=== Crear Nuevo Cliente ===\n")
        
        client_id = input("Client ID (único, sin espacios): ").strip()
        if not client_id:
            print("❌ Client ID es requerido")
            sys.exit(1)
        
        name = input("Nombre del cliente: ").strip()
        if not name:
            print("❌ Nombre es requerido")
            sys.exit(1)
        
        email = input("Email (opcional, Enter para omitir): ").strip() or None
        
        api_key = input("API Key (Enter para generar automáticamente): ").strip() or None
        
        print("\nLímites (Enter para usar valores por defecto):")
        rpm = input("Requests por minuto (default: 60): ").strip()
        rph = input("Requests por hora (default: 1000): ").strip()
        rpd = input("Requests por día (default: 10000): ").strip()
        mpd = input("Mensajes por día (default: 500): ").strip()
        
        limits = {}
        if rpm:
            limits["requests_per_minute"] = int(rpm)
        if rph:
            limits["requests_per_hour"] = int(rph)
        if rpd:
            limits["requests_per_day"] = int(rpd)
        if mpd:
            limits["messages_per_day"] = int(mpd)
        
        limits = limits if limits else None
    else:
        client_id = args.client_id
        name = args.name
        email = args.email
        api_key = args.api_key
        
        limits = {}
        if args.rpm:
            limits["requests_per_minute"] = args.rpm
        if args.rph:
            limits["requests_per_hour"] = args.rph
        if args.rpd:
            limits["requests_per_day"] = args.rpd
        if args.mpd:
            limits["messages_per_day"] = args.mpd
        limits = limits if limits else None
    
    # Crear cliente
    result = create_client(
        client_id=client_id,
        name=name,
        email=email,
        api_key=api_key,
        limits=limits,
    )
    
    # Mostrar información importante
    print("\n" + "=" * 60)
    print("✅ CLIENTE CREADO EXITOSAMENTE")
    print("=" * 60)
    print(f"Client ID: {result['client_id']}")
    print(f"Nombre: {result['name']}")
    if result['email']:
        print(f"Email: {result['email']}")
    print(f"\n🔑 API KEY (GUARDA ESTA INFORMACIÓN):")
    print(f"   {result['api_key']}")
    print("\n⚠️  IMPORTANTE: Esta API key no se mostrará nuevamente.")
    print("   Guárdala en un lugar seguro.")
    print("\n📝 Uso en la API:")
    print(f"   curl -X POST 'https://api.example.com/api/auth/login' \\")
    print(f"     -H 'Content-Type: application/json' \\")
    print(f"     -d '{{\"api_key\": \"{result['api_key']}\"}}'")
    print("=" * 60)


if __name__ == "__main__":
    main()

