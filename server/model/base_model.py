# core/base_model.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, AsyncGenerator
from server.utils.decorators import trace_action
from server.utils.logger import agent_logger, ComponentLoggerAdapter

class BaseAIModel(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.name: str = config.get("name", "unknown_model")
        self.model_type: str = config.get("type", "unknown")
        self.mode: str = config.get("mode", "api")
        self.provider: str = config.get("provider", "unknown")
        
        self.api_key: Optional[str] = config.get("api_key")
        self.base_url: Optional[str] = config.get("base_url")
        self.kwargs: Dict[str, Any] = config.get("kwargs", {})

        self.logger = ComponentLoggerAdapter(
            logger=agent_logger,
            component_name=self.name,
            component_type=self.model_type
        )
        
        # 只保留简单的初始化，日志已经被抽取
        self._setup()

    @abstractmethod
    def _setup(self) -> None:
        pass

    # ✅ 魔法在这里：所有继承 BaseAIModel 的子类，只要调用 async_invoke，自动拥有日志！
    @trace_action("invoke")
    @abstractmethod
    async def async_invoke(self, *args, **kwargs) -> Any:
        pass

    # ✅ 流式调用也一样自动被拦截和默默拼接！
    @trace_action("stream")
    @abstractmethod
    async def async_stream(self, *args, **kwargs) -> AsyncGenerator[Any, None]:
        raise NotImplementedError(f"Model [{self.name}] does not support streaming.")