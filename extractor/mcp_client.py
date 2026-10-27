"""Thin wrapper around the MCP Python SDK.

An MCP server is just a process (stdio) or URL (http) that speaks JSON-RPC.
The client does three things with it:
  1. initialize  - handshake, learn the server's capabilities
  2. tools/list  - ask which tools exist and what arguments they take
  3. tools/call  - run a tool with arguments and get content back
"""
import json
import os
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


@asynccontextmanager
async def connect(server_cfg: dict):
    """Open an initialized ClientSession for one server from config.yaml."""
    transport = server_cfg.get("transport", "stdio")

    if transport == "stdio":
        params = StdioServerParameters(
            command=server_cfg["command"],
            args=server_cfg.get("args", []),
            # The SDK only forwards a minimal environment by default.
            env={**os.environ, **server_cfg.get("env", {})},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    elif transport == "http":
        async with streamablehttp_client(
            server_cfg["url"], headers=server_cfg.get("headers", {})
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    else:
        raise ValueError(f"Unknown transport: {transport}")


async def call_tool_json(session: ClientSession, tool: str, args: dict):
    """Call a tool and return its result as Python data.

    Servers return either `structuredContent` or text blocks that usually
    hold JSON. Both cases are handled here so the sources don't care.
    """
    result = await session.call_tool(tool, args)

    if result.isError:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise RuntimeError(f"{tool} failed: {text}")

    if result.structuredContent:
        data = result.structuredContent
        # FastMCP wraps non-object return values as {"result": ...}.
        if set(data) == {"result"}:
            data = data["result"]
        return data

    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"{tool} returned non-JSON text: {text[:300]}")
