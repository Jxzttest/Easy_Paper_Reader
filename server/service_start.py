from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from server.db.db_factory import DBFactory
from server.task.task_manager import task_manager
from server.task.scheduler import scheduler
from server.rag.parser.parser_api import router as parser_router
from server.task.task_api import router as task_router
from server.chat.chat_api import router as chat_router
from server.agent.citation_api import router as citation_router
from server.chat_manager.dialogue_manager_api import router as dialogue_manager_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 启动 ──────────────────────────────────────────
    await DBFactory.init_all()
    task_manager.initialize()
    scheduler.initialize()
    await scheduler.restore_from_db()   # 恢复持久化的定时任务
    yield
    # ── 关闭 ──────────────────────────────────────────
    await scheduler.shutdown()
    await task_manager.shutdown()
    await DBFactory.close_all()


app = FastAPI(title="Easy Paper Reader", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parser_router)
app.include_router(task_router)
app.include_router(chat_router)
app.include_router(citation_router)
app.include_router(dialogue_manager_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8800)

