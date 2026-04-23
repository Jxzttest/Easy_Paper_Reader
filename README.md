# Easy Paper Reader

> 面向学术研究者的 AI 论文阅读助手，基于多 Agent 协同架构，支持 PDF 上传、智能问答、文本高亮翻译、后台任务（即时 / 定时）、引用追踪，以及可扩展的 Skill 插件系统。

---

## 功能概览

### 论文管理
- **PDF 上传与解析**：拖拽上传，自动解析文本块并构建向量索引（支持 PyMuPDF 和 PaddleOCR 两种模式）
- **论文库**：列出全部已上传论文，显示解析状态（等待中 / 解析中 / 已就绪 / 失败），支持按标题搜索
- **元数据管理**：自动提取标题、作者、摘要并持久化
- **论文删除**：清理元数据及对应向量数据

### PDF 阅读体验
- **原生文本渲染**：基于 `react-pdf-highlighter-extended`（PDF.js），告别 iframe 嵌入，文字可选中
- **文本高亮**：选中文字后弹出操作菜单，支持黄 / 绿 / 蓝三色高亮；按住 `Alt` 可框选区域高亮
- **即时翻译**：选中文字 → 点击「翻译」→ 浮窗展示结果，自动检测中英文互译
- **联动问 AI**：选中文字 → 点击「问 AI」→ 自动填充至对话框

### 智能问答（RAG + Multi-Agent）
- **SSE 流式对话**：实时推送 Agent 规划、执行、检查、最终回答
- **多 Agent 协同**：

| Agent | 职责 |
|---|---|
| `SupervisorAgent` | 意图识别与执行计划规划；区分「即时对话」和「后台任务」；支持重规划（最多重试 2 次） |
| `RAGAgent` | 基于论文内容的检索增强回答，自动升级为深度检索（DeepSearch） |
| `WritingAgent` | 学术写作辅助（创新点梳理 / 草稿 / 润色 / 通用问答）|
| `TranslationAgent` | 中英学术互译，附术语对照表 |
| `CheckAgent` | 评估回答质量（score < 0.75 时触发重规划）|

- **四层智能记忆**（见下文）：每轮对话自动加载上下文，历史对话超过阈值时自动压缩为摘要
- **快捷提问**：「总结这篇论文」「核心创新点是什么」「解释实验方法」「有哪些局限性」等一键发送
- **会话历史**：多会话管理（新建 / 切换 / 重命名 / 删除），重启后历史完整恢复

### 四层智能记忆系统

每个会话维护四层持久化记忆块（存储于 SQLite `memory_blocks` 表），按优先级组装为 LLM 上下文：

| 层级 | 内容 | 保留策略 | 优先级 |
|---|---|---|---|
| **System** | 角色定义、能力说明、行为准则 | 永久保留，绝不裁剪 | 🔴 最高 |
| **User Intent** | 用户当前任务意图、最新明确指令 | 永久保留，每轮更新 | 🔴 最高 |
| **Working Memory** | RAG 检索结果、Agent 执行输出、论文摘要 | 动态保留，超出 30,000 token 时驱逐最旧块 | 🟡 高 |
| **History** | 多轮对话记录 | 超过 12 轮时自动调用 LLM 压缩为摘要 | 🟢 中 |

所有子 Agent 均通过 `ContextBuilder` 统一组装上下文，`AgentBase._invoke_with_context()` 一键携带四层记忆调用 LLM。

### 后台任务（对话驱动，用户确认执行）

用户在对话中下达复杂指令时，系统自动识别是否属于「后台任务」并请求确认，确认后才真正执行。

**识别为后台任务的条件**（满足任一）：
- 需要跨论文、联网或外部数据检索（如：「找同领域最新 5 篇论文」）
- 执行耗时较长，不适合同步等待（如：「根据 xxx 观点生成完整段落」）
- 具有周期性触发需求（如：「每周日帮我收集最新相关论文」）

**不是后台任务的例子**（直接即时回答）：
- 「这篇论文的核心观点是什么？」
- 「数据库里还有哪篇是这个方向的？」
- 「这篇论文的影响因子是多少？」

**执行流程**：
1. 用户对话框输入指令
2. AI 识别为后台任务 → 推送 `confirm` 事件，前端弹出确认卡片（显示任务描述 / cron 周期）
3. 用户点击「确认执行」→ 后端创建任务并执行；点击「取消」→ 任务丢弃
4. 即时任务：通过 `GET /tasks/{task_id}` 轮询进度
5. 定时任务：持久化到 SQLite，服务重启后自动恢复

### Skill 插件系统

后台任务按需调用对应的 Skill 执行，而非全部交给通用 LLM Agent，能力更专、效率更高。

**架构**：

```
用户对话 → SupervisorAgent 识别为任务
              ↓
       _select_skill()（触发词快速匹配 + LLM 兜底路由）
              ↓
    task_meta 携带 skill_name → 用户确认
              ↓
    TaskExecutor 按 skill.executor_type 分发：
      python → 动态加载 executor.py → execute(task_desc, paper_uuids)
      llm    → 将 SKILL.md 内容注入 prompt → Orchestrator + LLM Agent
      无匹配  → 降级到通用 Orchestrator
```

