# Easy Paper Reader

> 面向学术研究者的 AI 论文阅读助手，基于多 Agent 协同架构，支持上传 PDF、智能问答、深度检索与引用追踪。

---

## 功能概览

### 论文管理
- **PDF 上传与解析**：支持拖拽上传，自动解析文本块并构建向量索引（支持 PyMuPDF 和 PaddleOCR 两种解析模式）
- **论文库**：列出全部已上传论文，显示解析状态（等待中 / 解析中 / 已就绪 / 失败），支持按标题搜索
- **元数据管理**：自动提取标题、作者、摘要等信息并持久化存储
- **论文删除**：删除论文元数据及对应向量数据，支持一键清理

### 智能问答（RAG + Multi-Agent）
- **SSE 流式对话**：实时推送 Agent 规划、执行、检查、最终回答，体验流畅
- **多 Agent 协同**：
  - `SupervisorAgent`：意图识别与执行计划规划，支持重规划（最多重试 2 次）
  - `RAGAgent`：基于论文内容的检索增强回答，自动根据检索质量升级为深度检索（DeepSearch）
  - `WritingAgent`：学术写作辅助，润色与摘要生成
  - `TranslationAgent`：学术中英互译
  - `CheckAgent`：评估回答质量，不合格时触发重规划
- **快捷提问**：一键发送「总结这篇论文」「核心创新点是什么」「解释实验方法」「有哪些局限性」
- **会话历史**：自动保存对话记录，支持多会话管理（新建 / 切换 / 重命名 / 删除）

### 引用追踪
- **即时引用检索**：对指定论文立即执行引用检索，异步后台运行
- **定时引用任务**：注册 cron 定时检索（daily / weekly / 每 6 小时 / 自定义 cron 表达式）
- **任务管理**：查询、触发、取消定时任务

### 后台任务系统
- **异步任务队列**：PDF 解析、引用检索均通过 TaskManager 异步执行，支持多步骤依赖
- **任务轮询**：前端通过 `GET /tasks/{task_id}` 实时查询任务进度
- **定时调度**：基于 cron 的持久化调度器，服务重启后自动恢复任务

---

## 技术架构

### 后端（FastAPI + Python）

```
server/
├── service_start.py          # FastAPI 应用入口，含 CORS 和 lifespan 管理
├── agent/                    # 多 Agent 系统
│   ├── orchestrator.py       # Agent 编排引擎（SSE 流式事件推送）
│   ├── supervisor_agent.py   # 意图识别与计划生成
│   ├── rag_agent.py          # 检索增强回答
│   ├── writing_agent.py      # 学术写作
│   ├── translation_agent.py  # 翻译
│   └── check_agent.py        # 质量检查与重规划触发
├── rag/                      # 检索增强生成
│   ├── rag_engine.py         # RAG 引擎（SimpleRAG / DeepSearchRAG 自动切换）
│   ├── deepsearch_rag.py     # 深度检索
│   └── parser/               # PDF 解析（PyMuPDF / PaddleOCR）
├── chat/                     # 对话接口（SSE 流式推送）
├── task/                     # 异步任务队列 + cron 调度器
├── db/                       # 数据层（SQLite / ChromaDB / Elasticsearch / PostgreSQL）
│   ├── sqlite_function/      # 论文元数据、会话、消息（默认）
│   ├── chroma_function/      # 向量存储（论文 Embeddings）
│   ├── elasticsearch_function/ # 对话历史、Agent 执行记录
│   └── postgresql_function/  # 用户数据（可选）
├── model/                    # 模型封装
│   ├── llm_model/            # LLM 调用
│   ├── embedding_model/      # Embedding 生成
│   ├── ranker_model/         # Reranker
│   └── ocr_model/            # PaddleOCR
└── config/                   # YAML 配置（数据库、模型、Agent）
```

### API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/papers/upload` | 上传 PDF，返回 task_id |
| `GET`  | `/papers/list` | 列出论文 |
| `GET`  | `/papers/{uuid}` | 获取论文元数据 |
| `DELETE` | `/papers/{uuid}` | 删除论文 |
| `GET`  | `/tasks/{task_id}` | 查询任务进度 |
| `POST` | `/chat/send` | SSE 流式对话 |
| `POST` | `/chat/session/new` | 新建会话 |
| `GET`  | `/chat/session/list` | 获取会话列表 |
| `GET`  | `/chat/session/{id}` | 获取会话消息历史 |
| `DELETE` | `/chat/session/{id}` | 删除会话 |
| `PATCH` | `/chat/session/{id}/title` | 修改会话标题 |
| `POST` | `/citation/run/{uuid}` | 立即执行引用检索 |
| `POST` | `/citation/schedule` | 注册定时引用检索 |
| `DELETE` | `/citation/schedule/{job_id}` | 取消定时任务 |
| `GET`  | `/citation/schedule/list` | 查询定时任务列表 |

### 前端（React + Vite + Tailwind CSS）

```
web/src/
├── App.jsx          # 路由（Dashboard / Reader）
├── api.js           # 后端 API 封装（含 SSE 流式读取）
├── pages/
│   ├── Dashboard.jsx  # 论文库主页（上传、列表、搜索）
│   └── Reader.jsx     # 论文阅读 + AI 对话页
└── components/
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
| SQLite | 论文元数据、会话记录、消息历史（默认，零配置） |
| ChromaDB | 论文向量索引（Embedding 检索） |
| Elasticsearch | 对话历史、Agent 执行日志（可选） |
| PostgreSQL | 用户数据（可选，生产推荐） |
| Redis | 对话上下文缓存（可选） |

---

## License

MIT
