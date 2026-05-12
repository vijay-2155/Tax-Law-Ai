"""
Unified LLM provider abstraction.

Supports: Ollama (local), OpenAI, Anthropic, Google Gemini, Groq, OpenRouter, NVIDIA.
All providers expose the same async streaming interface.

Usage:
    provider = get_provider(config)
    async for token in provider.chat_stream(system, messages, model):
        print(token, end="", flush=True)
"""

from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator, Protocol

import httpx

# ---------------------------------------------------------------------------
# Settings model (passed in from config / settings API)
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: str = "ollama"          # ollama | ollama_cloud | openai | anthropic | gemini | groq | openrouter | nvidia
    model: str = "qwen2.5:7b"         # model name / id
    api_key: str = ""                  # legacy / default
    base_url: str = ""                 # override for custom endpoints
    provider_api_keys: dict[str, str] = {} # provider -> key
    # Fixed at optimal values for legal/tax use-case — not user-configurable
    temperature: float = 0.1          # near-deterministic: precise, consistent legal answers
    max_tokens: int = 4096            # long enough for detailed section-by-section explanations

    @property
    def default_top_k(self) -> int:
        """Returns the optimal number of chunks for the current provider to balance accuracy vs quota."""
        return RECOMMENDED_TOP_K.get(self.provider, 8)

    @property
    def effective_api_key(self) -> str:
        """Returns the specific key for the active provider, or the generic api_key as fallback."""
        key = self.provider_api_keys.get(self.provider)
        if key: return key
        return self.api_key

    @property
    def native_think_supported(self) -> bool:
        """Only local Ollama supports the think field; cloud proxy and other providers do not."""
        return self.provider == "ollama"

    @property
    def effective_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        import os
        if self.provider == "ollama_cloud":
            # Two modes per official docs:
            #   API key set  → direct cloud API (requires Bearer token)
            #   No API key   → local Ollama daemon (user ran `ollama signin`,
            #                  daemon transparently proxies cloud model requests)
            if self.effective_api_key:
                return "https://ollama.com"
            # In Docker, localhost:11434 is inside the container — not the host.
            # OLLAMA_BASE_URL env var lets docker-compose point to the Ollama service.
            return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        if self.provider == "ollama":
            # Read OLLAMA_BASE_URL so docker-compose can inject 'http://ollama:11434'
            # without needing to rebuild the image. Falls back to localhost for bare installs.
            return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        defaults = {
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "nvidia": "https://integrate.api.nvidia.com/v1",
            "anthropic": "https://api.anthropic.com",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
        }
        return defaults.get(self.provider, "")


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------

class LLMProvider(Protocol):
    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> AsyncIterator[str]: ...

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str: ...


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------

class OllamaProvider:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.effective_base_url

    def _resolve_model(self, model: str | None) -> str:
        m = model or self.config.model
        if m == "auto":
            return AUTO_RESOLVE.get(self.config.provider, "qwen2.5:7b")
        return m

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        think: bool = True,
    ):
        model = self._resolve_model(model)
        # Cloud models routed via the local daemon don't support the think param
        use_think = think and self.config.native_think_supported

        headers = {}
        if self.config.effective_api_key:
            headers["Authorization"] = f"Bearer {self.config.effective_api_key}"

        payload: dict = {
            "model": model,
            "system": system,
            "messages": messages,
            "stream": True,
            "options": {"temperature": self.config.temperature},
        }
        if use_think:
            payload["think"] = True

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        msg = data.get("message", {})
                        content = msg.get("content", "")
                        thinking = msg.get("thinking", "")
                        if use_think and thinking:
                            yield f"<think>{thinking}</think>"
                        elif content:
                            yield content
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        think: bool = True,
    ) -> str:
        result = []
        async for token in self.chat_stream(system, messages, model, think=think):
            result.append(token)
        return "".join(result)


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (OpenAI, Groq, OpenRouter, custom)
# ---------------------------------------------------------------------------