**内置 Skill**：

| Skill | 能力 | 触发词示例 |
|---|---|---|
| `academic-literature-search` | arXiv / PubMed 学术文献检索，返回结构化结果（标题 / 作者 / 摘要 / 链接）| 搜文献、找论文、相关论文、检索 |

**扩展新 Skill**（无需重启）：
1. 在 `server/skills/` 下新建子目录
2. 创建 `SKILL.md`（含 YAML frontmatter：`name / description / triggers / executor`）
3. 若 `executor: python`，创建 `executor.py` 并实现 `async def execute(task_desc, paper_uuids, **kwargs)`
4. 调用 `POST /skills/reload` 热重载

### 引用追踪
- **即时检索**：对指定论文立即执行引用检索，异步后台运行
- **定时检索**：注册 cron 定时任务（daily / weekly / 每 6 小时 / 自定义表达式）
- **任务管理**：查询 / 触发 / 取消定时任务

### 翻译服务
- **即时翻译**：`POST /translate/text`，自动检测中英文互译
- **流式翻译**：`POST /translate/stream`，SSE 格式逐步输出
- **双模式**：
  - `mode: api`（默认）：复用 LLM API，学术翻译质量高
  - `mode: local`：加载本地 MarianMT / M2M100 小模型（离线可用）

---

## 技术架构

### 后端（FastAPI + Python）

```
server/
├── service_start.py             # FastAPI 入口（CORS、lifespan、路由注册、skill 初始化）
├── agent/                       # 多 Agent 系统
│   ├── orchestrator.py          # Agent 编排引擎（SSE 流式事件 + confirm 事件）
│   ├── supervisor_agent.py      # 意图识别、计划生成、后台任务判断、Skill 路由
│   ├── rag_agent.py             # 检索增强回答（结果写入 Working Memory 层）
│   ├── writing_agent.py         # 学术写作（携带四层上下文）
│   ├── translation_agent.py     # 中英互译（携带四层上下文）
│   ├── check_agent.py           # 质量检查与重规划触发
│   ├── base.py                  # AgentContext（集成 MemoryManager）+ AgentBase
│   └── memory/                  # 四层智能记忆模块
│       ├── memory_manager.py    # 记忆读写 / 历史压缩 / Working 层驱逐
│       └── context_builder.py   # 将四层记忆组装为 LLM messages 列表
├── rag/                         # 检索增强生成
│   ├── rag_engine.py            # RAG 引擎（SimpleRAG / DeepSearchRAG 自动切换）
│   └── parser/                  # PDF 解析（PyMuPDF / PaddleOCR）
├── chat/                        # 对话接口（SSE 流式推送 + MemoryManager 集成）
│   ├── chat_api.py              # POST /chat/send，每轮初始化四层记忆
│   └── context_manager.py      # 向后兼容入口（重导出 memory 模块）
├── translate/                   # 翻译 API
├── skills/                      # Skill 插件系统
│   ├── skill_registry.py        # 扫描 skills/ 目录，加载 SKILL.md 元信息
│   ├── skill_api.py             # GET /skills/list、GET /skills/{name}、POST /skills/reload
│   └── academic-literature-search/
│       ├── SKILL.md             # Skill 描述（frontmatter：name/triggers/executor）
│       └── executor.py          # arXiv 检索执行器（stdlib，零外部依赖）
├── task/                        # 异步任务队列 + cron 调度器
│   ├── task_manager.py          # 即时后台任务队列（多步骤 + 断点恢复）
│   ├── scheduler.py             # cron 定时调度器（支持 skill_name 路由）
│   ├── task_api.py              # 任务 API（confirm / reject / 查询 / 取消）
│   └── task_executor.py         # 任务执行器（skill python → LLM Agent 降级路由）
├── db/                          # 数据层
│   ├── sqlite_function/         # 论文元数据、会话、消息、任务、memory_blocks
│   ├── chroma_function/         # 论文向量索引（Embedding 检索）
│   └── db_factory.py            # 数据库连接工厂
├── model/                       # 模型封装
│   ├── llm_model/               # LLM 调用
│   ├── embedding_model/         # Embedding 生成
│   ├── ranker_model/            # Reranker
│   ├── ocr_model/               # PaddleOCR
│   └── translation_model/       # 翻译模型（API + 本地双模式）
└── config/                      # YAML 配置
```

### 数据库表结构（SQLite）

| 表 | 用途 |
|---|---|
| `paper_metadata` | 论文元数据（标题 / 作者 / 摘要 / 文件路径 / 解析状态）|
| `conversations` | 会话记录（session_id / paper_uuid / 标题）|
| `messages` | 原始对话消息（用于前端历史展示）|
| `memory_blocks` | **四层智能记忆块**（layer / priority / content / token_estimate）|
| `tasks` | 异步任务状态（多步骤 + 断点恢复）|
| `scheduled_jobs` | cron 定时任务（含 skill_name，重启后自动恢复）|

