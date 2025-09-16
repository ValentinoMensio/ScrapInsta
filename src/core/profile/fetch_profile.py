import traceback
from selenium.webdriver.common.by import By
from core.utils.undetected import random_sleep, random_mouse_movements
import json
from pathlib import Path
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import logging
from typing import Dict, Any, Optional
from .evaluator import evaluate_profile
from core.profile.utils.reels import extract_reel_metrics
from core.profile.utils.detection import (
    is_profile_private,
    is_profile_verified,
    close_instagram_login_popup
)
from core.profile.utils.basic_stats import extract_basic_stats, extract_biography
from core.profile.utils.text_analysis import detect_rubro
from utils.validation_helpers import validate_username, validate_rubro, safe_validate_profile_data
from utils.exception_handlers import handle_selenium_exceptions, log_exception_details
from schemas.profile_schemas import ProfileAnalysisResult
from pydantic import ValidationError
from exceptions.selenium_exceptions import (
    SeleniumTimeoutError, SeleniumElementNotFoundError, SeleniumNavigationError
)
from exceptions.business_exceptions import ProfilePrivateError, ProfileNotFoundError
from exceptions.validation_exceptions import ProfileValidationError

import re

with open(Path("src/config/keywords.json"), "r", encoding="utf-8") as f:
    keywords = json.load(f)

DOCTOR_KEYWORDS = keywords["doctor_keywords"]
RUBROS = keywords["rubros"]

logger = logging.getLogger(__name__)


def fetch_profile_from_reels(driver, username: str) -> Optional[Dict[str, Any]]:
    """
    Extrae métricas de reels directamente desde su página de reels.
    """
    try:
        # Esperar a que cargue al menos un reel
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/reel/']"))
            )
        except TimeoutException:
            logger.warning(f"Advertencia: {username} - El perfil no tiene reels visibles o tardaron en cargar")
            return None

        random_sleep(0.5, 1.5)
        random_mouse_movements(driver)

        # Obtener solo las métricas relevantes desde reels
        metrics = extract_reel_metrics(driver)
        if metrics['reel_count'] == 0:
            return {
                'avg_likes': 0,
                'avg_comments': 0,
                'avg_views': 0,
                'is_verified': is_profile_verified(driver)
            }

        return {
            'avg_likes': metrics['total_likes'] / metrics['reel_count'],
            'avg_comments': metrics['total_comments'] / metrics['reel_count'],
            'avg_views': metrics['total_views'] / metrics['reel_count'],
            'is_verified': is_profile_verified(driver)
        }

    except Exception as e:
        logger.error(f"Error extrayendo métricas de reels para {username}: {e}")
        return None
    
def analyze_profile(driver, username, max_profiles=50, has_session=True):
    """
    Analiza un perfil de Instagram y guarda sus datos si cumple con los criterios.
    El análisis se realiza de manera dinámica, deteniéndose cuando se determina
    que el perfil no cumple con los criterios.
    """
    # Validar username de entrada
    try:
        validated_username = validate_username(username)
        if not validated_username:
            raise ProfileValidationError(
                f"Username inválido: {username}",
                username=username,
                field="username",
                value=username
            )
        username = validated_username
    except ProfileValidationError:
        raise
    except Exception as e:
        log_exception_details(e, {'username': username})
        raise ProfileValidationError(
            f"Error validando username: {str(e)}",
            username=username,
            field="username"
        )
    
    result = {"username": username, "status": "error", "reason": "unknown"}

    try:
        # Navegar al perfil
        try:
            driver.get(f"https://www.instagram.com/{username}/reels")
            random_sleep(2, 3)
        except Exception as e:
            raise SeleniumNavigationError(
                f"Error navegando al perfil {username}",
                to_url=f"https://www.instagram.com/{username}/reels"
            )

        if not has_session:
            try:
                close_instagram_login_popup(driver)
            except Exception as e:
                logger.warning(f"Error cerrando popup de login: {e}")

        # Verificar si el perfil es privado
        try:
            if is_profile_private(driver, timeout=3):
                logger.info(f"✘ {username} - Cuenta privada")
                result["reason"] = "private"
                return result
        except TimeoutException:
            # Si hay timeout, asumir que el perfil no existe o hay problemas de red
            raise ProfileNotFoundError(
                f"Perfil {username} no encontrado o inaccesible",
                username=username,
                search_context="reels_page"
            )
        except Exception as e:
            log_exception_details(e, {'username': username, 'operation': 'check_private'})
            raise SeleniumElementNotFoundError(
                f"Error verificando si el perfil es privado: {str(e)}",
                selector="private_profile_indicators",
                url=f"https://www.instagram.com/{username}/reels"
            )
        
        random_mouse_movements(driver)
        
        bio = extract_biography(driver)
        rubro = detect_rubro(username, bio)

        if not rubro:
            logger.info(f"✘ {username} - Sin coincidencia de rubro")
            result["reason"] = "no_rubro"
            return result

        # Validar rubro
        validated_rubro = validate_rubro(rubro)
        if not validated_rubro:
            logger.warning(f"Rubro inválido para {username}: {rubro}")
            result["reason"] = "invalid_rubro"
            return result
        rubro = validated_rubro

        stats = extract_basic_stats(driver)
        if not stats:
            logger.info(f"✘ {username} - No se pudieron extraer estadísticas básicas")
            result["reason"] = "no_stats"
            return result

        data = fetch_profile_from_reels(driver, username)
        if not data:
            result["reason"] = "no_reel_data"
            return result

        logger.info(f"✔ {username} - {rubro}")

        # Preparar datos para evaluación
        evaluation_data = {
            "username": username,
            "followers_count": max(0, stats.get("followers", 0)),
            "posts_count": max(0, stats.get("posts", 0)),
            "avg_likes": max(0.0, data.get("avg_likes", 0)),
            "avg_comments": max(0.0, data.get("avg_comments", 0)),
            "avg_views": max(0.0, data.get("avg_views", 0))
        }

        profile_evaluation = evaluate_profile(evaluation_data)

        if not profile_evaluation:
            logger.warning(f"Advertencia: {username} - No se pudo evaluar el perfil")
            result["reason"] = "no_evaluation"
            return result

        # Preparar datos finales del perfil
        profile_data = {
            "username": username,
            "bio": bio or "",
            "followers": max(0, stats.get("followers", 0)),
            "following": max(0, stats.get("following", 0)),
            "posts": max(0, stats.get("posts", 0)),
            "rubro": rubro,
            "is_private": bool(data.get("is_private", False)),
            "is_verified": bool(data.get("is_verified", False)),
            "avg_likes": max(0.0, data.get("avg_likes", 0)),
            "avg_comments": max(0.0, data.get("avg_comments", 0)),
            "avg_views": max(0.0, data.get("avg_views", 0)),
            "engagement_score": max(0.0, min(1.0, profile_evaluation.get("engagement_score", 0.0))),
            "success_score": max(0.0, min(1.0, profile_evaluation.get("success_score", 0.0)))
        }

        # Validar datos finales del perfil
        try:
            validated_profile = safe_validate_profile_data(profile_data)
            result.update({
                "status": "success",
                **validated_profile
            })
            logger.debug(f"Datos de perfil validados para {username}")
        except Exception as e:
            logger.warning(f"Error validando datos finales de {username}: {e}")
            result.update({
                "status": "success",
                **profile_data
            })

        return result

    except Exception as e:
        logger.exception(f"Error analizando perfil {username}: {e}")
        result["reason"] = str(e)
        return result