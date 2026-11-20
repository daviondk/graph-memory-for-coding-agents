from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import OpenAI


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    @classmethod
    def from_api(cls, usage: Any) -> TokenUsage:
        if usage is None:
            return cls()
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    finish_reason: str | None = None
    usage: TokenUsage | None = None

    @property
    def should_execute_tools(self) -> bool:
        return bool(self.tool_calls)


def _http_client_from_env(explicit_proxy: str | None = None) -> httpx.Client | None:
    proxy = (
        explicit_proxy
        or os.environ.get("LLM_HTTP_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
    )
    if not proxy:
        return None
    return httpx.Client(proxy=proxy, timeout=httpx.Timeout(300.0))


class LLMProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        http_proxy: str | None = None,
    ) -> None:
        load_dotenv()
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL")
        self.model = model or os.environ.get("LLM_MODEL", "")
        self.temperature = temperature
        if not self.api_key:
            raise ValueError("LLM_API_KEY is required")
        if not self.model:
            raise ValueError("LLM_MODEL is required")
        http_client = _http_client_from_env(http_proxy)
        if http_client is None:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=http_client,
            )

    @classmethod
    def from_env(cls) -> LLMProvider:
        return cls()

    @classmethod
    def from_judge_env(cls) -> LLMProvider:
        load_dotenv()
        api_key = os.environ.get("JUDGE_API_KEY") or os.environ.get("LLM_API_KEY", "")
        base_url = os.environ.get("JUDGE_BASE_URL") or os.environ.get("LLM_BASE_URL")
        model = os.environ.get("JUDGE_LLM") or os.environ.get("LLM_MODEL", "")
        judge_proxy = os.environ.get("JUDGE_HTTP_PROXY")
        return cls(api_key=api_key, base_url=base_url, model=model, http_proxy=judge_proxy)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for raw in message.tool_calls:
                fn = raw.function
                args_raw = fn.arguments or "{}"
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id=raw.id,
                        name=fn.name,
                        arguments=args if isinstance(args, dict) else {},
                    )
                )
        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=TokenUsage.from_api(getattr(response, "usage", None)),
        )
