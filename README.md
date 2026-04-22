# Easy Paper Reader

> 面向学术研究者的 AI 论文阅读助手，基于多 Agent 协同架构，支持上传 PDF、智能问答、深度检索与引用追踪。

---

## 功能概览

### 论文管理
- **PDF 上传与解析**：支持拖拽上传，自动解析文本块并构建向量索引（支持 PyMuPDF 和 PaddleOCR 两种解析模式）
- **论文库**：列出全部已上传论文，显示解析状态（等待中 / 解析中 / 已就绪 / 失败），支持按标题搜索
- **元数据管理**：自动提取标题、作者、摘要等信息并持久化存储
- **论文删除**：删除论文元数据及对应向量数据，支持一键清理

### PDF 阅读体验（新版）
- **原生文本渲染**：基于 `react-pdf-highlighter-extended`（PDF.js），替代原来的 iframe 嵌入方案
- **文本高亮**：选中任意文字后弹出操作菜单，支持黄色/绿色/蓝色高亮标注；按住 `Alt` 键可框选区域高亮
- **即时翻译**：选中文字后点击「翻译」，调用后端翻译接口自动检测中英文并互译，结果浮窗展示
- **联动问 AI**：选中文字后点击「问 AI」，自动填充至对话框

### 智能问答（RAG + Multi-Agent）
- **SSE 流式对话**：实时推送 Agent 规划、执行、检查、最终回答，体验流畅
- **多 Agent 协同**：
  - `SupervisorAgent`：意图识别与执行计划规划，区分「即时对话」和「后台任务」，支持重规划（最多重试 2 次）
  - `RAGAgent`：基于论文内容的检索增强回答，自动根据检索质量升级为深度检索（DeepSearch）
  - `WritingAgent`：学术写作辅助，润色与摘要生成
  - `TranslationAgent`：学术中英互译
  - `CheckAgent`：评估回答质量，不合格时触发重规划
- **快捷提问**：一键发送「总结这篇论文」「核心创新点是什么」「解释实验方法」「有哪些局限性」
- **会话历史**：自动保存对话记录，支持多会话管理（新建 / 切换 / 重命名 / 删除）

### 后台任务（对话驱动，用户确认执行）

用户在对话中下达复杂指令时，系统自动识别是否属于「后台任务」并请求用户确认，确认后才真正执行。

**什么会被识别为后台任务？**（满足以下任一条件）
- 需要跨论文、联网或外部数据检索（如：「找同领域最新 5 篇论文」）
- 执行时间较长，不适合同步等待（如：「根据 xxx 观点生成一个完整段落」）
- 具有周期性触发需求（如：「每周日帮我收集相关最新论文」）

**什么不是后台任务？**（直接即时回答）
- 「这篇论文的核心观点是什么？」
- 「数据库里还有哪篇是这个方向的？」
- 「这篇论文影响因子是多少？」

**任务流程**：
1. 用户在对话框输入指令
2. AI 识别为后台任务 → 弹出确认卡片，显示任务描述（定时任务额外显示 cron 周期）
3. 用户点击「确认执行」→ 后端创建任务，对话显示 task_id 或 job_id
4. 用户点击「取消」→ 任务被丢弃，不执行
5. 即时任务：通过 `GET /tasks/{task_id}` 查询进度
6. 定时任务：持久化到 SQLite，服务重启后自动恢复，通过 `DELETE /tasks/confirm/{token}` 可取消

### 引用追踪
- **即时引用检索**：对指定论文立即执行引用检索，异步后台运行
- **定时引用任务**：注册 cron 定时检索（daily / weekly / 每 6 小时 / 自定义 cron 表达式）
- **任务管理**：查询、触发、取消定时任务

### 翻译服务
- **即时翻译接口**：`POST /translate/text`，自动检测中英文并互译
- **流式翻译接口**：`POST /translate/stream`，SSE 格式逐步输出，适合长段落
- **双模式支持**：
  - `mode: api`（默认）：复用 LLM API，通过 prompt 引导学术翻译
  - `mode: local`：加载本地 MarianMT / M2M100 翻译模型（需手动下载并配置路径）

---

## 技术架构

### 后端（FastAPI + Python）

```
server/
├── service_start.py          # FastAPI 应用入口，含 CORS 和 lifespan 管理
├── agent/                    # 多 Agent 系统
│   ├── orchestrator.py       # Agent 编排引擎（SSE 流式事件推送 + confirm 事件）
│   ├── supervisor_agent.py   # 意图识别与计划生成（含后台任务判断）
│   ├── rag_agent.py          # 检索增强回答
│   ├── writing_agent.py      # 学术写作
│   ├── translation_agent.py  # 翻译
│   └── check_agent.py        # 质量检查与重规划触发
├── rag/                      # 检索增强生成
│   ├── rag_engine.py         # RAG 引擎（SimpleRAG / DeepSearchRAG 自动切换）
│   ├── deepsearch_rag.py     # 深度检索
│   └── parser/               # PDF 解析（PyMuPDF / PaddleOCR）
├── chat/                     # 对话接口（SSE 流式推送）
├── translate/                # 翻译 API（/translate/text + /translate/stream）
├── task/                     # 异步任务队列 + cron 调度器
│   ├── task_manager.py       # 即时后台任务队列（多步骤 + 断点恢复）
│   ├── scheduler.py          # cron 定时调度器（citation_check / agent_periodic）
│   ├── task_api.py           # 任务 API（含 confirm/reject 接口）
│   └── task_executor.py      # 任务执行器（对话确认后的实际调度入口）
├── db/                       # 数据层（SQLite / ChromaDB / Elasticsearch / PostgreSQL）
│   ├── sqlite_function/      # 论文元数据、会话、消息（默认）
│   ├── chroma_function/      # 向量存储（论文 Embeddings）
│   ├── elasticsearch_function/ # 对话历史、Agent 执行记录
│   └── postgresql_function/  # 用户数据（可选）
├── model/                    # 模型封装
│   ├── llm_model/            # LLM 调用
│   ├── embedding_model/      # Embedding 生成
│   ├── ranker_model/         # Reranker
│   ├── ocr_model/            # PaddleOCR
│   └── translation_model/    # 翻译模型（API + 本地双模式）
└── config/                   # YAML 配置（数据库、模型、Agent）
```

