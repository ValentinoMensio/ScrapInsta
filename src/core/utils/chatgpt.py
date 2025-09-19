from openai import OpenAI
from config import settings  # Assuming your API key is here


client = OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_custom_message(profile: dict) -> str:
    username = profile.get("username", "tu perfil")
    rubro = profile.get("rubro", "profesional")
    engagement_score = profile.get("engagement_score", 0)
    success_score = profile.get("success_score", 0)
    followers_count = profile.get("followers_count", 0)
    avg_views = profile.get("avg_views", 0)
    posts_count = profile.get("posts_count", 0)

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
    """

    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": "Eres un experto en marketing que redacta mensajes persuasivos para Instagram sin sonar técnico."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=100
    )

    return response.choices[0].message.content
