"""Oracle as an MCP server. Exposes skills + memory + retrieval as MCP tools.

Run via the CLI:
    oracle mcp            # stdio transport (for Claude Desktop, Cursor, etc.)
"""

from oracle.mcp_server.server import build_server, run_stdio

__all__ = ["build_server", "run_stdio"]
