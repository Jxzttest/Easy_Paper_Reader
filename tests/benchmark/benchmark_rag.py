# 文件位置: tests/benchmark_rag.py

import asyncio
import random
import uuid
import time
import numpy as np
from typing import List

# 调整 path 以便能导入 src
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server.db.db_factory import DBFactory
from server.agent.rag.rag_engine import RAGEngine
from server.utils.logger import logger

# --- 模拟数据生成器 ---
class MockDataGenerator:
    def __init__(self):
        # 准备一些具有特定关键词的主题，以便测试 BM25
        self.topics = [
            ("Quantum Computing", "qubit superposition entanglement"),
            ("Deep Learning", "neural network backpropagation transformer"),
            ("Climate Change", "carbon emissions global warming sea level"),
            ("Renaissance Art", "da vinci michelangelo fresco perspective"),
            ("Database Systems", "acid transaction sql nosql indexing")
        ]

    def generate_chunks(self, count=100) -> List[dict]:
        chunks = []
        for i in range(count):
            topic_name, keywords = random.choice(self.topics)
            # 生成一段包含关键词的随机文本
            # 为了测试，我们在文本中加入唯一的 UUID，作为“精准答案”的标记
            unique_id = str(uuid.uuid4())[:8]
            
            content = f"This is a paper about {topic_name}. Key concepts include {keywords}. " \
                      f"Specific detail identifier: {unique_id}. " \
                      f"Random padding data {random.randint(1000, 9999)}."
            
            # 模拟向量 (实际应调用 Embedding 模型，这里为了 Benchmark 速度使用随机)
            # 维度必须与 ES mapping 一致 (768)
            vector = np.random.rand(768).tolist()
            
            chunks.append({
                "paper_id": f"paper_{random.randint(1, 10)}",
                "chunk_id": f"chunk_{i}_{unique_id}",
                "content": content,
                "vector": vector,
                "title": f"Research on {topic_name}",
                "unique_token": unique_id  # 用于验证
            })
        return chunks

async def run_benchmark():
    logger.info("Starting RAG Benchmark...")
    
    # 1. 初始化
    await DBFactory.init_all()
    rag = RAGEngine()
    es = DBFactory.get_es_paper_service()
    generator = MockDataGenerator()
    
    # 2. 准备数据
    DATA_SIZE = 50
    logger.info(f"Generating {DATA_SIZE} mock chunks...")
    dataset = generator.generate_chunks(DATA_SIZE)
    
    # 3. 写入 ES (为了不污染真实库，实际测试建议用专门的 index，这里简化直接写入)
    logger.info("Indexing data to Elasticsearch...")
    tasks = []
    for data in dataset:
        task = es.add_paper_chunk(
            paper_id=data['paper_id'],
            chunk_id=data['chunk_id'],
            content=data['content'],
            vector=data['vector'],
            title=data['title'],
            metadata={"is_test": True} # 标记为测试数据
        )
        tasks.append(task)
    await asyncio.gather(*tasks)
    
    # 等待 ES 刷新索引
    logger.info("Waiting for ES refresh...")
    await asyncio.sleep(2)
    
    # 4. 执行测试
    # 测试策略：使用数据中的 unique_token 或关键词构建 Query
    # 如果 vector 是随机的，纯 Vector Search 效果会很差，所以这里主要测试 Pipeline 的连通性和 BM25 的贡献
    # *注意*：为了让随机 Vector 也能测出 Hybrid 的效果，我们在 Query 中使用完全匹配的关键词
    
    logger.info("Running queries...")
    
    top_k = 5
    hits = 0
    total_latency = 0
    test_queries_count = 10 # 随机选 10 个进行测试
    
    test_samples = random.sample(dataset, test_queries_count)
    
    for sample in test_samples:
        # 构造 Query：包含原文中的 unique identifier，确保 BM25 能强匹配
        query = f"Tell me about {sample['unique_token']} and {sample['title']}"
        
        # 暂时 Hack：因为 Mock 数据的 Vector 是随机生成的，Query Vector 也是随机的
        # 它们之间没有语义关系。为了让测试代码不报错且逻辑跑通，我们手动注入一个
        # "作弊" 的行为：在真实场景下，Query Vector 和 Doc Vector 会在空间上接近。
        # 这里的 Benchmark 主要是测代码逻辑连通性和延迟。
        
        start = time.time()
        # 这里的 embedding_manager.get_embedding 也是返回随机向量
        results = await rag.search(query, top_k=top_k, alpha=0.5)
        latency = (time.time() - start) * 1000
        total_latency += latency
        
        # 验证结果
        # 检查检索结果的 chunk_id 列表中是否包含 sample 的 chunk_id
        found = False
        for res in results:
            if res['chunk_id'] == sample['chunk_id']:
                found = True
                break
        
        if found:
            hits += 1
        
        logger.info(f"Query: ...{sample['unique_token']}... | Latency: {latency:.2f}ms | Hit: {found}")

    # 5. 输出报告
    print("\n" + "="*30)
    print(f"Benchmark Report (N={test_queries_count})")
    print("="*30)
    print(f"Total Chunks: {DATA_SIZE}")
    print(f"Recall@{top_k}: {hits}/{test_queries_count} ({(hits/test_queries_count)*100:.1f}%)")
    print(f"Avg Latency: {total_latency/test_queries_count:.2f} ms")
    print("="*30 + "\n")

    # 6. 清理数据 (可选，这里仅做演示，生产环境请谨慎)
    # await es.delete_by_query(...) 
    
    await DBFactory.close_all()

if __name__ == "__main__":
    # Windows 下可能需要设置 loop policy
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(run_benchmark())