### SSE 事件类型（`POST /chat/send`）

| 事件 | 触发时机 | 数据字段 |
|---|---|---|
| `plan` | Supervisor 规划完成 | `intent`, `plan` |
| `confirm` | 识别到后台任务，等待用户确认 | `token`, `task_type`, `task_desc`, `cron_expr`, `message` |
| `agent` | 子 Agent 开始执行 | `name`, `status` |
| `result` | 子 Agent 执行完成 | `name`, `summary` |
| `check` | CheckAgent 评估结果 | `passed`, `score`, `issue` |
| `replan` | 触发重规划 | `new_plan`, `retry` |
| `answer` | 最终回答 | `content`, `sources` |
| `done` | 流结束（finally 块触发）| — |
| `error` | 执行异常 | `message` |

### API 端点

| 方法 | 路径 | 描述 |
|---|---|---|
| `POST` | `/papers/upload` | 上传 PDF，返回 task_id |
| `GET` | `/papers/list` | 列出论文 |
| `GET` | `/papers/{uuid}` | 获取论文元数据 |
| `DELETE` | `/papers/{uuid}` | 删除论文 |
| `POST` | `/chat/send` | SSE 流式对话（集成四层记忆）|
| `POST` | `/chat/session/new` | 新建会话 |
| `GET` | `/chat/session/list` | 获取会话列表 |
| `GET` | `/chat/session/{id}` | 获取会话消息历史 |
| `DELETE` | `/chat/session/{id}` | 删除会话（含四层记忆）|
| `PATCH` | `/chat/session/{id}/title` | 修改会话标题 |
| `GET` | `/tasks/list` | 获取任务列表 |
| `GET` | `/tasks/{task_id}` | 查询任务进度 |
| `POST` | `/tasks/{task_id}/cancel` | 取消任务 |
| `POST` | `/tasks/{task_id}/retry` | 断点重试 |
| `POST` | `/tasks/confirm/{token}` | 用户确认执行后台任务 |
| `DELETE` | `/tasks/confirm/{token}` | 用户拒绝后台任务 |
| `GET` | `/skills/list` | 列出所有已注册 Skill |
| `GET` | `/skills/{name}` | 获取 Skill 详情（含 SKILL.md）|
| `POST` | `/skills/reload` | 热重载 Skill 列表（无需重启）|
| `POST` | `/skills/{name}/run` | 直接测试执行 Skill（开发用）|
| `POST` | `/translate/text` | 即时文本翻译 |
| `POST` | `/translate/stream` | SSE 流式翻译 |
| `POST` | `/citation/run/{uuid}` | 立即执行引用检索 |
| `POST` | `/citation/schedule` | 注册定时引用检索 |
| `DELETE` | `/citation/schedule/{job_id}` | 取消定时任务 |
| `GET` | `/citation/schedule/list` | 查询定时任务列表 |

### 前端（React + Vite + Tailwind CSS）

```
web/src/
├── App.jsx            # 路由（Dashboard / Reader）
├── api.js             # 后端 API 封装（SSE 读取、confirm/reject）
├── pages/
│   ├── Dashboard.jsx  # 论文库主页（上传、列表、搜索）
│   └── Reader.jsx     # 论文阅读 + AI 对话（confirm 事件处理）
└── components/
    ├── PdfViewer.jsx  # PDF 渲染（高亮 / 翻译 / 问 AI 浮层）
    └── Toast.jsx      # 全局通知
```

---

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+

### 后端启动

```bash
pip install -r requirements.txt
cp .env.example .env   # 配置 LLM API Key 等
python -m server.service_start
# 或
uvicorn server.service_start:app --host 0.0.0.0 --port 8800 --reload
```

服务启动后自动完成：
- SQLite 数据库初始化（含 `memory_blocks` 表）
- Skill 插件扫描（`server/skills/` 目录）
- 定时任务从数据库恢复

### 前端启动

```bash
cd web
npm install
npm run dev
# 访问 http://localhost:5173
```

### 本地翻译模型（可选）

```bash
pip install transformers sentencepiece torch
python -c "
from transformers import MarianMTModel, MarianTokenizer
MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-en-zh').save_pretrained('./models/opus-mt-en-zh')
MarianMTModel.from_pretrained('Helsinki-NLP/opus-mt-en-zh').save_pretrained('./models/opus-mt-en-zh')
"
```

修改 `server/config/model_config.yaml`：
```yaml
translation:
  mode: local
  local_model_path: "./models/opus-mt-en-zh"
  local_model_type: marian
  use_gpu: false
```

### Docker（可选）

```bash
cd docker
cp .env.example .env
docker-compose up -d
```

---

## 数据存储

| 存储 | 用途 |
|---|---|
| **SQLite**（默认，零配置）| 论文元数据、会话、消息、**四层记忆块**、任务状态、定时任务 |
| **ChromaDB** | 论文向量索引（Embedding 检索）|
| Elasticsearch | 对话历史、Agent 执行日志（可选）|
| PostgreSQL | 用户数据（可选，生产推荐）|

---

## License

MIT
