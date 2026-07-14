"""
Hermes Remote Agent Server

FastAPI + WebSocket Hub + MCP Server 的集成入口。

启动方式:
  python main.py
  # 或通过 systemd: systemctl start hermes-agent-server

环境变量:
  AGENT_AUTH_TOKEN    预共享认证密钥 (必填)
  AGENT_PORT          HTTP/WS 监听端口 (默认 8085)
  AGENT_HOST          绑定地址 (默认 127.0.0.1)
  AGENT_LOG_LEVEL     日志级别 (默认 INFO)
"""

from __future__ import annotations

import os
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket

from db import DB
from ws_hub import Hub
from mcp_tools import mcp, bind


# ── 配置 ──

TOKEN = os.getenv("AGENT_AUTH_TOKEN", "")
PORT = int(os.getenv("AGENT_PORT", "8085"))
HOST = os.getenv("AGENT_HOST", "127.0.0.1")
LOG_LEVEL = os.getenv("AGENT_LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("server")

if not TOKEN:
    logger.fatal("AGENT_AUTH_TOKEN not set! 请设置环境变量 AGENT_AUTH_TOKEN")
    sys.exit(1)

# ── 初始化组件 ──

db = DB()
hub = Hub(db, token=TOKEN)
bind(hub, db)

# ── 生命周期 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Server 启停时的操作。"""
    logger.info(f"Starting Agent Server on {HOST}:{PORT} ...")
    db.mark_all_offline()
    await hub.start_heartbeat()
    yield
    logger.info("Shutting down Agent Server ...")
    db.mark_all_offline()

app = FastAPI(title="Hermes Remote Agent Server", lifespan=lifespan)


# ── WebSocket 路由 ──

@app.websocket("/ws")
async def agent_ws(ws: WebSocket):
    """Agent 连接入口。"""
    await hub.handle(ws)


# ── 健康检查 ──

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_online": hub.online_count,
        "agents_registered": len(db.list_agents()),
    }


# ── MCP 挂载 ──

# FastMCP + FastAPI 集成：将 MCP 的 Streamable HTTP 协议挂载到 /mcp 路径
mcp_app = mcp.streamable_http_app()
app.mount("/mcp", mcp_app)


# ── 入口 ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
