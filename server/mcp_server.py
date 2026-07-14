
"""MCP Server standalone entry"""

import os, sys

if len(sys.argv) < 2:
    print("Usage: python3 mcp_server.py <auth>", file=sys.stderr)
    sys.exit(1)

T = sys.argv[1]

sys.path.insert(0, os.path.dirname(__file__))

from db import DB
from ws_hub import Hub
from mcp_tools import mcp, bind

db = DB()
hub = Hub(db, token=T)
bind(hub, db)

port = int(os.getenv("AGENT_MCP_PORT", "8086"))
host = os.getenv("AGENT_HOST", "127.0.0.1")
app = mcp.streamable_http_app()

import uvicorn
uvicorn.run(app, host=host, port=port, log_level="info")
