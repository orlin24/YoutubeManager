"""AI provider abstraction. Default: OpenAI-compatible chat completions via httpx.

Works with OpenAI, Azure-compatible endpoints, Groq, Together, and local servers
like Ollama (set AI_BASE_URL=http://localhost:11434/v1).
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import httpx

from app.config import get_settings
from app.utils.errors import AppError
from app.utils.logging import get_logger

logger = get_logger("ai.provider")

NOT_CONFIGURED_MSG = "AI is not configured. Please set AI_API_KEY."


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1)
    return text


class AIProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str: ...

    @abstractmethod
    def stream(self, system_prompt: str, user_prompt: str): ...  # generator of str


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _post(self, messages: list[dict], json_mode: bool, temperature: float = 0.4) -> httpx.Response:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            return httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=90,
            )
        except httpx.HTTPError as exc:
            logger.error("AI provider request failed", exc_info=exc)
            raise AppError(502, "AI_PROVIDER_ERROR", "Could not reach the AI provider.") from exc

    def generate(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        resp = self._post(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=json_mode,
        )
        if resp.status_code == 401:
            raise AppError(503, "AI_AUTH_FAILED", "AI provider rejected the API key.")
        if resp.status_code != 200:
            logger.error("AI provider error: %s %s", resp.status_code, resp.text[:400])
            raise AppError(502, "AI_PROVIDER_ERROR", "AI provider returned an error.")
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AppError(502, "AI_PROVIDER_ERROR", "Unexpected AI provider response.") from exc

    def stream(self, system_prompt: str, user_prompt: str):
        resp = self._post(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=False,
            temperature=0.4,
        )
        if resp.status_code != 200:
            raise AppError(502, "AI_PROVIDER_ERROR", "AI provider returned an error.")
        yield resp.json()["choices"][0]["message"]["content"]


def get_provider() -> AIProvider:
    s = get_settings()
    if not s.AI_API_KEY:
        raise AppError(503, "AI_NOT_CONFIGURED", NOT_CONFIGURED_MSG)
    return OpenAIProvider(s.AI_API_KEY, s.AI_MODEL, s.AI_BASE_URL)


def generate_structured(
    provider: AIProvider, system_prompt: str, user_prompt: str, schema: type | None = None
) -> dict:
    """Call provider in JSON mode, parse robustly (fence stripping + one retry)."""
    text = provider.generate(system_prompt, user_prompt, json_mode=True)
    try:
        data = json.loads(_strip_code_fences(text))
    except json.JSONDecodeError:
        # retry once
        text = provider.generate(
            system_prompt,
            user_prompt + "\n\nIMPORTANT: respond with ONLY valid JSON, no code fences.",
            json_mode=True,
        )
        try:
            data = json.loads(_strip_code_fences(text))
        except json.JSONDecodeError as exc:
            raise AppError(502, "AI_INVALID_RESPONSE", "AI returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise AppError(502, "AI_INVALID_RESPONSE", "AI returned a non-object response.")
    if schema is not None:
        try:
            return schema(**data).model_dump()
        except Exception:  # noqa: BLE001
            return data
    return data
