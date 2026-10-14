"""Provider boundary over the existing transports and normalized ToolSpec contract.

Only implemented providers are registered. Catalog presence is not runtime support.
Streaming is deliberately unavailable until a streaming transport exists.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException

from . import ai, model_catalog
from .ollama import OllamaProvider
from .groq import GroqProvider
from .tools.specs import ToolSpec


@dataclass(frozen=True)
class ModelCapabilities:
    tools: bool | None
    vision: bool | None
    streaming: bool = False
    structured_output: bool = False


class ModelProvider(Protocol):
    id: str

    def capabilities(self, model: str) -> ModelCapabilities: ...

    async def list_models(self, base_url: str, api_key: str) -> list[str]: ...

    async def chat(self, base_url: str, api_key: str, model: str, messages: list[dict], *,
                   tools: list[ToolSpec] | None = None, temperature: float | None = None,
                   max_tokens: int | None = None) -> ai.Completion: ...

    def stream(self, *args, **kwargs) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class ExistingProvider:
    id: str

    def capabilities(self, model: str) -> ModelCapabilities:
        info = model_catalog.get_model(model)
        if not info or info.provider != self.id:
            return ModelCapabilities(None, None)
        return ModelCapabilities(info.supports_tools, info.supports_vision)

    async def list_models(self, base_url: str, api_key: str) -> list[str]:
        result = await ai.test_provider(self.id, base_url, api_key)
        return result["models"]

    async def chat(self, base_url: str, api_key: str, model: str, messages: list[dict], *,
                   tools: list[ToolSpec] | None = None, temperature: float | None = None,
                   max_tokens: int | None = None) -> ai.Completion:
        if not tools:
            return await ai.chat_completion(self.id, base_url, api_key, model, messages,
                                            temperature=temperature, max_tokens=max_tokens)
        from .tools import loop
        transport = loop.anthropic_tool_loop if self.id == "anthropic" else loop.openai_tool_loop
        return await transport(base_url, api_key, model, messages, tools, temperature, max_tokens)

    def stream(self, *args, **kwargs) -> AsyncIterator[str]:
        raise NotImplementedError("Streaming is not implemented by this runtime")


class OpenAIProvider(ExistingProvider):
    def __init__(self):
        super().__init__("openai")


class AnthropicProvider(ExistingProvider):
    def __init__(self):
        super().__init__("anthropic")


_PROVIDERS: dict[str, ModelProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "ollama": OllamaProvider(),
    "groq": GroqProvider(),
}


def get_provider(provider: str) -> ModelProvider:
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise HTTPException(422, "Unsupported model provider") from None


def supported_providers() -> tuple[str, ...]:
    return tuple(_PROVIDERS)
