"""
API adapters for each bot type.

Each function takes a prompt (and optional system prompt) and returns the
model's plain-text response. Set your API keys as environment variables
before running the server:

    export ANTHROPIC_API_KEY=sk-ant-...
    export XAI_API_KEY=xai-...
"""
import os
import httpx

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
XAI_URL = "https://api.x.ai/v1/chat/completions"


async def call_claude(prompt: str, system: str = "", model: str = "claude-sonnet-4-6") -> str:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []))


async def call_grok(prompt: str, system: str = "", model: str = "grok-4.6") -> str:
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "content-type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(XAI_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
