
"""Hermes Remote Agent Server - FastAPI + WebSocket Hub"""

from __future__ import annotations
import os, sys, logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from db import DB
from ws_hub import Hub
from mcp_tools import mcp, bind

if len(sys.argv) < 2:
    print("Usage: python3 main.py <auth>", file=sys.stderr)
    sys.exit(1)
T = sys.argv[1]

WS_PORT = int(os.environ.get("AGENT_WS_PORT", "8085"))
HOST = os.environ.get("AGENT_HOST", "127.0.0.1")
LOG_LEVEL = os.environ.get("AGENT_LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("server")

db = DB()
hub = Hub(db, token=T)
bind(hub, db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"WS Server on {HOST}:{WS_PORT}")
    db.mark_all_offline()
    await hub.start_heartbeat()
    yield
    db.mark_all_offline()


app = FastAPI(title="Hermes Remote Agent", lifespan=lifespan)


@app.websocket("/ws")
async def agent_ws(ws: WebSocket):
    await hub.handle(ws)


@app.get("/health")
async def health():
    return {"status": "ok", "agents_online": hub.online_count,
            "agents_registered": len(db.list_agents())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=WS_PORT, log_level=LOG_LEVEL.lower())
