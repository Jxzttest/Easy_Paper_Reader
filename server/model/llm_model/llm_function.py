#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import AsyncGenerator, List, Dict
from openai import AsyncOpenAI, RateLimitError, APIError
from server.config.config_loader import get_config
from server.utils.logger import logger


class LLMManager:
    """
    通过 OpenAI-compatible API 调用 LLM。
    支持普通调用和流式调用。单例模式。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _init_client(self):
        if self._initialized:
            return
        cfg = get_config().get("llm", {})
        self.model_name = cfg.get("model_name", "gpt-4o")
        self.temperature = cfg.get("temperature", 0.7)
        self.max_tokens = cfg.get("max_tokens", 4096)
        self._client = AsyncOpenAI(
            api_key=cfg.get("api_key") or "EMPTY",
            base_url=cfg.get("base_url") or "https://api.openai.com/v1",
        )
        self._initialized = True
        logger.info(f"[LLMManager] model={self.model_name}")

    async def invoke(
        self,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        self._init_client()
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )
            return response.choices[0].message.content
        except RateLimitError as e:
            logger.error(f"[LLMManager] rate limit: {e}")
            raise
        except APIError as e:
            logger.error(f"[LLMManager] API error: {e}")
            raise

    async def stream(
        self,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
    ) -> AsyncGenerator[str, None]:
        self._init_client()
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except RateLimitError as e:
            logger.error(f"[LLMManager] stream rate limit: {e}")
            yield "[ERROR: 请求过于频繁，请稍后再试]"
        except APIError as e:
            logger.error(f"[LLMManager] stream API error: {e}")
            yield f"[ERROR: {str(e)}]"
        except Exception as e:
            logger.error(f"[LLMManager] stream error: {e}")
            yield f"[ERROR: 生成中断 - {str(e)}]"
