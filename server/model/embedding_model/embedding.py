import numpy as np
from typing import List
from openai import AsyncOpenAI
from transformers import AutoTokenizer, AutoModel
from server.model.base_model import BaseAIModel

class EmbeddingModel(BaseAIModel):
    def _setup(self) -> None:
        # 这里可以根据配置加载不同的 embedding 模型
        self.model_name = self.kwargs.get("model_name", "default_embedding_model")
        if self.mode == "api":
            # 初始化远程 API 客户端（示例）
            self.client = AsyncOpenAI(
                api_key=self.api_key or "EMPTY",
                base_url=self.base_url
            )
        else:
            self.model_path = self.kwargs.get("model_path", "sentence-transformers/all-MiniLM-L6-v2")
            self.device = "cuda" if self.kwargs.get("device", False) else "cpu"
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True).to(self.device)
            self.client = AutoModel.from_pretrained(self.model_path, trust_remote_code=True).to(self.device)
        

    async def async_invoke(self, text: str) -> List[float]:
        """
        生成文本向量。
        这里使用随机向量作为占位符 (维度 1024)。
        """
        
        # return self.client.encode(text).tolist() if self.mode != "api" else np.random.rand(1024).tolist()
        
        # 模拟数据
        return np.random.rand(1024).tolist()
    
    async def async_stream(self, *args, **kwargs) -> None:
        "无调用"
        pass