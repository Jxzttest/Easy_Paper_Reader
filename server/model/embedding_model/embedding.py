#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from openai import AsyncOpenAI
from server.config.config_loader import get_config
from server.utils.logger import logger


class EmbeddingManager:
    """
    通过 OpenAI-compatible API 获取文本向量。
    单例模式，在 get_embedding() 时懒初始化客户端。
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
        cfg = get_config().get("embedding", {})
        self.model_name = cfg.get("model_name", "text-embedding-3-small")
        self.dimensions = cfg.get("dimensions", 1536)
        self._client = AsyncOpenAI(
            api_key=cfg.get("api_key") or "EMPTY",
            base_url=cfg.get("base_url") or "https://api.openai.com/v1",
        )
        self._initialized = True
        logger.info(f"[EmbeddingManager] model={self.model_name}, dims={self.dimensions}")

    async def get_embedding(self, text: str) -> List[float]:
        self._init_client()
        if not text or not text.strip():
            return [0.0] * self.dimensions
        try:
            response = await self._client.embeddings.create(
                input=text,
                model=self.model_name,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"[EmbeddingManager] get_embedding failed: {e}")
            raise

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量获取向量，减少 API 调用次数。"""
        self._init_client()
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(
                input=texts,
                model=self.model_name,
            )
            # API 返回顺序与输入一致
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"[EmbeddingManager] get_embeddings_batch failed: {e}")
            raise
