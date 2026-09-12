"""
Shared switchboard logic: bot registry, task store, and dispatch/aggregation.

Both app.py (the REST API ChatGPT's old Action-style calls would use) and
mcp_server.py (the MCP connector ChatGPT's Plugins/Connectors now use)
import from here so there's exactly one copy of the routing logic.
"""
import asyncio
import json
import time
import uuid
from typing import Optional

import adapters

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
# In-memory task store
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
# Dispatch functions
# ---------------------------------------------------------------------------
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
        update_task(task_id, output=raw, status="done")
        return

    if decision.get("action") != "delegate" or depth >= MAX_DELEGATION_DEPTH:
        update_task(task_id, output=decision.get("result", raw), status="done")
        return

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


async def handle_message(to: str, content: str) -> dict:
    """Shared entrypoint used by both the REST API and the MCP tool."""
    if to not in DISPATCH_TABLE:
        raise ValueError(f"'{to}' is not a valid target. Use claude_bot or grok_bot_a.")
    task_id = new_task(to, content)
    handler = DISPATCH_TABLE[to]
    await handler(task_id, content)
    task = TASKS[task_id]
    return {"task_id": task_id, "status": task["status"], "result": task["output"]}
