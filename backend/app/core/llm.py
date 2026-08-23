from typing import Any

import litellm

from app.core.config import get_settings

settings = get_settings()


def get_completion(
    messages: list[dict[str, str]],
    **kwargs: Any,
) -> str:
    response = litellm.completion(
        model=settings.LLM_MODEL_NAME,
        api_base=settings.OLLAMA_API_BASE if settings.LLM_MODEL_NAME.startswith("ollama") else None,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content
