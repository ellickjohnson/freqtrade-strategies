"""
LLM Client - Unified interface for LLM-powered autonomous reasoning.

Supports multiple providers: Anthropic Claude, OpenAI, and local models via Ollama.
Provides structured output parsing, rate limiting, and token budgeting.
"""

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union

try:
    from pydantic import BaseModel

    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


@dataclass
class LLMConfig:
    """Configuration for LLM client."""

    provider: LLMProvider = LLMProvider.ANTHROPIC
    model: str = "claude-sonnet-4-6"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 1024
    temperature: float = 0.7
    timeout_seconds: int = 60

    # Rate limiting
    requests_per_minute: int = 60
    tokens_per_day: int = 500000

    # Retry settings
    max_retries: int = 2
    retry_delay_seconds: int = 2


@dataclass
class LLMResponse:
    """Structured response from LLM."""

    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str
    parsed_json: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    reasoning_chain: Optional[List[str]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TokenUsage:
    """Track token usage for budgeting."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    request_count: int = 0
    last_reset: datetime = field(default_factory=datetime.utcnow)

    def add_usage(self, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.request_count += 1

    def get_daily_usage(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def needs_reset(self) -> bool:
        return datetime.utcnow() - self.last_reset > timedelta(days=1)

    def reset(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.request_count = 0
        self.last_reset = datetime.utcnow()


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion."""
        pass

    @abstractmethod
    async def complete_json(
        self,
        prompt: str,
        schema: Union[Dict, Type[BaseModel]],
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Generate JSON-structured completion."""
        pass


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = None
        self._initialized = False

    async def _ensure_client(self):
        if not self._initialized:
            try:
                import anthropic

                self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
                self._initialized = True
            except ImportError:
                raise ImportError("anthropic package required: pip install anthropic")

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        await self._ensure_client()

        messages = [{"role": "user", "content": prompt}]

        response = await asyncio.wait_for(
            self.client.messages.create(
                model=self.config.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=messages,
            ),
            timeout=self.config.timeout_seconds,
        )

        content = response.content[0].text

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            finish_reason=response.stop_reason,
        )

    async def complete_json(
        self,
        prompt: str,
        schema: Union[Dict, Type[BaseModel]],
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        # Add JSON formatting instructions
        json_prompt = f"""{prompt}

Respond with a valid JSON object matching this schema:
{json.dumps(schema, indent=2) if isinstance(schema, dict) else schema.model_json_schema()}

Your response must be valid JSON only, no other text."""

        response = await self.complete(
            prompt=json_prompt,
            system_prompt=system_prompt,
            temperature=0.3,  # Lower temperature for structured output
        )

        # Parse JSON from response
        try:
            # Try to extract JSON from response
            content = response.content.strip()
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0]
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0]

            parsed = json.loads(content)
            response.parsed_json = parsed

            # Extract confidence if present
            if "confidence" in parsed:
                response.confidence = float(parsed["confidence"])

            # Extract reasoning chain if present
            if "reasoning_chain" in parsed:
                response.reasoning_chain = parsed["reasoning_chain"]

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            response.parsed_json = None

        return response


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        self.client = None
        self._initialized = False

    async def _ensure_client(self):
        if not self._initialized:
            try:
                from openai import AsyncOpenAI

                self.client = AsyncOpenAI(api_key=self.api_key)
                self._initialized = True
            except ImportError:
                raise ImportError("openai package required: pip install openai")

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        await self._ensure_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await asyncio.wait_for(
            self.client.chat.completions.create(
                model=self.config.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            ),
            timeout=self.config.timeout_seconds,
        )

        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content,
            model=response.model,
            usage={
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
            finish_reason=choice.finish_reason,
        )

    async def complete_json(
        self,
        prompt: str,
        schema: Union[Dict, Type[BaseModel]],
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        json_prompt = f"""{prompt}

Respond with a valid JSON object matching this schema:
{json.dumps(schema, indent=2) if isinstance(schema, dict) else schema.model_json_schema()}

Your response must be valid JSON only."""

        response = await self.complete(
            prompt=json_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
        )

        try:
            content = response.content.strip()
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0]
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0]

            parsed = json.loads(content)
            response.parsed_json = parsed

            if "confidence" in parsed:
                response.confidence = float(parsed["confidence"])
            if "reasoning_chain" in parsed:
                response.reasoning_chain = parsed["reasoning_chain"]

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            response.parsed_json = None

        return response


class OllamaProvider(BaseLLMProvider):
    """Ollama local model provider."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        import aiohttp

        # Use /api/chat for better multi-turn support and context management
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "num_ctx": min(max_tokens * 4, 8192),  # Limit context window for speed
                "temperature": temperature,
            },
        }

        # Use timeout from config (default 300s)
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
            ) as response:
                result = await response.json()

        content = ""
        if result.get("message") and result.get("message", {}).get("content"):
            content = result["message"]["content"]

        return LLMResponse(
            content=content or result.get("response", ""),
            model=self.config.model,
            usage={
                "input_tokens": result.get("prompt_eval_count", 0),
                "output_tokens": result.get("eval_count", 0),
            },
            finish_reason="stop",
        )

    async def complete_json(
        self,
        prompt: str,
        schema: Union[Dict, Type[BaseModel]],
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        response = await self.complete(
            prompt=f"{prompt}\n\nRespond with valid JSON only. No markdown, no code fences, no explanation.",
            system_prompt=system_prompt,
            temperature=0.3,
        )

        try:
            content = response.content.strip()
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0]
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0]

            parsed = json.loads(content.strip())
            response.parsed_json = parsed

            if "confidence" in parsed:
                response.confidence = float(parsed["confidence"])
            if "reasoning_chain" in parsed:
                response.reasoning_chain = parsed["reasoning_chain"]
        except json.JSONDecodeError as e:
            logger.warning(f"Ollama JSON parse failed: {e}")
            response.parsed_json = None

        return response


