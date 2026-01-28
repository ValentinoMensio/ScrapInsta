from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

from seleniumwire.undetected_chromedriver.v2 import ChromeOptions

from .browser_utils import parse_proxy

logger = logging.getLogger(__name__)


def build_chrome_options(
    *,
    headless: bool,
    disable_images: bool,
    extra_flags: Optional[list[str]],
    user_agent: Optional[str],
    proxy_str: Optional[str],
) -> Tuple[ChromeOptions, Dict[str, Any]]:
    """
    Crea y configura ChromeOptions + seleniumwire_options.
    No lanza efectos colaterales; sólo prepara objetos de construcción.
    """
    opts = ChromeOptions()
    default_window_size = os.getenv("WINDOW_SIZE", "1200x800")
    if "x" in default_window_size:
        default_window_size = default_window_size.replace("x", ",")
    flags = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--metrics-recording-only",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=TranslateUI,AutomationControlled",
        "--ignore-certificate-errors",
        f"--window-size={default_window_size}",
    ]
    if headless:
        flags.append("--headless=new")
    if disable_images:
        flags.append("--blink-settings=imagesEnabled=false")

    for f in flags + (extra_flags or []):
        opts.add_argument(f)

    # Preferencias
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "intl.accept_languages": "es-AR,es",
        "webrtc.ip_handling_policy": "disable_non_proxied_udp",
        "webrtc.multiple_routes_enabled": False,
        "webrtc.nonproxied_udp_enabled": False,
    }
    try:
        opts.add_experimental_option("prefs", prefs)
    except Exception:
        logger.debug("No se pudieron fijar prefs", exc_info=True)

    # UA (si no viene por parámetro, usa uno moderno por defecto)
    ua = user_agent or (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
    try:
        opts.add_argument(f"--user-agent={ua}")
    except Exception:
        logger.debug("No se pudo fijar User-Agent", exc_info=True)

    # Proxy via selenium-wire
    seleniumwire_options: Dict[str, Any] = {}
    if proxy_str:
        p_user, p_pass, p_host, p_port = parse_proxy(proxy_str)
        seleniumwire_options = {
            "proxy": {
                "http": f"http://{p_user}:{p_pass}@{p_host}:{p_port}",
                "https": f"https://{p_user}:{p_pass}@{p_host}:{p_port}",
                "no_proxy": "localhost,127.0.0.1",
            },
            "disable_capture": True,
            "mitm_http2": False,
            "verify_ssl": True,
            "connection_timeout": 15,
            "suppress_connection_errors": True,
        }
        logger.info("Proxy configurado: %s:%s (user=***, pass=***)", p_host, p_port)

    # pageLoadStrategy "eager" (best-effort)
    try:
        opts.set_capability("pageLoadStrategy", "eager")
    except Exception:
        logger.debug("No se pudo setear pageLoadStrategy", exc_info=True)

    return opts, seleniumwire_options
