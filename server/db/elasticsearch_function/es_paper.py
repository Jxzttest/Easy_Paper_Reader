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
                    "content": {"type": "text", "analyzer": "standard"},
                    "vector": {
                        "type": "dense_vector", 
                        "dims": 768, 
                        "index": True, 
                        "similarity": "cosine"
                    },
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