"""测试用 MCP stdio 服务器：一个 echo 工具。"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool()
def echo(text: str) -> str:
    """原样返回文本，前面加 echo:。"""
    return "echo:" + text


if __name__ == "__main__":
    mcp.run(transport="stdio")
