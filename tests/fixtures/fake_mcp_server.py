"""Tiny offline MCP stdio server used by the transport contract tests."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("YukiFakeMCP")


@server.tool()
def echo(text: str) -> dict[str, object]:
    """Return one deterministic structured value."""

    return {"echo": text, "transport": "stdio"}


if __name__ == "__main__":
    server.run(transport="stdio")
