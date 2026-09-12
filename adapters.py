"""
API adapters for each bot type.
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
        if resp.status_code >= 400:
            print(f"ANTHROPIC ERROR {resp.status_code}: {resp.text}", flush=True)
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

    print(f"XAI REQUEST: key_present={bool(XAI_API_KEY)} model={model}", flush=True)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(XAI_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            print(f"XAI ERROR {resp.status_code}: {resp.text}", flush=True)
            resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
