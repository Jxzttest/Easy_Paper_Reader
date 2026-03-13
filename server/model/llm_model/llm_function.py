# models/llm_model.py

from typing import AsyncGenerator
from openai import AsyncOpenAI
from server.model.base_model import BaseAIModel
from openai import RateLimitError, APIError

class LLMModel(BaseAIModel):
    def _setup(self) -> None:
        self.model_name = self.kwargs.get("model_name")
        self.temperature = self.kwargs.get("temperature", 0.7)
        
        if self.mode == "api" or self.provider == "vllm":
            # 无论远端 OpenAI 还是本地 vLLM，都可以使用 OpenAI API 标准接口
            self.client = AsyncOpenAI(
                api_key=self.api_key or "EMPTY",
                base_url=self.base_url
            )
        else:
            # 此处可以拓展使用 transformers 本地加载
            pass

    async def async_invoke(self, messages: list, **override_kwargs) -> str:
        temp = override_kwargs.get("temperature", self.temperature)
        
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temp
        )
        return response.choices[0].message.content
    
    async def async_stream(
        self, 
        messages: list, 
        **override_kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式调用 - 逐字返回生成内容
        
        Yields:
            str: 每次生成的文本片段（可能为空字符串）
        """
        temp = override_kwargs.get("temperature", self.temperature)
        collected_content = []
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temp,
                stream=True,
                stream_options={"include_usage": True}  # 可选：包含 usage 信息
            )
            
            async for chunk in response:
                choice = chunk.choices[0] if chunk.choices else None
                
                # 处理内容生成
                if choice and choice.delta:
                    content = choice.delta.content
                    
                    # 只 yield 有实际内容的片段
                    if content:
                        collected_content.append(content)
                        yield content
                    
                    # 检查是否收到角色信息
                    if choice.delta.role:
                        self.logger.debug(f"Stream started with role: {choice.delta.role}")
                
                # 检测流结束信号
                if choice and choice.finish_reason:
                    self.logger.debug(f"Stream finished: {choice.finish_reason}")
                    # 可选：yield 结束标记或处理 usage
                    if chunk.usage:
                        self.logger.info(f"Token usage: {chunk.usage}")
                    break
                    
        except RateLimitError as e:
            self.logger.error(f"速率限制: {e}")
            yield "[ERROR: 请求过于频繁，请稍后再试]"
        except APIError as e:
            self.logger.error(f"API错误: {e}")
            yield f"[ERROR: {str(e)}]"
        except Exception as e:
            self.logger.error(f"流式生成异常: {e}")
            yield f"[ERROR: 生成中断 - {str(e)}]"