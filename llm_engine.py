import asyncio
import json
import os
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from typing import Optional, Iterator, List, Dict, Union, Any, AsyncIterator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from enum import Enum
load_dotenv()
class ExecutionMode(Enum):
    BATCH = "batch"           # 连招模式：一口气全打出去
    SEQUENTIAL = "sequential" # 稳健模式：打一张，看一眼，再思考
class LLM:
    def __init__(
            self,
            mcp_client,

            model: Optional[str] = None,
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            mcp_server_path:Optional[str] =None,
            mode=ExecutionMode.SEQUENTIAL,

            **kwargs
    ):

        self.mode = mode
        self.mcp_client=mcp_client
        # 解析 ModelScope 的凭证
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.history = []  #  TODO 以后扩展 记忆上下文
        # 验证凭证是否存在
        if not self.api_key:
            raise ValueError("ModelScope API key not found. Please set MODELSCOPE_API_KEY environment variable.")

        # 设置默认模型和其他参数
        self.model = model or os.getenv("LLM_MODEL_ID")

        self.temperature = kwargs.get('temperature', 0.7) or os.getenv("LLM_TEMPERATURE")
        self.max_tokens = kwargs.get('max_tokens') or os.getenv("LLM_MAX_TOKENS")
        self.timeout = kwargs.get('timeout', 60) or os.getenv("LLM_TIMEOUT")

        # 使用获取的参数创建OpenAI客户端实例
        self._client = AsyncOpenAI(api_key=self.api_key,
                              base_url=self.base_url, timeout=self.timeout)


    async def start_thinking_loop(self):
        """
               核心工作循环：看状态 -> 思考 -> 下指令
        """
        print("🧠 [Agent] 意识已接入，准备开始打牌！")

        while True:
            print("\n--- 新的回合 ---")

            await self.decide_and_act()


            await asyncio.sleep(3)

    async def decide_and_act(self):
        print("🧠 正在请求大模型决策...")
        # 1. 感知：获取当前状态
        state = await self.mcp_client.get_state()
        print("\n" + "=" * 30 + " 📥 当前游戏状态 (State) " + "=" * 30)
        self.history.append({"role": "user", "content": state})
        import json
        if isinstance(state, (dict, list)):
            print(json.dumps(state, indent=2, ensure_ascii=False))
        else:
            print(state)

        print("=" * 85 + "\n")

        if len(self.history) > 3:
            # 保留第一条 System Prompt（如果有的话）
            self.history = [self.history[0]] + self.history[-9:]
        #  准备工具列表
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            } for tool in self.mcp_client.tools  # 这里的 self.body 是你的 MCP 客户端
        ]
        # 2. 决策：询问 LLM
        response = await self._client.chat.completions.create(
            model=self.model,  # 使用加载类里配置好的模型名
            messages=self.history,  # 包含之前的游戏状态和对话
            tools=openai_tools,  # 拍给 AI 的技能说明书
            tool_choice="auto",  # 让 AI 自动决定是说话还是用工具
            temperature=self.temperature,  # 冷静程度
            max_tokens=self.max_tokens  # 防止废话
        )
        print("\n🔍 原始响应报文:")
        print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))
        # 提取 AI 的回答对象
        ai_message = response.choices[0].message

        # 检查是否有工具调用请求
        tool_calls = ai_message.tool_calls

        # --- 情况 A：AI 决定使用工具（比如出牌） ---
        if tool_calls:
            print(f"🎯 AI 决定执行工具调用，共 {len(ai_message.tool_calls)} 个动作")

            # 将 AI 的意图存入历史（必须先存入 assistant 的 tool_calls，才能存 tool 的结果）
            self.history.append(ai_message)
            # 3. 执行：根据模式分配策略
            if self.mode == ExecutionMode.BATCH:
                # 【连招模式】
                for call in tool_calls:
                    await self.execute_single_call(call)
                # 全部执行完后，下一轮循环再看结果

            elif self.mode == ExecutionMode.SEQUENTIAL:
                # 【稳健模式】
                # 只执行第一个动作，剩下的丢弃，强迫下一轮重新思考
                await self.execute_single_call(tool_calls[0])
         

        # --- 情况 B：AI 只是说了段话（没有调用工具） ---
        else:
            print(f"💬 AI 回复文本: {ai_message.content}")

            # 将 AI 的对话存入历史
            self.history.append({"role": "assistant", "content": ai_message.content})

          

       

    async def execute_single_call(self, tool_call):
        """这是一个私有接口，负责处理单个工具的调用和结果反馈"""
        func_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        print(f"执行动作: {func_name} 参数: {args}")
        result = await self.mcp_client.call_tool(func_name, args)

        # 把执行结果存回历史，反馈给 AI
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": str(result)
        })