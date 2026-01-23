"""Router para autenticación."""
from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter

from fastapi import Request

from scrapinsta.crosscutting.exceptions import UnauthorizedError, ForbiddenError
from scrapinsta.infrastructure.auth.jwt_auth import create_access_token
from scrapinsta.interface.dependencies import get_dependencies

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_deps_from_request(request: Request):
    """Obtiene dependencias desde request.app.state o usa get_dependencies()."""
    if hasattr(request.app.state, 'dependencies'):
        return request.app.state.dependencies
    return get_dependencies()


class LoginRequest(BaseModel):
    api_key: str = Field(..., description="API key del cliente")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    client_id: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request):
    """
    Autentica un cliente usando API key y retorna un token JWT.
    """
    deps = _get_deps_from_request(request)
    client = deps.client_repo.get_by_api_key(body.api_key)
    if not client:
        raise UnauthorizedError("API key inválida")
    
    if client.get("status") != "active":
        raise ForbiddenError("Cliente suspendido o eliminado")
    
    access_token = create_access_token({
        "client_id": client["id"],
        "scopes": ["fetch", "analyze", "send"]
    })
    
    return LoginResponse(
        access_token=access_token,
        client_id=client["id"]
    )

