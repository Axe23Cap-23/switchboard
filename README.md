# Switchboard

Routes messages between ChatGPT, a Claude bot, and a Grok bot hierarchy.

```
ChatGPT --> switchboard --> claude_bot
                        \-> grok_bot_a --> grok_bot_b
                                       \-> grok_bot_c
                                       \-> grok_bot_d
```

`claude_bot` and `grok_bot_a` are equal peers under the switchboard.
`grok_bot_a` can delegate a task to its own worker bots, waits for their
replies, summarizes, and reports back through the switchboard to whoever
asked. Every task — top-level and delegated — shows up live on the
dashboard.

## Setup

```bash
cd switchboard
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export XAI_API_KEY=xai-...
uvicorn app:app --reload --port 8000
```

Open the dashboard: http://localhost:8000/dashboard

## Sending a task

```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"to": "grok_bot_a", "content": "Research three competitors and summarize their pricing"}'
```

or

```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"to": "claude_bot", "content": "Draft a follow-up email to the vendor"}'
```

Both return `{"task_id": ..., "status": "done", "result": "..."}` once
finished — this is the same response ChatGPT's Action will get back.

## Wiring up ChatGPT

In a Custom GPT, add an Action with an OpenAPI schema pointing at
`POST https://your-server/message`, with a `to` field the GPT can set to
`"claude_bot"` or `"grok_bot_a"`, and a `content` field for the task text.
Once connected, ChatGPT can call this action mid-conversation and get the
result back to relay to you.

## What's stubbed out, on purpose

This is a starting scaffold, not a production service:

- **In-memory task store** (`TASKS` dict in `app.py`) — restarting the
  server loses history. Swap in SQLite or Postgres once this matters.
- **No auth** on `/message` or `/dashboard` — add an API key check before
  exposing this on the public internet.
- **Synchronous dispatch** — `/message` waits for the whole chain
  (including delegated sub-tasks) before responding. Fine for a few
  worker bots; move to background jobs + polling if tasks get slow or
  numerous.
- **No retry logic** — if a worker bot's API call fails, that sub-task is
  marked `"error"` and the rest still complete.
- **Adding more worker bots**: just add entries to `BOTS` in `app.py` and
  list their IDs under `grok_bot_a`'s `"children"`.
