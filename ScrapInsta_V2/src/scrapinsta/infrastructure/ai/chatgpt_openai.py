from __future__ import annotations

import logging
from typing import Optional, Mapping, Any, Dict

from openai import OpenAI  # pip install openai>=1.0.0
from scrapinsta.domain.ports.message_port import MessageComposerPort
from scrapinsta.config.settings import Settings  # tu settings centralizado

logger = logging.getLogger(__name__)


def _to_dict(ctx: Mapping[str, Any] | object) -> Dict[str, Any]:
    """Convierte ctx (dict / Pydantic / objeto) a dict sencillo."""
    if isinstance(ctx, dict):
        return dict(ctx)
    md = getattr(ctx, "model_dump", None)
    if callable(md):
        try:
            return md()
        except Exception:
            pass
    d = getattr(ctx, "__dict__", None)
    if isinstance(d, dict):
        return dict(d)
    # extracción por atributos comunes
    out: Dict[str, Any] = {}
    for name in ("username", "rubro", "followers", "posts", "avg_views", "engagement_score", "success_score"):
        try:
            out[name] = getattr(ctx, name)
        except Exception:
            pass
    return out


def _ctx_to_legacy_profile_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapea el contexto a formato legacy + variables extendidas.
    Incluye: bio, following, verified, private para sustitución en prompts.
    """
    return {
        "username": d.get("username") or "",
        "rubro": d.get("rubro") or "profesional",
        "engagement_score": d.get("engagement_score") or 0,
        "success_score": d.get("success_score") or 0,
        "followers_count": d.get("followers") or 0,
        "followers": d.get("followers") or 0,
        "avg_views": d.get("avg_views") or 0,
        "posts_count": d.get("posts") or 0,
        "posts": d.get("posts") or 0,
        "bio": d.get("bio") or "",
        "following": d.get("following") or d.get("followings") or 0,
        "followings": d.get("following") or d.get("followings") or 0,
        "verified": d.get("verified"),
        "private": d.get("private"),
    }


class OpenAIMessageComposer(MessageComposerPort):
    """
    Implementa el prompt HISTÓRICO (1:1) de tu proyecto viejo, pero como adapter hexagonal.
    - Usa Settings() para API key / modelo.
    - Mantiene el copy original del prompt y la estructura de llamada al API.
    """

    def __init__(
        self,
        *,
        client: Optional[OpenAI] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        s = Settings()
        self.client = client or OpenAI(api_key=s.openai_api_key or "")
        self.model = model or (s.openai_model or "gpt-4o-mini")
        self.temperature = float(temperature if temperature is not None else 0.7)
        self.max_tokens = int(max_tokens if max_tokens is not None else 100)

    def compose_message(
        self,
        ctx: Mapping[str, Any] | object,
        template_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> str:
        # 1) adaptar contexto al formato “profile” legado
        d = _to_dict(ctx)
        profile = _ctx_to_legacy_profile_dict(d)

        username = profile.get("username", "tu perfil")
        rubro = profile.get("rubro", "profesional")
        engagement_score = profile.get("engagement_score", 0)
        success_score = profile.get("success_score", 0)
        followers_count = profile.get("followers_count", 0)
        avg_views = profile.get("avg_views", 0)
        posts_count = profile.get("posts_count", 0)

        if custom_prompt and custom_prompt.strip():
            # Sustituir variables en el prompt del cliente
            bio = profile.get("bio") or ""
            following = profile.get("following") or profile.get("followings") or 0
            verified = profile.get("verified")
            private = profile.get("private")
            verified_str = "sí" if verified else "no"
            private_str = "sí" if private else "no"

            prompt = (
                custom_prompt.strip()
                .replace("{username}", str(username))
                .replace("{rubro}", str(rubro))
                .replace("{followers}", str(followers_count))
                .replace("{followers_count}", str(followers_count))
                .replace("{following}", str(following))
                .replace("{followings}", str(following))
                .replace("{posts}", str(posts_count))
                .replace("{posts_count}", str(posts_count))
                .replace("{bio}", str(bio))
                .replace("{engagement_score}", str(engagement_score))
                .replace("{success_score}", str(success_score))
                .replace("{avg_views}", str(avg_views))
                .replace("{verified}", verified_str)
                .replace("{private}", private_str)
                .replace("{is_verified}", verified_str)
                .replace("{is_private}", private_str)
            )
            prompt += f"\n\nDatos del perfil: Seguidores={followers_count}, Publicaciones={posts_count}, Engagement={engagement_score}, Success={success_score}. Redacta solo el mensaje final, breve y personal."
        else:
            prompt = f"""
        Eres un experto en marketing digital enfocado en ayudar a profesionales a mejorar su presencia en Instagram.

        Vas a redactar un mensaje breve, cálido y profesional para contactar al perfil {username}, que se presenta como {rubro}.
        El mensaje debe ser amigable, no técnico, pero mostrar que hay una evaluación personalizada de su perfil.
        Ofrece grabar un video por Loom con ideas prácticas: mejorar alcance, automatizar mensajes, crear Reels, aumentar presencia, etc.
        Además, ofrece la planificación y capacitación necesarias para crear Reels de manera eficiente y reducir el tiempo invertido en su producción.

        **Contexto de métricas para interpretar (no lo digas literalmente en el mensaje):**
        - engagement_score: mide cuánto interactúan los seguidores con el contenido. Valores bajos (< 0.01) indican poca interacción relativa.
        - success_score: combina interacción, vistas y frecuencia de publicación. Valores bajos (< 0.1) indican oportunidades de crecimiento.

        Estos son los datos del perfil:
        - Seguidores: {followers_count}
        - Publicaciones: {posts_count}
        - Promedio de vistas: {avg_views}
        - Engagement Score: {engagement_score}
        - Success Score: {success_score}

        No poner texto a completar ni presentarte.
        """.strip()

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Eres un experto en marketing que redacta mensajes persuasivos para Instagram sin sonar técnico."},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            text = (resp.choices[0].message.content or "").strip()
            return self._postprocess(text)
        except Exception as e:  # fallback local si falla el API
            logger.warning("OpenAI compose failed, using fallback: %s", e)
            return self._fallback(profile)

    @staticmethod
    def _postprocess(text: str) -> str:
        t = (text or "").strip().strip('"').strip("'")
        if len(t) > 480:
            t = t[:480].rstrip() + "…"
        return t

    @staticmethod
    def _fallback(p: Dict[str, Any]) -> str:
        uname = (p.get("username") or "hola").strip()
        rubro = (p.get("rubro") or "").strip()
        base = f"Hola {uname}, ¿cómo va? Estuve viendo tu trabajo"
        if rubro:
            base += f" en {rubro}"
        base += ". Me llamó la atención y creo que podría aportar ideas para mejorar el alcance. "
        base += "¿Te interesa que charlemos un minuto por acá?"
        return base
