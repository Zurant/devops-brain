import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化 FastAPI 实例
app = FastAPI(title="DevOps Brain API", version="0.1.0")

# 引入并注册路由
from src.api.routes import webhook, approval

app.include_router(webhook.router, prefix="/api")
app.include_router(approval.router, prefix="/api")

# 挂载静态文件目录 (前提是 static 目录必须存在)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
