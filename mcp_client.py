import os
from typing import Optional, Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self, server_path: Optional[str] = None):
        self.mcp_server_path = server_path or os.getenv("STS2_MCP_PATH")
        self.session: ClientSession | None = None
        self.tools: list[Any] = []

    async def connect_and_run(self, agent_loop_func):
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "uv", "run", "--directory", self.mcp_server_path, "python", "server.py"],
        )

        print("[MCP] Starting and connecting to STS2 MCP server...")
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                print("[MCP] Connected.")
                print("[MCP] Loading tool list...")
                result = await session.list_tools()
                self.tools = result.tools
                print(f"[MCP] Loaded {len(self.tools)} tools.")
                await agent_loop_func()

    async def get_state(self, format: str = "markdown") -> str:
        if not self.session:
            raise RuntimeError("MCP session is not initialized.")

        state_response = await self.session.call_tool("get_game_state", arguments={"format": format})
        return state_response.content[0].text

    async def call_tool(self, name, arguments):
        if not self.session:
            raise RuntimeError("MCP session is not initialized.")

        print(f"[MCP] Calling tool: {name} with arguments: {arguments}")

        try:
            result = await self.session.call_tool(name, arguments=arguments)
            if hasattr(result, "content") and len(result.content) > 0:
                return result.content[0].text
            return str(result)
        except Exception as exc:
            print(f"[MCP] Tool {name} failed: {exc}")
            return f"Error: {exc}"
