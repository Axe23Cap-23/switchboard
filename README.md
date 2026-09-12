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

Custom GPT Actions are no longer available on personal ChatGPT accounts.
Instead, this connects via MCP:

1. In ChatGPT, go to **Settings → Apps & Connectors** (or **Plugins**,
   depending on your account) and turn on **Developer Mode** if prompted.
2. Click **Add custom connector**.
3. Name it "Switchboard" and paste this URL:
   `https://your-server.onrender.com/mcp`
4. Connect — no authentication needed for this basic setup.
5. In a chat, enable the connector from the tools/plus menu, then ask
   ChatGPT to use it, e.g. "use the switchboard connector to ask grok_bot_a
   to summarize today's tech news."

ChatGPT will call the `send_message` tool with `to` and `content`, get the
result back, and can relay it to you in the conversation.

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
