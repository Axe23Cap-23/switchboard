"""
Switchboard server.

ChatGPT sends every message here. The switchboard routes it to one of two
top-level peers: claude_bot or grok_bot_a. grok_bot_a can delegate pieces
of its task to worker bots (grok_bot_b/c/d...), waits for their results,
summarizes, and reports back. Every task (top-level and delegated) is
visible on the live dashboard at /dashboard.

Run with:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...
    export XAI_API_KEY=...
    uvicorn app:app --reload --port 8000
"""
import asyncio
import json
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import adapters

app = FastAPI(title="ChatGPT / Claude / Grok switchboard")

# ---------------------------------------------------------------------------
# Bot registry — edit this to add or remove worker bots
# ---------------------------------------------------------------------------
BOTS = {
    "claude_bot": {"kind": "claude", "model": "claude-sonnet-4-6"},
    "grok_bot_a": {
        "kind": "grok",
        "model": "grok-4",
        "role": "dispatcher",
        "children": ["grok_bot_b", "grok_bot_c", "grok_bot_d"],
    },
    "grok_bot_b": {"kind": "grok", "model": "grok-4", "role": "worker"},
    "grok_bot_c": {"kind": "grok", "model": "grok-4", "role": "worker"},
    "grok_bot_d": {"kind": "grok", "model": "grok-4", "role": "worker"},
}

# grok_bot_a can delegate one level down; workers can't delegate further.
# Raise this only if you also add depth-aware delegation logic below.
MAX_DELEGATION_DEPTH = 1

DISPATCHER_SYSTEM_PROMPT = """You are Grok bot A, a task dispatcher. You receive a task and decide:
1. Handle it yourself and respond directly, or
2. Delegate pieces of it to your worker bots: {children}

Reply with ONLY valid JSON, no other text, in one of these two shapes:

To respond directly:
{{"action": "respond", "result": "<your answer>"}}

To delegate:
{{"action": "delegate", "tasks": [{{"target": "<bot_id>", "message": "<what to ask them>"}}]}}
"""

# ---------------------------------------------------------------------------
# In-memory task store — swap for a real database before this leaves your
# laptop or runs more than one worker process.
# ---------------------------------------------------------------------------
TASKS: dict[str, dict] = {}


def new_task(bot: str, content: str, parent_id: Optional[str] = None, depth: int = 0) -> str:
    task_id = uuid.uuid4().hex[:8]
    TASKS[task_id] = {
        "id": task_id,
        "bot": bot,
        "input": content,
        "output": None,
        "status": "pending",
        "parent_id": parent_id,
        "children": [],
        "depth": depth,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    if parent_id:
        TASKS[parent_id]["children"].append(task_id)
    return task_id


def update_task(task_id: str, **fields):
    TASKS[task_id].update(fields)
    TASKS[task_id]["updated_at"] = time.time()


# ---------------------------------------------------------------------------
# Core routing
# ---------------------------------------------------------------------------
class IncomingMessage(BaseModel):
    to: str  # "claude_bot" or "grok_bot_a"
    content: str


async def run_claude(task_id: str, content: str):
    update_task(task_id, status="in_progress")
    result = await adapters.call_claude(content)
    update_task(task_id, output=result, status="done")


async def run_grok_worker(task_id: str, content: str):
    update_task(task_id, status="in_progress")
    result = await adapters.call_grok(content)
    update_task(task_id, output=result, status="done")


async def run_grok_dispatcher(task_id: str, content: str, depth: int = 0):
    update_task(task_id, status="in_progress")
    children_ids = BOTS["grok_bot_a"]["children"]
    system = DISPATCHER_SYSTEM_PROMPT.format(children=", ".join(children_ids))

    raw = await adapters.call_grok(content, system=system)
    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        # Model didn't return clean JSON — fall back to treating it as a direct answer
        update_task(task_id, output=raw, status="done")
        return

    if decision.get("action") != "delegate" or depth >= MAX_DELEGATION_DEPTH:
        update_task(task_id, output=decision.get("result", raw), status="done")
        return

    # Delegate to workers concurrently, then summarize their results
    sub_ids = []
    coros = []
    for sub in decision.get("tasks", []):
        target = sub.get("target")
        message = sub.get("message", "")
        if target not in children_ids:
            continue
        sub_id = new_task(target, message, parent_id=task_id, depth=depth + 1)
        sub_ids.append(sub_id)
        coros.append(run_grok_worker(sub_id, message))

    if not coros:
        update_task(task_id, output="No valid delegation targets returned.", status="error")
        return

    await asyncio.gather(*coros)

    summary_input = "Original task: " + content + "\n\nWorker results:\n" + "\n".join(
        f"- {TASKS[sid]['bot']}: {TASKS[sid]['output']}" for sid in sub_ids
    )
    final = await adapters.call_grok(
        summary_input,
        system="Summarize the worker results into one final answer for the original requester.",
    )
    update_task(task_id, output=final, status="done")


DISPATCH_TABLE = {
    "claude_bot": run_claude,
    "grok_bot_a": run_grok_dispatcher,
}


@app.post("/message")
async def receive_message(msg: IncomingMessage):
    if msg.to not in DISPATCH_TABLE:
        raise HTTPException(400, f"'{msg.to}' is not a valid top-level target (use claude_bot or grok_bot_a)")

    task_id = new_task(msg.to, msg.content)
    handler = DISPATCH_TABLE[msg.to]
    await handler(task_id, msg.content)  # waits so ChatGPT's action gets an immediate reply

    task = TASKS[task_id]
    return {"task_id": task_id, "status": task["status"], "result": task["output"]}


@app.get("/api/tasks")
async def list_tasks():
    top_level = [t for t in TASKS.values() if t["parent_id"] is None]
    top_level.sort(key=lambda t: t["created_at"], reverse=True)

    def expand(t):
        return {**t, "children": [expand(TASKS[c]) for c in t["children"]]}

    return [expand(t) for t in top_level]


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    with open("dashboard.html") as f:
        return f.read()
