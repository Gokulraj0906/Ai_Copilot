"""
OpenRouter LLM client.

Uses a fallback model chain: primary model → fallback 1 → fallback 2.
Temperature is set low (0.1) for deterministic, grounded outputs.
json_mode=True enforces structured JSON output at the API level.
"""
import httpx
import logging
from app.llm.parser import extract_json
from app.core.config import settings

logger = logging.getLogger("copilot.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Primary: GPT-4o-mini (fast, cheap, strong instruction following)
# Fallback 1: Mistral-7B (free tier)
# Fallback 2: Gemini Flash (free tier)
MODEL_CHAIN = [
    "openai/gpt-4o-mini",
    "mistralai/mistral-7b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
]

# Low temperature = deterministic, follows catalog strictly, fewer hallucinations
TEMPERATURE = 0.1


class LLMError(Exception):
    pass


async def call_llm(
    messages: list[dict],
    json_mode: bool = True,
    request_timeout: float = 25.0,
) -> dict:
    last_error: Exception | None = None

    for model in MODEL_CHAIN:
        try:
            content = await _call_model(model, messages, json_mode, request_timeout)
            logger.info(f"LLM success with model={model}")
            return extract_json(content)
        except httpx.TimeoutException as e:
            logger.warning(f"{model} timed out, trying next model")
            last_error = e
        except httpx.HTTPStatusError as e:
            logger.warning(f"{model} returned HTTP {e.response.status_code}, trying next")
            last_error = e
        except Exception as e:
            logger.warning(f"{model} failed: {e}, trying next model")
            last_error = e

    raise LLMError(f"All models in chain failed. Last error: {last_error}")


async def _call_model(
    model: str,
    messages: list[dict],
    json_mode: bool,
    timeout: float,
) -> str:
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]