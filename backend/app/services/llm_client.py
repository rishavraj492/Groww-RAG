"""OpenAI-compatible chat client for prose drafts. Embeddings stay local."""

from __future__ import annotations

import threading
import time
from typing import Protocol

import httpx

from app.config import (
    LLM_MAX_COMPLETION_TOKENS,
    LLM_REASONING_EFFORT,
    LLM_REQUESTS_PER_DAY,
    LLM_REQUESTS_PER_MINUTE,
    LLM_TOKENS_PER_DAY,
    LLM_TOKENS_PER_MINUTE,
)
from app.schemas.generation import GENERATION_SCHEMA


class LLMError(Exception):
    """The chat call timed out, hit the Groq budget, returned an HTTP error, or had no message content."""


class Completer(Protocol):
    def complete(self, *, system: str, user: str) -> str:
        """Return the assistant message content."""


class LLMClient:
    """POST `{base_url}/chat/completions` and return `choices[0].message.content`."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        http_client: httpx.Client | None = None,
        requests_per_minute: int = LLM_REQUESTS_PER_MINUTE,
        requests_per_day: int = LLM_REQUESTS_PER_DAY,
        tokens_per_minute: int = LLM_TOKENS_PER_MINUTE,
        tokens_per_day: int = LLM_TOKENS_PER_DAY,
        max_completion_tokens: int = LLM_MAX_COMPLETION_TOKENS,
        reasoning_effort: str = LLM_REASONING_EFFORT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._max_completion_tokens = max_completion_tokens
        self._reasoning_effort = reasoning_effort
        self._budget = _Budget(requests_per_minute, requests_per_day, tokens_per_minute, tokens_per_day)
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def complete(self, *, system: str, user: str) -> str:
        reserved = _estimate_tokens(system, user, self._max_completion_tokens)
        self._budget.reserve(reserved)
        # Groq stores a temperature of 0 as a tiny positive value. Send 0 anyway.
        payload = {
            "model": self._model,
            "temperature": 0,
            "max_completion_tokens": self._max_completion_tokens,
            "reasoning_effort": self._reasoning_effort,
            "reasoning_format": "hidden",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "grounded_answer",
                    "strict": True,
                    "schema": GENERATION_SCHEMA,
                },
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = self._http.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError("chat completion failed") from exc
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("chat completion did not include message content") from exc
        self._budget.reconcile(reserved, _actual_tokens(body, reserved))
        if not isinstance(content, str) or not content.strip():
            raise LLMError("chat completion did not include message content")
        return content


class _Budget:
    """Rolling one-minute and one-day counters for this process."""

    def __init__(self, requests_per_minute: int, requests_per_day: int, tokens_per_minute: int, tokens_per_day: int) -> None:
        self._requests_per_minute = requests_per_minute
        self._requests_per_day = requests_per_day
        self._tokens_per_minute = tokens_per_minute
        self._tokens_per_day = tokens_per_day
        self._events: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def reserve(self, tokens: int) -> None:
        now = time.time()
        with self._lock:
            self._events = [(stamp, count) for stamp, count in self._events if now - stamp < 86400]
            minute = [(stamp, count) for stamp, count in self._events if now - stamp < 60]
            over_requests = len(minute) + 1 > self._requests_per_minute or len(self._events) + 1 > self._requests_per_day
            over_tokens = (
                sum(count for _, count in minute) + tokens > self._tokens_per_minute
                or sum(count for _, count in self._events) + tokens > self._tokens_per_day
            )
            if over_requests or over_tokens:
                raise LLMError("chat completion rate limit reached")
            self._events.append((now, tokens))

    def reconcile(self, reserved: int, actual: int) -> None:
        with self._lock:
            for index in range(len(self._events) - 1, -1, -1):
                stamp, tokens = self._events[index]
                if tokens == reserved:
                    self._events[index] = (stamp, actual)
                    return


def _estimate_tokens(system: str, user: str, max_completion_tokens: int) -> int:
    return max(1, (len(system) + len(user) + 3) // 4) + max_completion_tokens


def _actual_tokens(body: dict, fallback: int) -> int:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return fallback
    total = usage.get("total_tokens")
    if isinstance(total, int) and total >= 0:
        return total
    return fallback
