"""Router para health checks y métricas."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.metrics import (
    get_metrics,
    get_metrics_content_type,
    get_metrics_json,
    get_metrics_summary,
)
from scrapinsta.interface.dependencies import get_dependencies

logger = get_logger("routers.health")

router = APIRouter()


def _get_deps_from_request(request: Request):
    """Obtiene dependencias desde request.app.state o usa get_dependencies()."""
    if hasattr(request.app.state, 'dependencies'):
        return request.app.state.dependencies
    return get_dependencies()


@router.get("/health")
def health(request: Request):
    """
    Health check básico: verifica conectividad con BD.
    Usado para verificar que el servicio está vivo.
    """
    deps = _get_deps_from_request(request)
    try:
        deps.job_store.pending_jobs()
        return {"ok": True, "status": "healthy"}
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {"ok": False, "status": "unhealthy", "error": str(e)}


@router.get("/ready")
def ready(request: Request):
    """
    Readiness check: verifica que el servicio está listo para recibir tráfico.
    Verifica BD y dependencias críticas.
    """
    deps = _get_deps_from_request(request)
    checks = {
        "database": False,
    }
    all_ok = True

    # Verificar BD
    try:
        deps.job_store.pending_jobs()
        checks["database"] = True
    except Exception as e:
        logger.error("readiness_check_failed", component="database", error=str(e))
        all_ok = False

    status_code = 200 if all_ok else 503
    return Response(
        content=json.dumps({
            "ok": all_ok,
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
        }),
        status_code=status_code,
        media_type="application/json",
    )


@router.get("/live")
def live():
    """
    Liveness check: verifica que el proceso está vivo.
    Siempre retorna OK si el proceso está corriendo.
    """
    return {"ok": True, "status": "alive"}


@router.get("/metrics")
def metrics():
    """
    Endpoint de métricas Prometheus (formato Prometheus estándar).
    Expone todas las métricas del sistema en formato Prometheus para scraping.
    """
    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type(),
    )


@router.get("/metrics/json")
def metrics_json():
    """
    Endpoint de métricas en formato JSON legible.
    Retorna todas las métricas organizadas por categoría en formato JSON.
    """
    return get_metrics_json()


@router.get("/metrics/summary")
def metrics_summary():
    """
    Endpoint de resumen de métricas.
    Retorna un resumen legible de las métricas más importantes:
    - Requests HTTP por endpoint y status
    - Latencia promedio por endpoint
    - Tareas procesadas por tipo
    - Jobs activos
    - Conexiones de BD
    - Rate limit hits
    - Workers activos
    """
    return get_metrics_summary()

