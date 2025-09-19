from typing import Optional
from config.settings import BASE_DIR
import json
import re
from unidecode import unidecode

KEYWORDS_PATH = BASE_DIR / "config" / "keywords.json"
with KEYWORDS_PATH.open("r", encoding="utf-8") as f:
    keywords = json.load(f)

DOCTOR_KEYWORDS = [unidecode(k.lower()) for k in keywords["doctor_keywords"]]
RUBROS = {
    rubro: [unidecode(word.lower()) for word in word_list]
    for rubro, word_list in keywords["rubros"].items()
}

def detect_rubro(username: str, bio: str) -> Optional[str]:
    """
    Detecta el rubro de un perfil a partir del username y la biografía.
    Usa coincidencia exacta de palabra (regex) y normalización sin acentos.
    """
    username_normalized = unidecode(username.lower())
    bio_normalized = unidecode(bio.lower())

    # Heurística específica para doctores
    if any(username_normalized.startswith(key) for key in DOCTOR_KEYWORDS):
        return "Doctor"

    # Búsqueda por palabras clave con coincidencia exacta
    for rubro, keywords in RUBROS.items():
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, bio_normalized):
                return rubro

    return None
