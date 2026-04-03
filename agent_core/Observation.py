# agent_core/observation.py

class Observation:
    def __init__(self, llm, prompt_router, model_name: str, temperature: float = 0.3):
        """
        初始化观察局
        :param llm_client:  OpenAI 兼容客户端 (比如 self._client)
        :param prompt_router:  提示词类实例
        :param model_name: 使用的模型名称
        """
        self.llm = llm
        self.router = prompt_router
        self.model = model_name
        self.temperature = temperature  # 观察阶段可以稍微给一点温度，让它思考灵活些

    def _parse_state(self, raw_state: str):
        """
        【核心降维打击】：提取状态类型
        """
        # 1. 提取 state_type (例如从 "# Game State: combat" 中提取 "combat")
        state_type = "unknown"
        first_line = raw_state.strip().split('\n')[0]
        if "Game State:" in first_line:
            state_type = first_line.split("Game State:")[1].strip().lower()

        # 2. 其余部分
        clean_state = raw_state.strip()

        return state_type, clean_state



    async def analyze(self, raw_state: str) -> tuple[str, str, str]:
        """
        根据当前状态，生成本回合的文字策略
        """
        # 1. 解析与瘦身
        state_type, clean_state = self._parse_state(raw_state)

        # 2. 从 Router 获取对应场景的 System Prompt
        system_prompt = self.router.get_observation_prompt(state_type)

        print(f"\n🔍 [观察] 识别到场景: {state_type.upper()}")
        print(f"✂️ [观察] 正在请求 AI 参谋分析局势...")

        # 3. 调用 LLM（关键：绝不传入 tools，强制它只输出文本）
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"当前游戏状态：\n{clean_state}"}
            ],
            temperature=self.temperature,
            max_tokens=800  # 限制它不要长篇大论，最多写200字策略
        )
        print("\n" + "🔥" * 20 + " [RAW RESPONSE DUMP] " + "🔥" * 20)
        try:
            # 如果是新版 openai 库，用 model_dump_json 会自动排版成漂亮的 JSON
            print(response.model_dump_json(indent=2))
        except AttributeError:
            # 如果你的库比较老或者用的其他封装，就粗暴地直接打印
            print(response)
        print("🔥" * 50 + "\n")
        # 4. 提取策略文本
        strategy = response.choices[0].message.content.strip()

        print(f"🧠 [AI策略]:\n{strategy}\n" + "-" * 40)

        return state_type, clean_state, strategy