"""RDS for MySQL Upgrade Assistant — MCP Server.

Exposes upgrade workflow tools (discover / precheck / create-green / monitor /
switchover / validate / batch / params / cleanup) to MCP clients such as
Claude Desktop or Cursor over stdio transport.
"""

from mcp.server.fastmcp import FastMCP
from rds_upgrade_mcp.tools import register_tools

mcp = FastMCP("rds-mysql-upgrade")
register_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="stdio")