class LLMClient:
    """
    Unified LLM client with rate limiting, retry logic, and structured output.

    Usage:
        config = LLMConfig(provider=LLMProvider.ANTHROPIC)
        client = LLMClient(config)

        response = await client.analyze(
            prompt="Analyze this trading strategy...",
            schema=AnalysisResult
        )
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.provider = self._create_provider()
        self.token_usage = TokenUsage()
        self._request_times: List[float] = []
        self._lock = asyncio.Lock()
        self._available: Optional[bool] = None

    def _create_provider(self) -> BaseLLMProvider:
        if self.config.provider == LLMProvider.ANTHROPIC:
            return AnthropicProvider(self.config)
        elif self.config.provider == LLMProvider.OPENAI:
            return OpenAIProvider(self.config)
        elif self.config.provider == LLMProvider.OLLAMA:
            return OllamaProvider(self.config)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

    async def _check_rate_limit(self):
        """Check and enforce rate limits."""
        async with self._lock:
            now = time.time()

            # Clean old request times
            minute_ago = now - 60
            self._request_times = [t for t in self._request_times if t > minute_ago]

            # Check requests per minute
            if len(self._request_times) >= self.config.requests_per_minute:
                sleep_time = 60 - (now - self._request_times[0])
                if sleep_time > 0:
                    logger.info(f"Rate limit reached, sleeping for {sleep_time:.1f}s")
                    await asyncio.sleep(sleep_time)

            # Check daily token budget
            if self.token_usage.needs_reset():
                self.token_usage.reset()

            if self.token_usage.get_daily_usage() >= self.config.tokens_per_day:
                raise RuntimeError("Daily token budget exceeded")

            self._request_times.append(now)

    async def _retry_with_backoff(self, func, *args, **kwargs) -> LLMResponse:
        """Execute with exponential backoff retry."""
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                await self._check_rate_limit()
                response = await func(*args, **kwargs)

                # Track token usage
                usage = response.usage
                self.token_usage.add_usage(
                    usage.get("input_tokens", 0), usage.get("output_tokens", 0)
                )

                return response

            except Exception as e:
                last_error = e
                delay = self.config.retry_delay_seconds * (2**attempt)
                logger.warning(f"LLM request failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"LLM request failed after {self.config.max_retries} retries: {last_error}"
        )

    async def is_available(self) -> bool:
        """Check if the LLM provider is reachable."""
        if self._available is True:
            return True

        try:
            if self.config.provider == LLMProvider.OLLAMA:
                import aiohttp

                base_url = self.config.base_url or os.getenv(
                    "OLLAMA_BASE_URL", "http://localhost:11434"
                )
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{base_url}/api/tags", timeout=timeout
                    ) as resp:
                        if resp.status == 200:
                            self._available = True
                            return True
            elif self.config.provider == LLMProvider.ANTHROPIC:
                if self.config.api_key or os.getenv("ANTHROPIC_API_KEY"):
                    self._available = True
                    return True
            elif self.config.provider == LLMProvider.OPENAI:
                if self.config.api_key or os.getenv("OPENAI_API_KEY"):
                    self._available = True
                    return True
        except Exception as e:
            logger.warning(
                f"LLM provider {self.config.provider.value} not available: {e}"
            )

        self._available = False
        return False

    async def analyze(
        self,
        prompt: str,
        schema: Union[Dict, Type[BaseModel]],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured analysis output.

        Args:
            prompt: Analysis prompt
            schema: JSON schema or Pydantic model for structured output
            system_prompt: Optional system context

        Returns:
            Parsed JSON result, or empty dict if LLM unavailable
        """
        if not await self.is_available():
            logger.warning(
                f"LLM provider {self.config.provider.value} unavailable - returning empty analysis"
            )
            return {}

        try:
            response = await self._retry_with_backoff(
                self.provider.complete_json,
                prompt=prompt,
                schema=schema,
                system_prompt=system_prompt,
            )
            return response.parsed_json or {}
        except RuntimeError as e:
            logger.error(f"LLM analysis failed after retries: {e}")
            return {}
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return {}

    async def reason(
        self,
        context: str,
        goal: str,
        constraints: Optional[List[str]] = None,
    ) -> LLMResponse:
        """
        Generate reasoning chain for a goal.

        Args:
            context: Current state/context
            goal: What we want to achieve
            constraints: Optional constraints to consider

        Returns:
            Response with reasoning_chain populated
        """
        schema = {
            "type": "object",
            "properties": {
                "reasoning_chain": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Step-by-step reasoning",
                },
                "conclusion": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "recommended_actions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["reasoning_chain", "conclusion", "confidence"],
        }

        prompt = f"""Given the following context, provide step-by-step reasoning to achieve the goal.

Context:
{context}

Goal: {goal}

{f"Constraints: {json.dumps(constraints)}" if constraints else ""}

Provide your reasoning as a structured JSON response."""

        response = await self._retry_with_backoff(
            self.provider.complete_json,
            prompt=prompt,
            schema=schema,
            system_prompt="You are a quantitative finance expert providing structured reasoning.",
        )

        return response

    async def research(
        self,
        query: str,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Research a topic and return structured findings.

        Args:
            query: Research question
            sources: Optional list of sources to consider

        Returns:
            Structured research result
        """
        schema = {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fact": {"type": "string"},
                            "source": {"type": "string"},
                            "relevance": {"type": "number"},
                            "sentiment": {"type": "number"},
                        },
                    },
                },
                "summary": {"type": "string"},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
        }

        prompt = f"""Research and analyze the following:

Query: {query}

{f"Consider these sources: {json.dumps(sources)}" if sources else ""}

Provide structured research findings."""

        response = await self._retry_with_backoff(
            self.provider.complete_json,
            prompt=prompt,
            schema=schema,
            system_prompt="You are a financial research analyst.",
        )

        return response.parsed_json or {}

    async def decide(
        self,
        context: str,
        options: List[Dict[str, Any]],
        criteria: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Make a decision from options.

        Args:
            context: Decision context
            options: Available options
            criteria: Decision criteria

        Returns:
            Decision with reasoning
        """
        schema = {
            "type": "object",
            "properties": {
                "selected_option": {"type": "string"},
                "reasoning": {"type": "string"},
                "confidence": {"type": "number"},
                "factors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "factor": {"type": "string"},
                            "weight": {"type": "number"},
                            "impact": {"type": "string"},
                        },
                    },
                },
                "alternatives": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["selected_option", "reasoning", "confidence"],
        }

        prompt = f"""Make a decision based on the following:

Context:
{context}

Options:
{json.dumps(options, indent=2)}

{f"Decision criteria: {json.dumps(criteria)}" if criteria else ""}

Provide your decision with reasoning."""

        response = await self._retry_with_backoff(
            self.provider.complete_json,
            prompt=prompt,
            schema=schema,
            system_prompt="You are a quantitative trading strategy decision engine.",
        )

        return response.parsed_json or {}

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current token usage statistics."""
        return {
            "total_input_tokens": self.token_usage.total_input_tokens,
            "total_output_tokens": self.token_usage.total_output_tokens,
            "request_count": self.token_usage.request_count,
            "daily_budget": self.config.tokens_per_day,
            "budget_remaining": self.config.tokens_per_day
            - self.token_usage.get_daily_usage(),
        }
