"""
Métricas Prometheus para observabilidad.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from typing import Dict, Any


http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

tasks_processed_total = Counter(
    "tasks_processed_total",
    "Total tasks processed",
    ["kind", "status", "account"]
)

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Task processing duration in seconds",
    ["kind", "account"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)
)

jobs_active = Gauge(
    "jobs_active",
    "Active jobs by status",
    ["status"]
)

tasks_queued = Gauge(
    "tasks_queued",
    "Tasks in queue by status and account",
    ["status", "account"]
)

db_queries_total = Counter(
    "db_queries_total",
    "Total database queries",
    ["operation", "table"]
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)

db_connections_active = Gauge(
    "db_connections_active",
    "Active database connections"
)

rate_limit_hits_total = Counter(
    "rate_limit_hits_total",
    "Total rate limit hits",
    ["client_id", "endpoint"]
)

workers_active = Gauge(
    "workers_active",
    "Active workers by account",
    ["account"]
)

worker_errors_total = Counter(
    "worker_errors_total",
    "Total worker errors",
    ["account", "error_type"]
)

browser_actions_total = Counter(
    "browser_actions_total",
    "Total browser actions",
    ["action", "account"]
)

browser_action_duration_seconds = Histogram(
    "browser_action_duration_seconds",
    "Browser action duration in seconds",
    ["action", "account"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

cleanup_operations_total = Counter(
    "cleanup_operations_total",
    "Total cleanup operations executed",
    ["operation_type"]
)

cleanup_rows_deleted_total = Counter(
    "cleanup_rows_deleted_total",
    "Total rows deleted by cleanup operations",
    ["operation_type", "table"]
)

cleanup_duration_seconds = Histogram(
    "cleanup_duration_seconds",
    "Cleanup operation duration in seconds",
    ["operation_type"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0)
)

cleanup_last_run_timestamp = Gauge(
    "cleanup_last_run_timestamp",
    "Unix timestamp of last cleanup run",
    ["operation_type"]
)

lease_cleanup_reclaimed_total = Counter(
    "lease_cleanup_reclaimed_total",
    "Total tasks reclaimed from expired leases",
    []
)

lease_cleanup_duration_seconds = Histogram(
    "lease_cleanup_duration_seconds",
    "Lease cleanup operation duration in seconds",
    [],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0)
)

# Redis metrics
redis_operations_total = Counter(
    "redis_operations_total",
    "Total Redis operations",
    ["operation", "status"]
)

redis_operation_duration_seconds = Histogram(
    "redis_operation_duration_seconds",
    "Redis operation duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
)

redis_connection_status = Gauge(
    "redis_connection_status",
    "Redis connection status (1 = connected, 0 = disconnected)"
)

# Cache metrics
cache_operations_total = Counter(
    "cache_operations_total",
    "Total cache operations",
    ["operation", "result"]
)

cache_hit_rate = Histogram(
    "cache_hit_rate",
    "Cache hit rate per operation type",
    ["operation_type"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
)

def get_metrics() -> bytes:
    return generate_latest()


def get_metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


def get_metrics_json() -> Dict[str, Any]:
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
            if sample.name != family_name:
                sample_dict["metric_name"] = sample.name
            samples.append(sample_dict)
        
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
        elif family_name.startswith("cleanup_") or family_name.startswith("lease_cleanup_"):
            metrics_dict["cleanup"][family_name] = {
                "help": family.documentation,
                "type": family.type,
                "samples": samples,
            }
    
    return metrics_dict


def get_metrics_summary() -> Dict[str, Any]:
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
        "cleanup": {
            "total_operations": 0.0,
            "total_rows_deleted": 0.0,
            "last_run_timestamps": {},
        },
    }
    
    latency_data: Dict[str, Dict[str, Any]] = {}
    
    for family in text_string_to_metric_families(metrics_text):
        if family.name == "http_requests_total":
            for sample in family.samples:
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
            for sample in family.samples:
                endpoint = sample.labels.get("endpoint", "unknown")
                
                if endpoint not in latency_data:
                    latency_data[endpoint] = {"count": 0.0, "sum": 0.0}
                
                if "_count" in sample.name:
                    latency_data[endpoint]["count"] = float(sample.value)
                elif "_sum" in sample.name:
                    latency_data[endpoint]["sum"] = float(sample.value)
            
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
        
        elif family.name == "cleanup_operations_total":
            total_ops = sum(float(s.value) for s in family.samples)
            summary["cleanup"]["total_operations"] = total_ops
        
        elif family.name == "cleanup_rows_deleted_total":
            total_rows = sum(float(s.value) for s in family.samples)
            summary["cleanup"]["total_rows_deleted"] = total_rows
        
        elif family.name == "cleanup_last_run_timestamp":
            for sample in family.samples:
                op_type = sample.labels.get("operation_type", "unknown")
                summary["cleanup"]["last_run_timestamps"][op_type] = float(sample.value)
    
    return summary

