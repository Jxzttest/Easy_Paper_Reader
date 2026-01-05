#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
from typing import List, Dict, Optional
from server.db.elasticsearch_function.es_base import ElasticsearchBase
from server.utils.logger import logger

class ESPaperStore(ElasticsearchBase):
    storage_name = "es_paper"

    def __init__(self):
        super().__init__()
        self.paper_index = self.config_dict.get('paper_index', 'paper_chunk_store')
        
        # 默认 Paper Mapping，如果配置文件没有则使用此默认值
        default_mapping = {
            "mappings": {
                "properties": {
                    "paper_id": {"type": "keyword"},
                    "chunk_id": {"type": "keyword"},
                    "content": {"type": "text", "analyzer": "standard"}, # 文本内容 / 表格HTML / 图片OCR文字
                    "content_type": {"type": "keyword"}, # 枚举：text, table, figure, equation, code
                    "vector": {
                        "type": "dense_vector", 
                        "dims": 768, 
                        "index": True, 
                        "similarity": "cosine"
                    },
                    "image_path": {"type": "keyword"}, # 如果是图片/表格，存储裁剪后的图片路径
                    "page_num": {"type": "integer"},
                    "create_time": {"type": "date"}
                }
            }
        }
        self.paper_body = self.config_dict['body'].get('paper_body', default_mapping)

    async def initialize(self):
        await self._create_index_if_not_exists(self.paper_index, self.paper_body)

    async def add_paper_chunk(self, 
                              paper_id: str, 
                              chunk_id: str, 
                              content: str, 
                              vector: List[float], 
                              metadata: Dict = None):
        doc = {
            "paper_id": paper_id,
            "chunk_id": chunk_id,
            "content": content,
            "vector": vector,
            "metadata": metadata or {},
            "create_time": datetime.datetime.now().isoformat()
        }
        await self.es_connect.index(index=self.paper_index, document=doc)

    async def search_similar(self, vector: List[float], top_k: int = 3):
        query = {
            "knn": {
                "field": "vector",
                "query_vector": vector,
                "k": top_k,
                "num_candidates": 100
            },
            "_source": ["paper_id", "content", "metadata"]
        }
        res = await self.es_connect.search(index=self.paper_index, body=query)
        return [hit['_source'] for hit in res['hits']['hits']]
    
    async def search_hybrid(self, 
                            text_query: str, 
                            vector: List[float], 
                            top_k: int = 5, 
                            alpha: float = 0.5):
        """
        混合检索：Vector (KNN) + BM25 (Text Match)
        :param alpha: 权重因子 (0.0 - 1.0)。
                      1.0 表示纯向量搜索，0.0 表示纯文本搜索。
                      ES 的分数体系不同，这里通过 boost 来简单模拟权重平衡。
        """
        # 注意：ES 的 _score 对于向量通常在 [0, 1] 或 [0, 2] 之间，但 BM25 可以很高。
        # 在 ES 8.x 中，推荐使用 knn 参数与 query 参数并行的方式。
        
        # 向量部分的 boost
        knn_boost = alpha
        # 文本部分的 boost
        query_boost = 1.0 - alpha
        
        body = {
            # 1. 向量检索部分
            "knn": {
                "field": "vector",
                "query_vector": vector,
                "k": top_k,
                "num_candidates": 100,
                "boost": knn_boost
            },
            # 2. 关键词检索部分 (BM25)
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "content": {
                                    "query": text_query,
                                    "boost": query_boost
                                }
                            }
                        }
                    ]
                }
            },
            # 返回字段
            "_source": ["paper_id", "chunk_id", "content", "title", "page_num", "metadata", "score"],
            "size": top_k
        }

        try:
            # 使用 search 接口，ES 8 会自动进行混合评分
            response = await self.es_connect.search(index=self.paper_index, body=body)
            hits = response['hits']['hits']
            
            # 整理返回结果
            results = []
            for hit in hits:
                item = hit['_source']
                item['_score'] = hit['_score'] # 保留分数以便调试
                results.append(item)
            return results
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []