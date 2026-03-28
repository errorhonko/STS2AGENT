import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from prompts import STS2_SYSTEM_PROMPT
# 加载环境变量
load_dotenv()


def ask_ai_for_next_move(game_state_text):
    """
    把游戏状态发给大模型，让它决定怎么出牌
    """
    # 1. 初始化模型客户端
    client = OpenAI(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL")
    )
    print("👉 当前读取的接口网址:", os.getenv("LLM_BASE_URL"))
    print("👉 当前读取的模型KEY:", os.getenv("LLM_API_KEY"))


    print("🧠 正在呼叫大模型进行思考...")

    # 3. 调用大模型
    try:
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL_ID"),
            messages=[
                {"role": "system", "content": STS2_SYSTEM_PROMPT},
                {"role": "user", "content": f"当前游戏状态：\n{game_state_text}"}
            ],
            temperature=0.1  # 温度设低一点，让它冷静思考，不要瞎编
        )
        print("📦 API 返回的原始对象:", response)
        # 4. 解析 AI 的回答
        ai_reply = response.choices[0].message.content.strip()
        print("\n🤖 AI 原始回复：\n", ai_reply)

        # 尝试将回答转换为 Python 字典
        decision = json.loads(ai_reply)
        print("\n✅ 决策解析成功！")
        print("💡 AI 的思路:", decision.get("reasoning"))
        print("🃏 准备打出的牌索引:", [card["hand_index"] for card in decision.get("cards_to_play")])

        return decision


    except Exception as e:

        import traceback  # 导入错误追踪库

        print(f"\n❌ 思考失败，大模型脑抽了: {e}")

        print("\n👇 具体的报错行数和详细原因如下：")

        traceback.print_exc()  # 打印完整的红色报错堆栈

        return None


if __name__ == "__main__":
    # 为了测试，我们把你刚才抓到的真实数据直接当作字符串传给它
    sample_game_state = """
    【此处省略，请假装这里是你刚才抓取到的完整战报数据】
    由于测试，我直接把关键信息写在这里：
    敌人：SEAPUNK_0 (Intent: 攻击 11)
    费用：3/3
    手牌：[0] 防御(1费), [1] 打击(1费), [2] 防御(1费), [3] 打击(1费), [4] 打击(1费)
    """

    # 真实测试时，你可以把你上一轮抓到的那段文字直接赋值给 sample_game_state
    ask_ai_for_next_move(sample_game_state)