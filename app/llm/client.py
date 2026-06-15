import httpx
import logging
from app.llm.parser import extract_json
from app.config import settings

logger = logging.getLogger("copilot.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL_CHAIN = [
    "openai/gpt-4o-mini", 
    "mistralai/mistral-7b-instruct:free", 
    "google/gemini-2.0-flash-exp:free"
]


class LLMError(Exception):
    pass


async def call_llm(messages: list[dict], json_mode: bool = True, request_timeout: float = 25.0) -> dict:
    last_error: Exception | None = None

    for model in MODEL_CHAIN:
        try:
            content = await _call_model(model, messages, json_mode, request_timeout)
            return extract_json(content)
        except httpx.TimeoutException as e:
            logger.warning(f"{model} timed out, trying next model")
            last_error = e
            continue
        except httpx.HTTPStatusError as e:
            logger.warning(f"{model} returned {e.response.status_code}, trying next model")
            last_error = e
            continue
        except Exception as e:
            logger.warning(f"{model} failed: {e}, trying next model")
            last_error = e
            continue

    raise LLMError(f"All models failed. Last error: {last_error}")


async def _call_model(model: str, messages: list[dict], json_mode: bool, timeout: float) -> str:
    payload = {"model": model, "messages": messages, "temperature": 0.2}
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