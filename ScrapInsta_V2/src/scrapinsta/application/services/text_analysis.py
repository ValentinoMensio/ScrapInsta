from __future__ import annotations
from typing import Optional, Dict, List
import json
import re
from functools import lru_cache

from unidecode import unidecode
from scrapinsta.config.settings import BASE_DIR

KEYWORDS_PATH = BASE_DIR / "config" / "keywords.json"


@lru_cache(maxsize=1)
def _load_keywords() -> Dict[str, List[str]]:
    with KEYWORDS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "doctor_keywords": [unidecode(k.lower()) for k in data.get("doctor_keywords", [])],
        "rubros": {
            rubro: [unidecode(w.lower()) for w in words]
            for rubro, words in data.get("rubros", {}).items()
        },
    }


def detect_rubro(username: str, bio: Optional[str]) -> Optional[str]:
    """
    Detecta rubro a partir de username y bio (bio puede ser None).
    - Heurística específica para doctores (prefijo en username).
    - Búsqueda de palabras clave por rubro (coincidencia de palabra).
    """
    kw = _load_keywords()
    doctor_keys = kw["doctor_keywords"]
    rubros = kw["rubros"]

    username_norm = unidecode((username or "").strip().lower())
    bio_norm = unidecode((bio or "").strip().lower())

    if any(username_norm.startswith(key) for key in doctor_keys):
        return "Doctor"

    for rubro, words in rubros.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", bio_norm):
                return rubro

    return None
