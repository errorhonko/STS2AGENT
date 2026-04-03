class PromptRouter:
    def __init__(self):
        # 基础人设：所有 Prompt 的基底
        self.base_persona = (
            "你是一个《杀戮尖塔2》(Slay the Spire 2) 的顶级自动化 AI 玩家。\n"
            "你的目标是做出最优决策，赢得最终的胜利。\n"
        )
    def get_observation_prompt(self, state_type):
        """
                【观察阶段】提示词：只负责分析局势，输出文字策略，绝对不调用工具。
                """
        task_instruction = (
            "【当前任务】：请仔细阅读游戏状态，并输出你的『策略』。\n"
            "【严格要求】：\n"
            "1. 禁止回复任何工具调用代码或 JSON 格式。\n"
            "2. 用简短的大白话输出你的分析和决定（字数控制在100字以内）。\n"
            "3. 必须明确指出你要操作的对象的索引 (index) 或具体动作。\n\n"
        )

        # 针对不同场景，给出不同的分析侧重点
        scene_guidance = {
            "combat": "【战斗场景提示】：根据当前的能量，优先计算是否能击杀敌人（斩杀线）。如果不能，请关注敌人的意图，计算需要多少格挡值，优先保证自身血量，减少血量损失,如果判断当前敌人为会失去很多血量的强敌或BOSS考虑使用药水，明确给出出牌/回合结束/使用药水的一个指令。",
            "map": "【地图场景提示】：分析当前血量和金币。血量健康时多走问号（Unkown）和篝火（RestSite）；金币多时可以考虑商店（Shop），尽量避开精英怪（Elite）。给出你要选择的节点索引。",
            "card_reward": "【选牌场景提示】：分析当前卡牌对卡组的收益。如果都不好，可以选择跳过 (Skip)。明确给出你要选的卡牌索引或说明跳过。",
            "event": "【事件场景提示】：权衡失去生命值/金币与获得遗物/卡牌的利弊，选择预期收益最高的选项。",
            "shop": "【商店场景提示】：根据卡组考虑购买卡牌或者是遗物，其次是移除打击/防御。"
        }

        # 如果遇到未知的 state_type，给一个通用的提示
        guidance = scene_guidance.get(state_type, "【通用场景提示】：请根据当前屏幕内容，选择最合理的选项。")

        return f"{self.base_persona}\n{task_instruction}\n{guidance}"


    def get_action_prompt(self, state_type, strategy):
        """
                【执行阶段】提示词：拿到策略后，变成一个“无情的工具调用机器”。
                """
        return (
            f"{self.base_persona}\n"
            "【当前任务】：你现在的身份是『策略执行器』。\n"
            f"【战术参谋给出的策略如下】:\n------\n{strategy}\n------\n\n"
            "【严格要求】：\n"
            "1. 你必须、且只能通过 function calling / tool calls 来执行上述策略。\n"
            "2. 绝对禁止输出任何常规文本回复（不要说“好的”、“我明白了”）。\n"
            "3. 如果策略包含多个动作（比如打出多张牌），请一次性按顺序发出多个 tool calls，或者发出第一步动作。"

        )

    def get_reflection_prompt(self, failed_action: str, error_msg: str) -> str:
        """
        【反思阶段】提示词：当调用工具报错时，让 AI 分析原因。
        """
        return (
            f"{self.base_persona}\n"
            "【系统警告】：你刚才执行的操作失败了！\n"
            f"- 试图执行的操作：{failed_action}\n"
            f"- 游戏返回的错误：{error_msg}\n\n"
            "【当前任务】：\n"
            "请分析失败的原因（例如：能量不足、目标不存在、选错了索引）。\n"
            "输出你修正后的新策略。如果无法挽回，请输出“结束回合”或“跳过”。"
        )