### SSE 事件类型（`/chat/send`）

| 事件 | 触发时机 | 数据字段 |
|------|----------|----------|
| `plan` | Supervisor 规划完成 | `intent`, `plan` |
| `confirm` | 识别到后台任务，等待用户确认 | `token`, `task_type`, `task_desc`, `cron_expr`, `message` |
| `agent` | 子 Agent 开始执行 | `name`, `status` |
| `result` | 子 Agent 执行完成 | `name`, `summary` |
| `check` | CheckAgent 评估结果 | `passed`, `score`, `issue` |
| `replan` | 触发重规划 | `new_plan`, `retry` |
| `answer` | 最终回答 | `content`, `sources` |
| `error` | 执行异常 | `message` |

### API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/papers/upload` | 上传 PDF，返回 task_id |
| `GET`  | `/papers/list` | 列出论文 |
| `GET`  | `/papers/{uuid}` | 获取论文元数据 |
| `DELETE` | `/papers/{uuid}` | 删除论文 |
| `GET`  | `/tasks/list` | 获取任务列表 |
| `GET`  | `/tasks/{task_id}` | 查询任务进度 |
| `POST` | `/tasks/{task_id}/cancel` | 取消任务 |
| `POST` | `/tasks/{task_id}/retry` | 断点重试任务 |
| `POST` | `/tasks/confirm/{token}` | **用户确认执行后台任务** |
| `DELETE` | `/tasks/confirm/{token}` | **用户拒绝执行后台任务** |
| `POST` | `/chat/send` | SSE 流式对话 |
| `POST` | `/chat/session/new` | 新建会话 |
| `GET`  | `/chat/session/list` | 获取会话列表 |
| `GET`  | `/chat/session/{id}` | 获取会话消息历史 |
| `DELETE` | `/chat/session/{id}` | 删除会话 |
| `PATCH` | `/chat/session/{id}/title` | 修改会话标题 |
| `POST` | `/translate/text` | 即时文本翻译 |
| `POST` | `/translate/stream` | SSE 流式翻译 |
| `POST` | `/citation/run/{uuid}` | 立即执行引用检索 |
| `POST` | `/citation/schedule` | 注册定时引用检索 |
| `DELETE` | `/citation/schedule/{job_id}` | 取消定时任务 |
| `GET`  | `/citation/schedule/list` | 查询定时任务列表 |

### 前端（React + Vite + Tailwind CSS）

```
web/src/
├── App.jsx          # 路由（Dashboard / Reader）
├── api.js           # 后端 API 封装（含 SSE 流式读取、confirm/reject 接口）
├── pages/
│   ├── Dashboard.jsx  # 论文库主页（上传、列表、搜索）
│   └── Reader.jsx     # 论文阅读 + AI 对话页（含 confirm 事件处理）
└── components/
    ├── PdfViewer.jsx  # PDF 查看器（高亮 + 翻译 + 问 AI）
    └── Toast.jsx      # 全局通知组件
```

---

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+

### 后端启动

```bash
pip install -r requirements.txt
cp .env.example .env   # 配置 LLM API Key、数据库等
python -m server.service_start
# 或
uvicorn server.service_start:app --host 0.0.0.0 --port 8800 --reload
```

### 前端启动

```bash
cd web
npm install
npm run dev
# 访问 http://localhost:5173
```

### 本地翻译模型（可选）

若希望使用本地小模型替代 LLM API 进行翻译，可下载 Helsinki-NLP 的 MarianMT 模型：

```bash
pip install transformers sentencepiece torch
python -c "
from transformers import MarianMTModel, MarianTokenizer
# 英→中
MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-en-zh').save_pretrained('./models/opus-mt-en-zh')
MarianMTModel.from_pretrained('Helsinki-NLP/opus-mt-en-zh').save_pretrained('./models/opus-mt-en-zh')
"
```

然后修改 `server/config/model_config.yaml`：
```yaml
translation:
  mode: local
  local_model_path: "./models/opus-mt-en-zh"
  local_model_type: marian
  use_gpu: false
```

### Docker 启动（可选）

```bash
cd docker
cp .env.example .env
docker-compose up -d
```

---

## 数据存储

| 存储 | 用途 |
|------|------|
| SQLite | 论文元数据、会话记录、消息历史、任务状态、定时任务（默认，零配置） |
| ChromaDB | 论文向量索引（Embedding 检索） |
| Elasticsearch | 对话历史、Agent 执行日志（可选） |
| PostgreSQL | 用户数据（可选，生产推荐） |
| Redis | 对话上下文缓存（可选） |

---

## License

MIT
