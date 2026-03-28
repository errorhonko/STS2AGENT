import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
# 引入我们写好的大脑
from agent_brain import ask_ai_for_next_move
import os
# ⚠️ 这里填入你真实的 MCP 服务器路径 (和你之前 get_state.py 里的一样)
load_dotenv()


async def main():
    print("🚀 正在启动杀戮尖塔2 Agent 总控中心...")

    # 1. 连接 MCP 服务器 (眼睛和手)
    mcp_server_path = r"C:\Users\admin\PycharmProjects\STS2AGENT\STS2MCP\mcp"

    print("⏳ 正在尝试启动并连接 STS2 MCP 服务...")

    # 1. 配置启动参数（相当于在命令行敲 uv run ...）
    server_params = StdioServerParameters(
        command="python",  # 把这里的 uv 换成 python
        args=["-m", "uv", "run", "--directory", mcp_server_path, "python", "server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ 成功连接到游戏 MCP！")

            # 2. 进入自动打牌循环
            while True:
                print("\n=======================================")
                print("👀 正在观察当前战况...")

                # 获取游戏状态 (假设你的获取状态工具叫 get_game_state，请根据实际情况修改)
                state_response = await session.call_tool("get_game_state")
                game_state_text = state_response.content[0].text

                # 防呆设计：如果没在战斗中，就不出牌了
                if "Play Phase: True" not in game_state_text:
                    print("⏸️ 当前不在出牌阶段，等待 3 秒后重试...")
                    await asyncio.sleep(3)
                    continue

                # 3. 让大脑思考
                decision = ask_ai_for_next_move(game_state_text)

                if not decision or not decision.get("cards_to_play"):
                    print("🤔 AI 决定这回合不打牌了，或者思考失败。")
                    # 这里你可以调用结束回合的工具，比如: await session.call_tool("combat_end_turn")
                    break  # 测试阶段，打完或者不打就先退出循环

                # 4. 动手出牌！
                cards_to_play = decision["cards_to_play"]

                # 🌟 核心机制：按照 hand_index 从大到小（从右到左）排序，防止卡牌错位！
                cards_to_play.sort(key=lambda x: x["hand_index"], reverse=True)

                print(f"🖐️ 准备动手打牌 (倒序防错位): {cards_to_play}")

                for card in cards_to_play:
                    idx = card["hand_index"]
                    target = card.get("target")

                    print(f"🃏 正在打出第 [{idx}] 张牌，目标: {target}...")

                    # 组装打牌参数
                    args = {"card_index": idx}
                    if target:
                        args["target"] = target

                    # 调用你刚刚找到的 combat_play_card 工具
                    await session.call_tool("combat_play_card", arguments=args)

                    # 打完一张牌稍微等一下，让游戏动画飞一会儿，也防止请求过快
                    await asyncio.sleep(1)

                print("✅ 本轮出牌执行完毕！")
                # break  # 测试阶段，我们先只让它自动打一轮就停下来


if __name__ == "__main__":
    asyncio.run(main())