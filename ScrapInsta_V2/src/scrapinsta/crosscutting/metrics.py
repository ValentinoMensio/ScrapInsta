# -*- coding: utf-8 -*-
"""
Métricas Prometheus para observabilidad.

Expone métricas clave del sistema:
- Requests por endpoint
- Latencia de requests
- Tareas procesadas
- Tamaño de colas
- Errores por tipo
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from typing import Dict, Any


# =========================================================
# Métricas de API
# =========================================================

# Requests HTTP por endpoint y método
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

# Latencia de requests HTTP
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

# =========================================================
# Métricas de Jobs y Tasks
# =========================================================

# Tareas procesadas por tipo y estado
tasks_processed_total = Counter(
    "tasks_processed_total",
    "Total tasks processed",
    ["kind", "status", "account"]
)

# Duración de procesamiento de tareas
task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Task processing duration in seconds",
    ["kind", "account"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)
)

# Jobs activos por estado
jobs_active = Gauge(
    "jobs_active",
    "Active jobs by status",
    ["status"]
)

# Tareas en cola por estado y cuenta
tasks_queued = Gauge(
    "tasks_queued",
    "Tasks in queue by status and account",
    ["status", "account"]
)

# =========================================================
# Métricas de Base de Datos
# =========================================================

# Queries a BD por tipo
db_queries_total = Counter(
    "db_queries_total",
    "Total database queries",
    ["operation", "table"]
)

# Duración de queries
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)

# Conexiones activas a BD
db_connections_active = Gauge(
    "db_connections_active",
    "Active database connections"
)

# =========================================================
# Métricas de Rate Limiting
# =========================================================

# Requests bloqueados por rate limit
rate_limit_hits_total = Counter(
    "rate_limit_hits_total",
    "Total rate limit hits",
    ["client_id", "endpoint"]
)

# =========================================================
# Métricas de Workers
# =========================================================

# Workers activos por cuenta
workers_active = Gauge(
    "workers_active",
    "Active workers by account",
    ["account"]
)

# Errores de workers
worker_errors_total = Counter(
    "worker_errors_total",
    "Total worker errors",
    ["account", "error_type"]
)

# =========================================================
# Métricas de Selenium/Browser
# =========================================================

# Acciones de browser
browser_actions_total = Counter(
    "browser_actions_total",
    "Total browser actions",
    ["action", "account"]
)

# Duración de acciones de browser
browser_action_duration_seconds = Histogram(
    "browser_action_duration_seconds",
    "Browser action duration in seconds",
    ["action", "account"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

# =========================================================
# Funciones de utilidad
# =========================================================

def get_metrics() -> bytes:
    """
    Genera métricas en formato Prometheus.

    Returns:
        Bytes con métricas en formato Prometheus
    """
    return generate_latest()


def get_metrics_content_type() -> str:
    """
    Retorna el Content-Type para métricas Prometheus.

    Returns:
        Content-Type apropiado
    """
    return CONTENT_TYPE_LATEST


def get_metrics_json() -> Dict[str, Any]:
    """
    Obtiene métricas en formato JSON legible.

    Returns:
        Diccionario con métricas organizadas por categoría
    """
    from prometheus_client.parser import text_string_to_metric_families
    
    metrics_text = generate_latest().decode('utf-8')
    metrics_dict: Dict[str, Any] = {
        "http": {},
        "tasks": {},
        "jobs": {},
        "database": {},
        "rate_limiting": {},
        "workers": {},
        "browser": {},
    }
    
    for family in text_string_to_metric_families(metrics_text):
        family_name = family.name
        samples = []
        
        for sample in family.samples:
            sample_dict = {
                "value": float(sample.value),
                "labels": dict(sample.labels) if sample.labels else {},
            }
            # Agregar el nombre completo si es un bucket o similar
            if sample.name != family_name:
                sample_dict["metric_name"] = sample.name
            samples.append(sample_dict)
        
        # Organizar por categoría
        if family_name.startswith("http_"):
            metrics_dict["http"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
        elif family_name.startswith("task_"):
            metrics_dict["tasks"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
        elif family_name.startswith("job_"):
            metrics_dict["jobs"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
        elif family_name.startswith("db_"):
            metrics_dict["database"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
        elif family_name.startswith("rate_limit_"):
            metrics_dict["rate_limiting"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
        elif family_name.startswith("worker_"):
            metrics_dict["workers"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
        elif family_name.startswith("browser_"):
            metrics_dict["browser"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
    
    return metrics_dict


def get_metrics_summary() -> Dict[str, Any]:
    """
    Obtiene un resumen legible de las métricas más importantes.

    Returns:
        Diccionario con resumen de métricas clave en formato legible
    """
    from prometheus_client.parser import text_string_to_metric_families
    
    metrics_text = generate_latest().decode('utf-8')
    summary: Dict[str, Any] = {
        "http": {
            "requests_by_endpoint": {},
            "latency_by_endpoint": {},
        },
        "tasks": {
            "processed_by_kind": {},
        },
        "jobs": {
            "active_by_status": {},
        },
        "database": {
            "active_connections": 0.0,
        },
        "rate_limiting": {
            "total_hits": 0.0,
        },
        "workers": {
            "total_active": 0.0,
        },
    }
    
    # Variables temporales para calcular latencia
    latency_data: Dict[str, Dict[str, Any]] = {}
    
    for family in text_string_to_metric_families(metrics_text):
        if family.name == "http_requests_total":
            # Agrupar por endpoint (solo muestras con el nombre exacto, no _created)
            for sample in family.samples:
                # Ignorar muestras _created (son gauges de timestamp)
                if "_created" in sample.name or sample.name != "http_requests_total":
                    continue
                    
                endpoint = sample.labels.get("endpoint", "unknown")
                status = sample.labels.get("status_code", "unknown")
                method = sample.labels.get("method", "GET")
                
                if endpoint not in summary["http"]["requests_by_endpoint"]:
                    summary["http"]["requests_by_endpoint"][endpoint] = {
                        "total": 0.0,
                        "by_status": {},
                        "by_method": {},
                    }
                
                summary["http"]["requests_by_endpoint"][endpoint]["total"] += float(sample.value)
                summary["http"]["requests_by_endpoint"][endpoint]["by_status"][status] = \
                    summary["http"]["requests_by_endpoint"][endpoint]["by_status"].get(status, 0.0) + float(sample.value)
                summary["http"]["requests_by_endpoint"][endpoint]["by_method"][method] = \
                    summary["http"]["requests_by_endpoint"][endpoint]["by_method"].get(method, 0.0) + float(sample.value)
            
        elif family.name == "http_request_duration_seconds":
            # Procesar histogramas
            for sample in family.samples:
                endpoint = sample.labels.get("endpoint", "unknown")
                
                if endpoint not in latency_data:
                    latency_data[endpoint] = {"count": 0.0, "sum": 0.0}
                
                if "_count" in sample.name:
                    latency_data[endpoint]["count"] = float(sample.value)
                elif "_sum" in sample.name:
                    latency_data[endpoint]["sum"] = float(sample.value)
            
            # Calcular promedios
            for endpoint, data in latency_data.items():
                if data["count"] > 0:
                    avg_seconds = data["sum"] / data["count"]
                    summary["http"]["latency_by_endpoint"][endpoint] = {
                        "avg_ms": round(avg_seconds * 1000, 2),
                        "total_requests": int(data["count"]),
                    }
                    
        elif family.name == "tasks_processed_total":
            for sample in family.samples:
                kind = sample.labels.get("kind", "unknown")
                status = sample.labels.get("status", "unknown")
                
                if kind not in summary["tasks"]["processed_by_kind"]:
                    summary["tasks"]["processed_by_kind"][kind] = {}
                
                summary["tasks"]["processed_by_kind"][kind][status] = \
                    summary["tasks"]["processed_by_kind"][kind].get(status, 0.0) + float(sample.value)
            
        elif family.name == "jobs_active":
            for sample in family.samples:
                status = sample.labels.get("status", "unknown")
                summary["jobs"]["active_by_status"][status] = float(sample.value)
            
        elif family.name == "db_connections_active":
            if family.samples:
                summary["database"]["active_connections"] = float(family.samples[0].value)
            
        elif family.name == "rate_limit_hits_total":
            total_hits = sum(float(s.value) for s in family.samples)
            summary["rate_limiting"]["total_hits"] = total_hits
            
        elif family.name == "workers_active":
            total_workers = sum(float(s.value) for s in family.samples)
            summary["workers"]["total_active"] = total_workers
    
    return summary

