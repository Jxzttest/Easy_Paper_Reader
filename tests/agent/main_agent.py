import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# 配置中加入 knowledge_server
CONFIG_PATH = "config/agent.yaml" 

async def main():
    app = MCPApp(name="AcademicApp", settings=CONFIG_PATH)
    
    async with app.run():
        # 定义 Orchestrator
        orchestrator = Agent(
            name="Orchestrator",
            instruction="""
            你是一个学术助手。
            
            【能力使用指南】
            1. **获取信息**: 在做任何分析前，先查看 papers 的基本信息。
               - 使用 Resource `paper://{paper_id}/metadata` 获取标题作者。
               
            2. **回答问题**:
               - 如果用户问具体文本细节 -> `search_paper_content`
               - 如果用户想看图/架构 -> `search_paper_images` (非常重要：这会返回图片路径)
               - 如果用户问代码实现 -> `search_paper_code`
            
            3. **处理图片**:
               - 当 `search_paper_images` 返回图片路径时，请明确告诉用户你找到了图片，并根据返回的 '图注/OCR内容' 进行解释。
            """,
            server_names=["knowledge_server"] # 对应上面的 server
        )

        async with orchestrator:
            llm = await orchestrator.attach_llm(OpenAIAugmentedLLM)
            
            # 假设我们已知 paper_id (实际场景通过 search 工具获取)
            target_paper_id = "uuid_1234_5678" 

            print(f"--- 场景 1: 直接读取 Resource (不消耗 Search Token) ---")
            # Agent 会尝试解析 URI 资源
            # 注意：在 mcp-agent 框架中，通常需要在 prompt 里引导它去 read_resource，
            # 或者在这里我们模拟 User 发送了一个包含 resource 的 prompt
            task1 = f"请帮我读取 paper://{target_paper_id}/metadata 的内容并告诉我这篇文章的作者是谁？"
            resp1 = await llm.generate_str(task1)
            print(f"Agent: {resp1}\n")

            print(f"--- 场景 2: 图片跨模态检索 ---")
            task2 = f"这篇文章({target_paper_id})里有一张关于 Transformer 架构的图，帮我找出来并解释一下。"
            resp2 = await llm.generate_str(task2)
            print(f"Agent: {resp2}\n")

            print(f"--- 场景 3: 代码检索 ---")
            task3 = f"帮我找找这篇文章({target_paper_id})里有没有计算 Attention 的伪代码？"
            resp3 = await llm.generate_str(task3)
            print(f"Agent: {resp3}\n")

if __name__ == "__main__":
    asyncio.run(main())