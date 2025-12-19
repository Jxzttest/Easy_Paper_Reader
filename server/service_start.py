from contextlib import asynccontextmanager
from fastapi import FastAPI
from server.db.db_factory import DBFactory

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 启动时初始化数据库 ---
    await DBFactory.init_all()
    yield
    # --- 关闭时清理连接 ---
    await DBFactory.close_all()

app = FastAPI(lifespan=lifespan)