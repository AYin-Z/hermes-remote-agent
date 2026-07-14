"""Hermes Remote Agent — WS + MCP on single port"""

import os, sys, logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from db import DB
from ws_hub import Hub
from mcp_tools import mcp, bind

if len(sys.argv) < 2:
    print("Usage: python3 main.py <auth_token>", file=sys.stderr)
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

# Create MCP ASGI app ONCE
MCP_APP = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Server on {HOST}:{WS_PORT}")
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


# ASGI middleware to route /mcp/* to MCP_APP
@app.middleware("http")
async def mcp_middleware(request, call_next):
    if request.url.path.startswith("/mcp"):
        from starlette.responses import Response
        scope = dict(request.scope)
        scope["path"] = "/mcp"
        scope["raw_path"] = b"/mcp"

        body = b""
        status = [200]
        headers = []

        async def recv():
            return {"type": "http.request", "body": await request.body(), "more_body": False}

        async def send(msg):
            nonlocal body
            if msg["type"] == "http.response.start":
                status[0] = msg["status"]
                headers.clear()
                for k, v in msg.get("headers", []):
                    headers.append((k.decode() if isinstance(k, bytes) else k,
                                   v.decode() if isinstance(v, bytes) else v))
            elif msg["type"] == "http.response.body":
                body += msg.get("body", b"")

        await MCP_APP(scope, recv, send)
        return Response(content=body, status_code=status[0], headers=dict(headers))

    return await call_next(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=WS_PORT, log_level=LOG_LEVEL.lower())
