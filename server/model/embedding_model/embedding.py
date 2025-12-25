import numpy as np
from typing import List

class EmbeddingManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingManager, cls).__new__(cls)
            # self.model = SentenceTransformer('all-MiniLM-L6-v2') # 示例
        return cls._instance

    async def get_embedding(self, text: str) -> List[float]:
        """
        生成文本向量。
        这里使用随机向量作为占位符 (维度 768)。
        """
        # 模拟延时
        # await asyncio.sleep(0.01)
        
        # 真实场景示例:
        # return self.model.encode(text).tolist()
        
        return np.random.rand(768).tolist()