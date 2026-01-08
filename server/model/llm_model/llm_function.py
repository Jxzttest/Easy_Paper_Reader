from openai import AsyncOpenAI


# 这里使用一个内部的 LLM 客户端，用于工具内部的数据处理
# 这样大量的 Context 不会流转回主 Agent
client = AsyncOpenAI(api_key="...", base_url="...")

async def _internal_llm_process(prompt: str, context: str) -> str:
    """工具内部的 LLM 调用"""
    messages = [
        {"role": "system", "content": "你是一个学术专家。请根据提供的上下文回答问题。"},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {prompt}"}
    ]
    response = await client.chat.completions.create(
        model="gpt-4o", messages=messages, temperature=0.3
    )
    return response.choices[0].message.content