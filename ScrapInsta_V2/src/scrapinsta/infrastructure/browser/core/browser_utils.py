from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


# ------------------------------ helpers genéricos ------------------------------

def safe_username(username: str) -> str:
    """Normaliza el username para usarse como nombre de carpeta/archivo."""
    return re.sub(r"[^a-z0-9_.-]+", "_", username.strip().lower())


def parse_proxy(proxy_str: str) -> Tuple[str, str, str, str]:
    """Parses 'user:pass@host:port' or 'scheme://user:pass@host:port' -> (user, pass, host, port)."""
    # Remover esquema si existe (http://, https://, etc.)
    if "://" in proxy_str:
        proxy_str = proxy_str.split("://", 1)[1]
    
    if "@" not in proxy_str:
        raise ValueError("Proxy inválido, esperado 'user:pass@host:port' o 'scheme://user:pass@host:port'")
    credentials, address = proxy_str.split("@", 1)
    if ":" not in credentials or ":" not in address:
        raise ValueError("Proxy inválido, esperado 'user:pass@host:port' o 'scheme://user:pass@host:port'")
    p_user, p_pass = credentials.split(":", 1)
    p_host, p_port = address.split(":", 1)
    return p_user, p_pass, p_host, p_port


def quick_probe(driver, *, timeout: int = 6) -> None:
    """Intento best-effort de warm-up/red de salida, sin levantar excepciones."""
    try:
        driver.get("https://api.ipify.org?format=json")
        WebDriverWait(driver, timeout).until(lambda d: d.find_element(By.TAG_NAME, "body"))
        body = driver.find_element(By.TAG_NAME, "body").text
        logger.info("ipify: %s", body[:180].replace("\n", " "))
    except Exception as e:
        logger.debug("ipify error: %s", e)

    try:
        driver.get("https://httpbin.org/headers")
        WebDriverWait(driver, timeout).until(lambda d: d.find_element(By.TAG_NAME, "body"))
        logger.debug("httpbin headers ok")
    except Exception:
        pass


def safe_quit(driver) -> None:
    """Cierra el driver si está vivo (idempotente)."""
    if driver:
        try:
            driver.quit()
        except Exception:
            logger.debug("Error cerrando driver", exc_info=True)


def detect_chrome_major() -> Optional[int]:
    """Detecta la versión mayor de Google Chrome instalada localmente."""
    for cmd in ("google-chrome", "chromium", "chrome"):
        if shutil.which(cmd):
            try:
                out = subprocess.check_output([cmd, "--version"], text=True)
                m = re.search(r"\b(\d+)\.\d+\.\d+\.\d+\b", out)
                if m:
                    return int(m.group(1))
            except Exception:
                continue
    return None
