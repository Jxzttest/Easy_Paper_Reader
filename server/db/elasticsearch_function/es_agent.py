
import datetime
import uuid
from typing import Optional, List, Dict, Any
from fastapi import HTTPException
from elasticsearch.exceptions import NotFoundError
from server.db.elasticsearch_function.es_base import ElasticsearchBase
from server.utils.logger import logger

class ESAgentStore(ElasticsearchBase):
    storage_name = "es_agent"

    def __init__(self):
        super().__init__()
        # 从配置中提取特定字段
        self.agent_body = self.config_dict['body']['agent_body']
        self.agent_index = self.config_dict['agent_index']

        default_mapping = {
            "mappings": {
                "properties": {
                    "message_id": {"type": "keyword"},
                    
                    "timestamp": {"type": "date" }
                }
            }
        }
        self.agent_body = self.config_dict['body'].get('agent_body', default_mapping)

    async def initialize(self):
        await self._create_index_if_not_exists(self.agent_index, self.agent_body)


    async def get_tool_calls_statistics(
        self,
        user_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict:
        """获取tool调用的统计信息"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"exists": {"field": "tool_calls"}}
                    ]
                }
            },
            "aggs": {
                "by_tool_name": {
                    "terms": {"field": "tool_calls.tool_name.keyword", "size": 100}
                },
                "by_status": {
                    "terms": {"field": "tool_calls.status.keyword"}
                },
                "avg_duration": {
                    "avg": {"field": "tool_calls.duration_ms"}
                },
                "total_calls": {
                    "value_count": {"field": "tool_calls.tool_call_id.keyword"}
                }
            }
        }
        
        # 添加时间范围过滤
        if start_time and end_time:
            query["query"]["bool"]["filter"] = {
                "range": {
                    "timestamp": {
                        "gte": start_time,
                        "lte": end_time
                    }
                }
            }
        
        try:
            res = await self.es_connect.search(index=self.agent_index, body=query)
            return res.get('aggregations', {})
        except Exception as e:
            logger.error(f"Get tool statistics failed: {e}")
            return {}

    async def add_tool_call_result(
        self,
        message_id: str,
        tool_call_id: str,
        tool_output: str,
        status: str = "success",
        error: Optional[str] = None,
        **kwargs
    ):
        """更新tool调用的结果"""
        try:
            # 查找消息
            search_response = await self.es_connect.search(
                index=self.agent_index,
                body={
                    "query": {
                        "term": {"message_id": message_id}
                    }
                }
            )
            
            if not search_response['hits']['hits']:
                raise ValueError(f"Message not found: {message_id}")
            
            doc = search_response['hits']['hits'][0]
            current_tool_calls = doc['_source'].get('tool_calls', [])
            
            # 更新对应的tool调用
            updated = False
            for i, tool in enumerate(current_tool_calls):
                if tool.get('tool_call_id') == tool_call_id:
                    current_tool_calls[i].update({
                        "tool_output": tool_output,
                        "status": status,
                        "tool_error": error,
                        "end_time": datetime.datetime.utcnow().isoformat(),
                        **kwargs
                    })
                    updated = True
                    break
            
            if updated:
                await self.es_connect.update(
                    index=self.messages_index,
                    id=doc['_id'],
                    body={
                        "doc": {
                            "tool_calls": current_tool_calls,
                            "status": "completed"
                        }
                    },
                    refresh=True
                )
            else:
                logger.warning(f"Tool call {tool_call_id} not found in message {message_id}")
                
        except Exception as e:
            logger.error(f"Update tool call failed: {e}")
            raise HTTPException(status_code=500, detail=f"Update tool call failed: {str(e)}")
    