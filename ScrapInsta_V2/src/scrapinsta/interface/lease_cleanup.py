"""
Proceso periódico para reencolar tareas con leases expirados.

Este proceso se ejecuta cada minuto para recuperar tareas que fueron leaseadas
pero cuyo worker murió o no completó la tarea dentro del TTL.
"""
from __future__ import annotations

import time
import os
from typing import Optional

from scrapinsta.config.settings import Settings
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL
from scrapinsta.crosscutting.logging_config import (
    configure_structured_logging,
    get_logger,
)

configure_structured_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
)
logger = get_logger("lease_cleanup")

_settings = Settings()
_job_store = JobStoreSQL(_settings.db_dsn)

CLEANUP_INTERVAL_SECONDS = int(os.getenv("LEASE_CLEANUP_INTERVAL", "60"))
MAX_RECLAIMED_PER_RUN = int(os.getenv("LEASE_CLEANUP_MAX_RECLAIMED", "100"))


def run_cleanup() -> int:
    """Ejecuta una pasada de limpieza de leases expirados."""
    try:
        reclaimed = _job_store.reclaim_expired_leases(max_reclaimed=MAX_RECLAIMED_PER_RUN)
        if reclaimed > 0:
            logger.info(
                "leases_reclaimed",
                count=reclaimed,
                max_reclaimed=MAX_RECLAIMED_PER_RUN,
            )
        return reclaimed
    except Exception as e:
        logger.exception(
            "lease_cleanup_failed",
            error=str(e),
        )
        return 0


def main():
    """Loop principal del proceso de limpieza."""
    logger.info(
        "lease_cleanup_started",
        interval_seconds=CLEANUP_INTERVAL_SECONDS,
        max_reclaimed_per_run=MAX_RECLAIMED_PER_RUN,
    )
    
    while True:
        try:
            start_time = time.time()
            reclaimed = run_cleanup()
            duration = time.time() - start_time
            
            logger.debug(
                "lease_cleanup_cycle",
                reclaimed=reclaimed,
                duration_ms=round(duration * 1000, 2),
            )
            
            time.sleep(CLEANUP_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("lease_cleanup_stopped", reason="SIGINT")
            break
        except Exception as e:
            logger.exception(
                "lease_cleanup_unexpected_error",
                error=str(e),
            )
            time.sleep(CLEANUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