class OpenAICompatProvider:
    def __init__(self, config: LLMConfig):
        self.config = config

    def _client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=self.config.effective_api_key or "dummy",
            base_url=self.config.effective_base_url,
        )

    def _extra_request_kwargs(self, model: str) -> dict:
        if self.config.provider == "nvidia" and "kimi" in model.lower():
            return {"extra_body": {"chat_template_kwargs": {"thinking": True}}}
        return {}

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        model = model or self.config.model
        if model == "auto":
            model = AUTO_RESOLVE.get(self.config.provider, "gpt-4o")

        all_messages = [{"role": "system", "content": system}] + messages
        client = self._client()
        stream = await client.chat.completions.create(
            model=model,
            messages=all_messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=True,
            **self._extra_request_kwargs(model),
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str:
        model = model or self.config.model
        if model == "auto":
            model = AUTO_RESOLVE.get(self.config.provider, "gpt-4o")

        all_messages = [{"role": "system", "content": system}] + messages
        client = self._client()
        resp = await client.chat.completions.create(
            model=model,
            messages=all_messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            **self._extra_request_kwargs(model),
        )
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------

class AnthropicProvider:
    def __init__(self, config: LLMConfig):
        self.config = config

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        import json
        import anthropic

        model = model or self.config.model
        if model == "auto":
            model = "claude-3-5-sonnet-20240620"

        client = anthropic.AsyncAnthropic(api_key=self.config.effective_api_key)

        async with client.messages.stream(
            model=model,
            system=system,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str:
        import anthropic

        model = model or self.config.model
        if model == "auto":
            model = "claude-3-5-sonnet-20240620"

        client = anthropic.AsyncAnthropic(api_key=self.config.effective_api_key)
        resp = await client.messages.create(
            model=model,
            system=system,
            messages=messages,
            max_tokens=self.config.max_tokens,
        )
        return resp.content[0].text if resp.content else ""


# ---------------------------------------------------------------------------
# Google Gemini provider
# ---------------------------------------------------------------------------

class GeminiProvider:
    def __init__(self, config: LLMConfig):
        self.config = config

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        from google import genai
        from google.genai import types

        model = model or self.config.model
        if model == "auto":
            model = "gemini-2.0-flash"

        client = genai.Client(api_key=self.config.effective_api_key)

        # Convert messages to Gemini Content format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
        )

        # generate_content_stream is synchronous — run in thread pool
        import concurrent.futures
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _run_stream():
            for chunk in client.models.generate_content_stream(
                model=model, contents=contents, config=config
            ):
                loop.call_soon_threadsafe(queue.put_nowait, chunk.text or "")
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop.run_in_executor(executor, _run_stream)

        while True:
            token = await queue.get()
            if token is None:
                break
            if token:
                yield token

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str:
        from google import genai
        from google.genai import types

        model = model or self.config.model
        client = genai.Client(api_key=self.config.effective_api_key)

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
        )
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=config,
        )
        return resp.text or ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_provider(config: LLMConfig) -> OllamaProvider | OpenAICompatProvider | AnthropicProvider | GeminiProvider:
    p = config.provider.lower()
    if p == "ollama":
        return OllamaProvider(config)
    elif p == "anthropic":
        return AnthropicProvider(config)
    elif p == "gemini":
        return GeminiProvider(config)
    elif p == "ollama_cloud":
        return OllamaProvider(config)
    elif p in ("openai", "groq", "openrouter", "nvidia"):
        return OpenAICompatProvider(config)
    else:
        # Unknown provider — try OpenAI-compatible
        return OpenAICompatProvider(config)


# Default models per provider
DEFAULT_MODELS: dict[str, list[str]] = {
    "ollama": ["auto", "gemma4:latest", "qwen2.5:7b", "qwen2.5:14b", "llama3.2:3b", "mistral:7b", "phi4:14b"],
    "ollama_cloud": [
        "auto",
        "gpt-oss:120b-cloud",
        "qwen3-coder:480b-cloud",
        "nemotron-3-super:cloud",
        "glm-4.7:cloud",
        "minimax-m2.5:cloud",
        "minimax-m2.1:cloud",
        "gpt-oss:20b-cloud",
    ],
    "openai": ["auto", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["auto", "claude-sonnet-4-5", "claude-haiku-4-5-20251001", "claude-opus-4-6"],
    "gemini": ["auto", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    "groq": [
        "auto",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3-32b",
        "mixtral-8x7b-32768"
    ],
    "openrouter": ["auto", "anthropic/claude-3.5-sonnet", "openai/gpt-4o", "meta-llama/llama-3.3-70b-instruct"],
    "nvidia": [
        "auto",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "z-ai/glm-4.7",
        "minimaxai/minimax-m2.7",
        "qwen/qwen3-coder-480b-a35b-instruct",
        "stepfun-ai/step-3.5-flash",
        "mistralai/mistral-nemotron",
        "bytedance/seed-oss-36b-instruct",
        "meta/llama-4-maverick-17b-128e-instruct",
        "microsoft/phi-4-multimodal-instruct",
        "abacusai/dracarys-llama-3.1-70b-instruct",
        "moonshotai/kimi-k2-thinking",
        "moonshotai/kimi-k2-instruct",
    ],
}

# Best model per provider (used when "auto" is selected)
AUTO_RESOLVE: dict[str, str] = {
    "ollama": "gemma4:latest",
    "ollama_cloud": "gpt-oss:120b-cloud",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20240620",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "anthropic/claude-3.5-sonnet",
    "nvidia": "mistralai/mistral-large-3-675b-instruct-2512",
}

# Optimal number of chunks to send to LLM (balance accuracy vs quota)
RECOMMENDED_TOP_K: dict[str, int] = {
    "groq": 5,           # Free tier has strict TPM limits
    "openai": 10,        # Handles large context easily
    "anthropic": 10,
    "gemini": 12,        # 1M+ context window
    "ollama": 8,         # Local performance balance
    "ollama_cloud": 16,  # kimi-k2 has 256K context — use more chunks
    "openrouter": 10,
    "nvidia": 12,
}
