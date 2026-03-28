import asyncio
from mcp_client import MCPClient
from llm_engine import  LLM

async def main():
    mcp_client=MCPClient()
    agent=LLM(mcp_client)
    await mcp_client.connect_and_run(agent.start_thinking_loop)


if __name__ == "__main__":
    # 启动总调度
    asyncio.run(main())