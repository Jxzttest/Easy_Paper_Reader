from contextlib import asynccontextmanager
from fastapi import FastAPI
from server.db.db_factory import DBFactory
from server.parser.parser_api import router as parser_router
from server.chat_manager.dialogue_manager_api import router as dialogue_manager_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 启动时初始化数据库 ---
    await DBFactory.init_all()
    yield
    # --- 关闭时清理连接 ---
    await DBFactory.close_all()

app = FastAPI(lifespan=lifespan)
app.include_router(parser_router)
app.include_router(dialogue_manager_router)