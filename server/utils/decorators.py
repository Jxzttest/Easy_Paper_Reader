# tracing/decorators.py
import time
import inspect
from functools import wraps
from server.utils.logger import agent_logger

def trace_action(action_type: str):
    """
    通用追踪装饰器，自动从 self 提取 name 和 type
    支持普通 async 函数和 async generator (流式)
    """
    def decorator(func):
        # 检查是否为异步生成器 (流式)
        is_async_gen = inspect.isasyncgenfunction(func)

        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            component_name = getattr(self, "name", "Unnamed")
            component_type = getattr(self, "model_type", getattr(self, "type", "Unknown"))
            
            # 1. 记录开始
            start_time = time.time()
            agent_logger.info(
                f"[{component_type.upper()}] {component_name} invoked.",
                extra={
                    "component_name": component_name,
                    "component_type": component_type,
                    "action": "start",
                    "payload": {"args": str(args), "kwargs": str(kwargs)}
                }
            )

            try:
                # 2. 执行核心逻辑并记录结束
                if is_async_gen:
                    # ==== 流式输出处理 ====
                    full_response =[]
                    async for chunk in func(self, *args, **kwargs):
                        if chunk:
                            full_response.append(chunk)
                        yield chunk
                    
                    # 默默拼接完毕后，记一条完整日志
                    duration = round((time.time() - start_time) * 1000, 2)
                    final_text = "".join([str(c) for c in full_response])
                    agent_logger.info(
                        f"[{component_type.upper()}] {component_name} stream finished in {duration}ms.",
                        extra={
                            "component_name": component_name,
                            "component_type": component_type,
                            "action": "end",
                            "duration_ms": duration,
                            "payload": {"result": final_text}
                        }
                    )
                else:
                    # ==== 非流式普通输出处理 ====
                    result = await func(self, *args, **kwargs)
                    duration = round((time.time() - start_time) * 1000, 2)
                    agent_logger.info(
                        f"[{component_type.upper()}] {component_name} finished in {duration}ms.",
                        extra={
                            "component_name": component_name,
                            "component_type": component_type,
                            "action": "end",
                            "duration_ms": duration,
                            "payload": {"result": str(result)[:500]} # 截断超长结果
                        }
                    )
                    return result

            except Exception as e:
                # 3. 记录异常
                duration = round((time.time() - start_time) * 1000, 2)
                agent_logger.error(
                    f"[{component_type.upper()}] {component_name} FAILED: {str(e)}",
                    extra={
                        "component_name": component_name,
                        "component_type": component_type,
                        "action": "error",
                        "duration_ms": duration,
                        "payload": {"error": str(e)}
                    }
                )
                raise e

        return async_wrapper
    return decorator