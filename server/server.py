"""Hermes Remote Agent — unified WS + MCP server"""

import os, sys, logging, asyncio, threading, time
from contextlib import asynccontextmanager

if len(sys.argv) < 2:
    print("Usage: python3 server.py <auth_token>", file=sys.stderr)
    sys.exit(1)
T = sys.argv[1]

PORT = int(os.environ.get("AGENT_PORT", "8085"))
HOST = os.environ.get("AGENT_HOST", "127.0.0.1")
LOG_LEVEL = os.environ.get("AGENT_LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("server")

from db import DB
from ws_hub import Hub
from mcp_tools import mcp, bind

db = DB()
hub = Hub(db, token=T)
bind(hub, db)


# ── WS server in background thread ──

async def start_ws():
    from fastapi import FastAPI, WebSocket
    import uvicorn

    @asynccontextmanager
    async def lifespan(app):
        logger.info(f"WS on {HOST}:{PORT}")
        db.mark_all_offline()
        await hub.start_heartbeat()
        yield
        db.mark_all_offline()

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/ws")
    async def agent_ws(ws: WebSocket):
        await hub.handle(ws)

    @app.get("/health")
    async def health():
        return {"status": "ok", "agents_online": hub.online_count,
                "agents_registered": len(db.list_agents())}

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
    await uvicorn.Server(config).serve()


threading.Thread(target=lambda: asyncio.run(start_ws()), daemon=True).start()
time.sleep(2)
logger.info("Starting MCP on :8086")
mcp.run(transport="streamable-http")
