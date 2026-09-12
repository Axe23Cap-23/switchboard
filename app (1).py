"""
Switchboard server — REST API + dashboard.

The MCP connector (mcp_server.py) is mounted at /mcp and shares all its
routing logic with this file via core.py.

Run with:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...
    export XAI_API_KEY=...
    uvicorn app:app --reload --port 8000
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import core
from mcp_server import mcp

app = FastAPI(title="ChatGPT / Claude / Grok switchboard")

# Mount the MCP connector ChatGPT's Plugins/Connectors will talk to
app.mount("/mcp", mcp.streamable_http_app())


class IncomingMessage(BaseModel):
    to: str
    content: str


@app.post("/message")
async def receive_message(msg: IncomingMessage):
    try:
        return await core.handle_message(msg.to, msg.content)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/tasks")
async def list_tasks():
    top_level = [t for t in core.TASKS.values() if t["parent_id"] is None]
    top_level.sort(key=lambda t: t["created_at"], reverse=True)

    def expand(t):
        return {**t, "children": [expand(core.TASKS[c]) for c in t["children"]]}

    return [expand(t) for t in top_level]


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    with open("dashboard.html") as f:
        return f.read()
