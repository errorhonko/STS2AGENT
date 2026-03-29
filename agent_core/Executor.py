# agent_core/executor.py
import json
import re


class Executor:
    def __init__(self, llm_client, mcp_client, prompt_router, model_name: str, temperature: float = 0.0):
        """
        初始化执行局
        :param llm_client: OpenAI 兼容客户端
        :param mcp_client: 杀戮尖塔 MCP 客户端
        :param prompt_router: 提示词路由
        :param model_name: 模型名称 (如 "qwen3.5-9b")
        :param temperature: 强烈建议设为 0.0！执行阶段不需要任何创造力，只需要精准。
        """
        self.llm = llm_client
        self.mcp_client = mcp_client
        self.router = prompt_router
        self.model = model_name
        self.temperature = temperature

    async def execute(self, state_type: str, clean_state: str, strategy: str) -> list:
        """
        根据参谋长给出的策略，强制大模型调用工具并执行
        """
        # 1. 组装执行指令（把策略塞进 Prompt 里）
        system_prompt = self.router.get_action_prompt(state_type, strategy)

        # 2. 获取当前可用的工具集
        # TODO 进阶优化：以后可以写个 get_tools_by_type(state_type) 只传相关工具以节省 Token
        available_tools = self.mcp_client.tools
        #  准备工具列表
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            } for tool in available_tools  # 这里的 self.body 是你的 MCP 客户端
        ]
        print(f"\n🦾 [执行局] 收到战术指令，正在强制转换为机器操作...")

        # 3. 调用 LLM（核心动作）
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"当前游戏状态：\n{clean_state}\n请立即执行策略。"}
            ],
            tools=openai_tools,
            # 强制它必须调用工具，不准用普通文本回复！
            tool_choice="required",
            temperature=self.temperature
        )

        message = response.choices[0].message
        tool_invocations = self._extract_tool_calls(message)
        execution_results = await self._run_tools(tool_invocations)
        return execution_results

        # execution_results = []
        #
        # # 4. 解析并执行 Tool Calls
        # if message.tool_calls:
        #     for tool_call in message.tool_calls:
        #         func_name = tool_call.function.name
        #
        #         # 安全解析参数 (处理大模型可能返回的字符串格式)
        #         try:
        #             args = json.loads(tool_call.function.arguments)
        #         except json.JSONDecodeError:
        #             print(f"⚠️ [执行] 参数解析失败，原始参数: {tool_call.function.arguments}")
        #             args = {}
        #
        #         print(f"⚡ [执行] 扣动扳机 -> {func_name}({args})")
        #
        #         # 真正调用 MCP 客户端操作游戏
        #         try:
        #             result = await self.mcp_client.call_tool(func_name, args)
        #             execution_results.append({
        #                 "tool": func_name,
        #                 "status": "success",
        #                 "response": result
        #             })
        #             print(f"✅ [执行局] 动作完成，游戏返回: {result}")
        #         except Exception as e:
        #             error_msg = str(e)
        #             execution_results.append({
        #                 "tool": func_name,
        #                 "status": "error",
        #                 "response": error_msg
        #             })
        #             print(f"❌ [执行局] 动作报错: {error_msg}")
        # else:
        #     # 防御性编程：以防万一模型还是犯病了
        #     print(f"⚠️ [执行] 警告：模型违抗了指令，没有调用任何工具！")
        #     print(f"模型的狡辩: {message.content}")
        #
        # return execution_results

    def _extract_tool_calls(self, message) -> list:
        """提取工具调用（兼容 JSON 与 Qwen XML）"""

        # 1. 标准 JSON 格式 (列表推导式，一行搞定)
        if message.tool_calls:
            return [{"name": tc.function.name, "args": json.loads(tc.function.arguments or "{}")}
                    for tc in message.tool_calls]

        # 2. Qwen XML 格式 (海象操作符 + 字典推导式，几行搞定)
        text = getattr(message, 'reasoning_content', '') or message.content or ""

        if func_match := re.search(r'<function=([^>]+)>', text):
            # 一把抓出所有的 <parameter=键>值</parameter>
            raw_args = re.findall(r'<parameter=([^>]+)>(.*?)</parameter>', text, re.DOTALL)

            # 组装字典：去空格，并且如果值是纯数字就自动转成 int
            args = {k.strip(): int(v.strip()) if v.strip().isdigit() else v.strip() for k, v in raw_args}

            print(f"⚠️ [执行] 触发 Qwen XML 解码器: {func_match.group(1).strip()}")
            return [{"name": func_match.group(1).strip(), "args": args}]

        # 3. 什么都没匹配到，返回空列表
        return []

    async def _run_tools(self, tool_invocations: list) -> list:
        """
        接收提取好的工具列表，依次传递给 MCP 客户端执行
        """
        execution_results = []

        # 如果列表是空的，说明大模型没打算操作，直接返回空结果
        if not tool_invocations:
            print(f"⚠️ [执行] 模型未发出任何有效操作指令。")
            return execution_results

        # 遍历所有需要执行的动作
        for invocation in tool_invocations:
            func_name = invocation["name"]
            args = invocation["args"]

            print(f"⚡ [执行] 正在向游戏客户端发送指令 -> {func_name}({args})")

            # 👇 这里就是你刚刚写的核心执行代码！
            try:
                # 真正调用游戏接口
                result = await self.mcp_client.call_tool(func_name, args)
                execution_results.append({
                    "tool": func_name,
                    "status": "success",
                    "response": result
                })
                print(f"✅ [执行局] 动作完成，游戏返回: {result}")

            except Exception as e:
                # 如果游戏那边报错了（比如指定的遗物序号不存在），记录下来
                execution_results.append({
                    "tool": func_name,
                    "status": "error",
                    "response": str(e)
                })
                print(f"❌ [执行局] 动作报错: {str(e)}")

        return execution_results