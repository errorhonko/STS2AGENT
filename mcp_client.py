import os
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    def __init__(self, server_path: Optional[str] = None,):
        self.mcp_server_path = server_path or os.getenv("STS2_MCP_PATH")
        self.session = None
        self.tools = []
    async def connect_and_run(self, agent_loop_func):

        server_params = StdioServerParameters(
            command="python",
            args=["-m", "uv", "run", "--directory", self.mcp_server_path, "python", "server.py"],
        )

        print("🦾 [MCP] 正在启动并连接游戏引擎...")
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                print("🦾 [MCP] 连接完毕！")
                print("📡 正在获取技能列表...")
                result = await session.list_tools()
                self.tools = result.tools

                print(f"✅ 成功加载 {len(self.tools)} 个技能")
                # 把控制权正式交给 Agent
                await agent_loop_func()
    async def get_state(self)->str:
        state_response = await self.session.call_tool("get_game_state")
        game_state_text = state_response.content[0].text
        return game_state_text

    async def call_tool(self, name, arguments):
        """
        动作执行器：真正把 LLM 的意图发送给 MCP 服务器
        """
        if not self.session:
            raise RuntimeError("🚨 错误：MCP 会话未初始化，无法执行工具！")

        print(f"🦾 [MCP 动作] 正在执行: {name}, 参数: {arguments}")

        try:
            # 这里的 call_tool 是 MCP SDK 提供的原始方法
            result = await self.session.call_tool(name, arguments=arguments)

            # 返回执行结果（通常是文本或 JSON）
            # MCP 的返回结果通常嵌套在 result.content 中
            if hasattr(result, 'content') and len(result.content) > 0:
                return result.content[0].text
            return str(result)

        except Exception as e:
            print(f"❌ 执行工具 {name} 失败: {e}")
            return f"Error: {str(e)}"

  