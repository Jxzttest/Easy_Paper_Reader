#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TranslationModel —— 学术论文翻译模型

支持两种运行模式：
  mode=api   : 通过 OpenAI-compatible API 调用远端大语言模型（默认）
  mode=local : 加载本地部署的小型翻译模型（Helsinki-NLP/opus-mt 系列或兼容格式）

本地模型推荐：
  - opus-mt-en-zh  (英→中, Helsinki-NLP)
  - opus-mt-zh-en  (中→英, Helsinki-NLP)
  - 或任意兼容 transformers MarianMT / M2M100 格式的本地模型

配置示例（model_config.yaml）：
  translation:
    mode: api                              # api | local
    # --- api 模式 ---
    api_key: "sk-xxxx"
    base_url: "https://api.xxx.com/v1"
    model_name: "claude-opus-4-6"
    # --- local 模式 ---
    # local_model_path: "./models/opus-mt-en-zh"
    # local_model_type: "marian"          # marian | m2m100
    # use_gpu: false
"""

import re
from typing import Any, AsyncGenerator, Dict, Optional

from server.model.base_model import BaseAIModel


class TranslationModel(BaseAIModel):
    """
    学术翻译模型，支持 api 和 local 两种模式。

    api 模式：直接调用 LLM，通过 prompt 引导学术翻译。
    local 模式：加载本地 MarianMT/M2M100 翻译模型（transformers）。
    """

    def _setup(self) -> None:
        if self.mode == "local":
            self._setup_local()
        else:
            self._setup_api()

    # ── API 模式 ─────────────────────────────────────────────────────────────

    def _setup_api(self) -> None:
        from openai import AsyncOpenAI
        model_name = self.kwargs.get("model_name", "gpt-4o-mini")
        self._client = AsyncOpenAI(
            api_key=self.api_key or "EMPTY",
            base_url=self.base_url or "https://api.openai.com/v1",
        )
        self._model_name = model_name
        self.logger.info(f"API mode, model={self._model_name}")

    # ── Local 模式 ────────────────────────────────────────────────────────────

    def _setup_local(self) -> None:
        """
        加载本地翻译模型。
        支持 marian（MarianMT）和 m2m100 两种架构。
        首次调用时懒加载，避免启动时长阻塞。
        """
        self._local_initialized = False
        self._local_model_path: str = self.kwargs.get("local_model_path", "")
        self._local_model_type: str = self.kwargs.get("local_model_type", "marian")
        self._pipeline = None
        self._tokenizer = None
        self._model = None
        self.logger.info(
            f"Local mode (lazy init), path={self._local_model_path}, "
            f"type={self._local_model_type}, gpu={self.use_gpu}"
        )

    def _ensure_local_model(self) -> None:
        if self._local_initialized:
            return
        import torch
        device = 0 if (self.use_gpu and torch.cuda.is_available()) else -1

        if self._local_model_type == "marian":
            from transformers import MarianMTModel, MarianTokenizer
            self._tokenizer = MarianTokenizer.from_pretrained(self._local_model_path)
            self._model = MarianMTModel.from_pretrained(self._local_model_path)
            if device >= 0:
                self._model = self._model.cuda()
        elif self._local_model_type == "m2m100":
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
            self._tokenizer = M2M100Tokenizer.from_pretrained(self._local_model_path)
            self._model = M2M100ForConditionalGeneration.from_pretrained(self._local_model_path)
            if device >= 0:
                self._model = self._model.cuda()
            # m2m100 需要设置源/目标语言，默认英→中，在 invoke 时覆盖
            self._tokenizer.src_lang = self.kwargs.get("src_lang", "en")
            self._tgt_lang = self.kwargs.get("tgt_lang", "zh")
        else:
            raise ValueError(f"Unsupported local_model_type: {self._local_model_type}")

        self._local_initialized = True
        self.logger.info("Local translation model loaded successfully")

    # ── 公共接口 ──────────────────────────────────────────────────────────────

    async def async_invoke(self, text: str, target_lang: str = "auto") -> str:
        """
        翻译文本。

        Args:
            text:        待翻译的文本（中文或英文）
            target_lang: "zh"（译为中文）| "en"（译为英文）| "auto"（自动检测）

        Returns:
            翻译结果字符串
        """
        if not text or not text.strip():
            return ""

        resolved_lang = self._detect_target_lang(text, target_lang)

        if self.mode == "local":
            return await self._local_translate(text, resolved_lang)
        return await self._api_translate(text, resolved_lang)

    async def async_stream(self, text: str, target_lang: str = "auto") -> AsyncGenerator[str, None]:
        """
        流式翻译（api 模式支持流；local 模式退化为非流式）。
        """
        if not text or not text.strip():
            return

        resolved_lang = self._detect_target_lang(text, target_lang)

        if self.mode == "local":
            result = await self._local_translate(text, resolved_lang)
            yield result
            return

        async for chunk in self._api_translate_stream(text, resolved_lang):
            yield chunk

    # ── API 翻译 ──────────────────────────────────────────────────────────────

    async def _api_translate(self, text: str, target_lang: str) -> str:
        lang_name = "中文" if target_lang == "zh" else "English"
        system_prompt = (
            "你是一位专业的学术翻译专家，擅长中英文学术论文互译。\n"
            "要求：\n"
            "1. 仅输出译文，不要解释或添加额外内容\n"
            "2. 保持学术严谨性，专业术语翻译准确\n"
            "3. 保持原文段落和换行格式"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请将以下内容翻译为{lang_name}：\n\n{text}"},
        ]
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            temperature=0.1,
            max_tokens=4096,
        )
        return response.choices[0].message.content or ""

    async def _api_translate_stream(self, text: str, target_lang: str) -> AsyncGenerator[str, None]:
        lang_name = "中文" if target_lang == "zh" else "English"
        system_prompt = (
            "你是一位专业的学术翻译专家，擅长中英文学术论文互译。\n"
            "要求：\n"
            "1. 仅输出译文，不要解释或添加额外内容\n"
            "2. 保持学术严谨性，专业术语翻译准确\n"
            "3. 保持原文段落和换行格式"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请将以下内容翻译为{lang_name}：\n\n{text}"},
        ]
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            temperature=0.1,
            max_tokens=4096,
            stream=True,
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ── Local 翻译 ────────────────────────────────────────────────────────────

    async def _local_translate(self, text: str, target_lang: str) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        # 本地模型推理是同步阻塞操作，放到线程池执行
        return await loop.run_in_executor(None, self._sync_local_translate, text, target_lang)

    def _sync_local_translate(self, text: str, target_lang: str) -> str:
        self._ensure_local_model()
        import torch

        if self._local_model_type == "marian":
            inputs = self._tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
            if self.use_gpu and torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            translated = self._model.generate(**inputs)
            return self._tokenizer.decode(translated[0], skip_special_tokens=True)

        elif self._local_model_type == "m2m100":
            # m2m100 通过 src_lang / forced_bos_token_id 控制语言方向
            src_lang = "zh" if target_lang == "en" else "en"
            self._tokenizer.src_lang = src_lang
            inputs = self._tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
            if self.use_gpu and torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            tgt_lang_id = self._tokenizer.get_lang_id(target_lang)
            translated = self._model.generate(**inputs, forced_bos_token_id=tgt_lang_id)
            return self._tokenizer.decode(translated[0], skip_special_tokens=True)

        return text

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_target_lang(text: str, hint: str) -> str:
        """根据 hint 或自动检测决定目标语言。"""
        if hint in ("zh", "en"):
            return hint
        # 简单启发：CJK 字符占比 > 20% 则判定为中文，翻成英文
        cjk = len(re.findall(r'[一-鿿㐀-䶿]', text))
        ratio = cjk / max(len(text), 1)
        return "en" if ratio > 0.2 else "zh"


# ── 工厂函数（供 API 层直接使用）────────────────────────────────────────────

_instance: Optional[TranslationModel] = None


def get_translation_model() -> TranslationModel:
    """返回全局单例 TranslationModel，读取 model_config.yaml 中的 translation 配置。"""
    global _instance
    if _instance is not None:
        return _instance

    from server.config.config_loader import get_config
    cfg = get_config().get("translation", {})

    config: Dict[str, Any] = {
        "name": "translation_model",
        "type": "translation",
        "mode": cfg.get("mode", "api"),
        "provider": cfg.get("provider", "openai-compatible"),
        "api_key": cfg.get("api_key"),
        "base_url": cfg.get("base_url"),
        "kwargs": {
            "model_name": cfg.get("model_name", "gpt-4o-mini"),
            "local_model_path": cfg.get("local_model_path", ""),
            "local_model_type": cfg.get("local_model_type", "marian"),
            "src_lang": cfg.get("src_lang", "en"),
            "tgt_lang": cfg.get("tgt_lang", "zh"),
        },
        "use_gpu": cfg.get("use_gpu", False),
    }
    _instance = TranslationModel(config)
    return _instance
