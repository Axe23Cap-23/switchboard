"""
MCP connector for the switchboard.

This is what ChatGPT talks to when you add it as a custom connector under
Settings > Connectors > Add custom connector (Developer Mode must be on).
It exposes one tool, send_message, that routes to claude_bot or grok_bot_a
using the exact same logic as the REST API in app.py.
"""
from mcp.server.fastmcp import FastMCP

import core

mcp = FastMCP("switchboard", stateless_http=True)


@mcp.tool()
async def send_message(to: str, content: str) -> str:
    """Send a task to the switchboard.

    Args:
        to: Which bot should handle this — either "claude_bot" or "grok_bot_a".
            grok_bot_a can delegate pieces of the task to its own worker bots
            and will report back a combined result.
        content: The task or question to send.
    """
    try:
        result = await core.handle_message(to, content)
    except ValueError as e:
        return f"Error: {e}"
    return result["result"] or "(no output)"
