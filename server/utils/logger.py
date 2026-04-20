# import os
# import logging


# # 确保日志目录存在
# log_dir = os.path.join(os.path.dirname(__file__), "log")
# if not os.path.exists(log_dir):
#     os.makedirs(log_dir)

# # 配置日志
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
#     handlers=[
#         logging.FileHandler(os.path.join(log_dir, "app.log")),
#         logging.StreamHandler(),
#     ],
# )
# logger = logging.getLogger(__name__)



# tracing/logger.py
import os
import json
import time
import logging
from typing import Any, Dict
from contextvars import ContextVar
from datetime import datetime

# 全局 Trace ID 上下文变量，用于串联同一次请求的所有组件调用
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="SYSTEM")

def setup_elegant_logger(log_dir: str = "logs"):
    """配置全局日志系统，双写：控制台(简略) + 本地JSONL文件(全量结构化)"""
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"trace_{today}.jsonl")

    logger = logging.getLogger("agent_backend")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 清除默认 handler，防止重复打印
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. 控制台 Handler (人类可读的优雅输出)
    console_formatter = logging.Formatter(
        '%(asctime)s | [%(levelname)s] | Trace:%(trace_id)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    ch = logging.StreamHandler()
    ch.setFormatter(console_formatter)
    
    # 2. 文件 Handler (JSONL 格式结构化落盘)
    class JSONLFormatter(logging.Formatter):
        def format(self, record):
            log_record = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "trace_id": getattr(record, "trace_id", "SYSTEM"),
                "component_name": getattr(record, "component_name", "Unknown"),
                "component_type": getattr(record, "component_type", "Unknown"),
                "action": getattr(record, "action", "log"), # start, end, error
                "duration_ms": getattr(record, "duration_ms", None),
                "message": record.getMessage(),
                "payload": getattr(record, "payload", {}) # 存具体的输入/输出
            }
            return json.dumps(log_record, ensure_ascii=False)

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(JSONLFormatter())

    # 注入 Trace ID 的 Filter
    class TraceFilter(logging.Filter):
        def filter(self, record):
            record.trace_id = current_trace_id.get()
            return True

    logger.addFilter(TraceFilter())
    logger.addHandler(ch)
    logger.addHandler(fh)
    
    return logger

# 初始化全局 logger
agent_logger = setup_elegant_logger()

# 兼容简单调用：from server.utils.logger import logger
logger = agent_logger


class ComponentLoggerAdapter(logging.LoggerAdapter):
    """
    组件专属日志适配器
    自动为每一条中间日志注入 component_name, component_type 和 action="step"
    """
    def __init__(self, logger: logging.Logger, component_name: str, component_type: str):
        super().__init__(logger, {})
        self.component_name = component_name
        self.component_type = component_type

    def process(self, msg: str, kwargs: Dict[str, Any]):
        # 拦截所有日志调用，自动注入结构化字段到 extra 中
        extra = kwargs.get("extra", {})
        extra.update({
            "component_name": self.component_name,
            "component_type": self.component_type,
            "action": extra.get("action", "step"), # 默认动作类型为 step (中间步骤)
            "payload": extra.get("payload", {})
        })
        kwargs["extra"] = extra
        return f"[{self.component_type.upper()}] {self.component_name} | {msg}", kwargs