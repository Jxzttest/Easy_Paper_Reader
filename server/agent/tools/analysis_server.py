import os
from typing import List
from mcp.server.fastmcp import FastMCP
from openai import AsyncOpenAI

# 引入你的数据库工厂
from server.db.db_factory import DBFactory

mcp = FastMCP("AcademicAnalysis")

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

@mcp.tool()
async def explain_paper_summary(paper_id: str) -> str:
    """
    (工具 1, 5) 读取论文的摘要、引言和结论，生成全文概括和创新点总结。
    """
    es = DBFactory.get_es_paper_service()
    # 策略：只检索 Abstract, Introduction, Conclusion 类型的 chunk
    # 或者检索 content_type="text" 的前几段和后几段
    chunks = await es.retrieve_by_types(paper_id, ["text"], limit=10) 
    
    context = "\n".join([c['content'] for c in chunks])
    
    prompt = "请详细总结这篇文章的主要内容，并列出其核心创新点。"
    return await _internal_llm_process(prompt, context)

@mcp.tool()
async def explain_code_snippet(paper_id: str) -> str:
    """
    (工具 2) 提取论文中的代码段或伪代码进行解释。
    """
    es = DBFactory.get_es_paper_service()
    # 检索 content_type = 'code'
    chunks = await es.retrieve_by_types(paper_id, ["code"], limit=5)
    
    if not chunks:
        return "该论文未检测到明显的代码段。"

    context = "\n".join([c['content'] for c in chunks])
    prompt = "请解释这些代码片段的主要逻辑和功能。"
    return await _internal_llm_process(prompt, context)

@mcp.tool()
async def explain_structure_figure(paper_id: str, query: str = "structure diagram") -> str:
    """
    (工具 3) 寻找并解释论文中的结构图/架构图。
    Args:
        query: 用户关于图的描述，如"Transformer架构图"
    """
    es = DBFactory.get_es_paper_service()
    # 1. 向量检索，限制 content_type='figure'
    results = await es.vector_search(paper_id, query, filter_type="figure", limit=1)
    
    if not results:
        return "未找到相关的结构图。"
    
    img_data = results[0]
    img_path = img_data.get('image_path')
    ocr_caption = img_data.get('content') # OCR识别出的图注或图内文字
    
    # 2. 多模态调用 (如果有 image_path)
    # 这里演示逻辑：如果有图，应该把图发给 Vision 模型。
    # 为了简化，这里假设 _internal_vision_llm_process 存在
    # response = await _internal_vision_llm_process(img_path, f"请结合图注 '{ocr_caption}' 解释这张结构图的含义。")
    
    return f"[系统提示：已找到图片 {img_path}]。图注内容为：{ocr_caption}。请告知用户图片已找到，并根据图注解释：这张图展示了..."

@mcp.tool()
async def compare_papers_innovation(paper_id_list: List[str]) -> str:
    """
    (工具 4, 6) 对比两篇或多篇论文的创新点差异。
    """
    es = DBFactory.get_es_paper_service()
    combined_context = ""
    
    for pid in paper_id_list:
        # 获取每篇论文的摘要/元数据
        chunks = await es.retrieve_by_types(pid, ["text"], limit=3) # 假设前3块是摘要
        text = "\n".join([c['content'] for c in chunks])
        combined_context += f"--- Paper ID: {pid} ---\n{text}\n\n"
    
    prompt = "请对比上述几篇论文，总结它们各自的创新点，并分析它们之间的异同。"
    return await _internal_llm_process(prompt, combined_context)

@mcp.tool()
async def critique_user_idea(user_idea: str, reference_paper_ids: List[str]) -> str:
    """
    (工具 8) 基于给定的参考论文，评估用户的创新点，并提出修改建议。
    """
    es = DBFactory.get_es_paper_service()
    ref_context = ""
    for pid in reference_paper_ids:
        # 检索相关性最高的片段来佐证
        chunks = await es.vector_search(pid, user_idea, limit=3)
        text = "\n".join([c['content'] for c in chunks])
        ref_context += f"--- Reference ({pid}) ---\n{text}\n"
        
    prompt = f"用户的创新点是：'{user_idea}'。\n请结合参考资料，分析该创新点的新颖性，是否已被覆盖，以及改进建议。"
    return await _internal_llm_process(prompt, ref_context)

if __name__ == "__main__":
    mcp.run()