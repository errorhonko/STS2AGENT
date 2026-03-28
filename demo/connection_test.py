import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_connection():
    # ⚠️ 请把这里改成你解压 STS2_MCP 的真实目录！
    # 注意：Windows 路径建议用正斜杠 "/"，或者在前面加 r，比如 r"C:\xxx\STS2_MCP\mcp"
    mcp_server_path = r"C:\Users\admin\PycharmProjects\STS2AGENT\STS2MCP\mcp"

    print("⏳ 正在尝试启动并连接 STS2 MCP 服务...")

    # 1. 配置启动参数（相当于在命令行敲 uv run ...）
    server_params = StdioServerParameters(
        command="python",  # 把这里的 uv 换成 python
        args=["-m", "uv", "run", "--directory", mcp_server_path, "python", "server.py"],
    )

    try:
        # 2. 建立标准输入输出流的连接
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # 3. 初始化协议握手
                await session.initialize()
                print("✅ 握手成功！已连接到《杀戮尖塔2》！\n")

                # 4. 核心测试：向游戏索要它支持的“技能清单”
                print("🔍 正在拉取游戏支持的指令列表...")
                tools_response = await session.list_tools()

                print("\n" + "=" * 40)
                print("🎮 游戏提供的可用工具 (Tools):")
                print("=" * 40)
                for tool in tools_response.tools:
                    print(f"🔹 【{tool.name}】")
                    print(f"   说明: {tool.description}")
                    print("-" * 40)
                state_response = await session.call_tool("get_game_state")
                game_state_text = state_response.content[0].text
                print(game_state_text)

    except Exception as e:
        print(f"\n❌ 连接失败！报错信息如下：\n{e}")
        print("💡 检查清单：\n1. 游戏是否已启动且开启了 Mod？\n2. 路径是否完全正确？\n3. uv 是否已正确安装？")


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(test_connection())