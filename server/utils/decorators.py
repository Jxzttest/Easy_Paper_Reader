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
        is_async_gen = inspect.isasyncgenfunction(func)

        if is_async_gen:
            # ========== async generator 专用包装器 ==========
            @wraps(func)
            async def async_gen_wrapper(self, *args, **kwargs):
                component_name = getattr(self, "name", "Unnamed")
                component_type = getattr(self, "model_type", getattr(self, "type", "Unknown"))
                
                start_time = time.time()
                agent_logger.info(
                    f"[{component_type.upper()}] {component_name} stream invoked.",
                    extra={
                        "component_name": component_name,
                        "component_type": component_type,
                        "action": "start",
                        "payload": {"args": str(args), "kwargs": str(kwargs)}
                    }
                )

                try:
                    full_response = []
                    async for chunk in func(self, *args, **kwargs):
                        if chunk:
                            full_response.append(chunk)
                        yield chunk
                    
                    # 流式结束后记录日志
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
                except Exception as e:
                    duration = round((time.time() - start_time) * 1000, 2)
                    agent_logger.error(
                        f"[{component_type.upper()}] {component_name} stream FAILED: {str(e)}",
                        extra={
                            "component_name": component_name,
                            "component_type": component_type,
                            "action": "error",
                            "duration_ms": duration,
                            "payload": {"error": str(e)}
                        }
                    )
                    raise e

            return async_gen_wrapper

        else:
            # ========== 普通 async 函数专用包装器 ==========
            @wraps(func)
            async def async_func_wrapper(self, *args, **kwargs):
                component_name = getattr(self, "name", "Unnamed")
                component_type = getattr(self, "model_type", getattr(self, "type", "Unknown"))
                
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
                    result = await func(self, *args, **kwargs)
                    duration = round((time.time() - start_time) * 1000, 2)
                    agent_logger.info(
                        f"[{component_type.upper()}] {component_name} finished in {duration}ms.",
                        extra={
                            "component_name": component_name,
                            "component_type": component_type,
                            "action": "end",
                            "duration_ms": duration,
                            "payload": {"result": str(result)[:500]}
                        }
                    )
                    return result

                except Exception as e:
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

            return async_func_wrapper

    return decorator