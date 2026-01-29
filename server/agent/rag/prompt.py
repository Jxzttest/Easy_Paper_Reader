
def get_deepsearch_toc_prompt():
    sections = []

    # 添加包含系统指令的 Header
    deepsearch_toc_prompt = f"""
    你是一个高级 AI 研究助理，擅长多步骤推理

    # 当前已经搜索的内容
    {knowledge}
    # 搜索记录
    """
    sections.push("你是一个高级 AI 研究助理，擅长多步骤推理...");

    if (knowledge?.length) {
    sections.push("<knowledge>[知识条目]</knowledge>");
    }

    // 添加之前行动的上下文信息
    if (context?.length) {
    sections.push("<context>[行动历史记录]</context>");
    }

    // 添加失败的尝试和学习到的策略
    if (badContext?.length) {
    sections.push("<bad-attempts>[失败的尝试]</bad-attempts>");
    sections.push("<learned-strategy>[改进策略]</learned-strategy>");
    }

    // 根据当前状态定义可用的行动选项
    sections.push("<actions>[可用行动定义]</actions>");

    // 添加响应格式指令
    sections.push("请以有效的 JSON 格式响应，并严格匹配 JSON schema。");

    return sections.join("\n\n");
