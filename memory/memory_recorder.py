import json
import os
import re
from datetime import datetime


class TrajectoryRecorder:
    def __init__(self, log_dir="training_data"):

        self.last_state_text = None
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self.current_episode = []
        self.last_hp = None

    def record_step(self, state_text: str, action: list):
        """
        每次操作后记录。增加了 current_floor（当前楼层）参数。
        """
        # 提取楼层 (匹配 "Floor 2" 里的 2)
        floor_match = re.search(r'Floor\s+(\d+)', state_text)
        current_floor = int(floor_match.group(1)) if floor_match else 1
        # 提取当前血量 (匹配 "HP: 74/80" 里的 74)
        hp_match = re.search(r'## Player \(You\)[\s\S]*?HP:\s*(\d+)/', state_text)
        current_hp = int(hp_match.group(1)) if hp_match else None
        # 🌟 提取回合数
        round_match = re.search(r'\*\*Round\s+(\d+)\*\*', state_text)
        current_round = int(round_match.group(1)) if round_match else 1
        if not hasattr(self, 'last_round'):
            self.last_round = current_round
        if not hasattr(self, 'hp_at_round_start'):
            self.hp_at_round_start = current_hp
        # 2. 结束判定
        if current_hp is not None and current_hp <= 0:
            print(f"💀 [系统] 血条清空！检测到游戏结束！最终到达楼层: {current_floor}")
            # 注意：死的时候也要给上一步算账！因为是上一步害死了它
            if self.last_hp is not None and len(self.current_episode) > 0:
                self.current_episode[-1]["step_reward"] = current_hp - self.last_hp
            self.finish_episode(current_floor)
            return
        if current_floor > 46:  # 或者 56 (打心脏)
            print(f"🎉 [系统] 突破 51 层！检测到游戏通关！")
            self.finish_episode(current_floor)
            return


        
        # self.last_state_text = state_text
        #
        # # 计算即时奖励 (血量变化)
        # reward = 0
        # if current_hp is not None and self.last_hp is not None:
        #     actual_reward = current_hp - self.last_hp
        #
        #     # 把这笔扣分/加分，悄悄修改到录像带里的【上一步】操作上！
        #     if len(self.current_episode) > 0:
        #         self.current_episode[-1]["step_reward"] = actual_reward
        #         # 如果掉血了，可以在控制台打印一下，方便你监控
        #         if actual_reward < 0:
        #             print(f"🩸 [结账] 刚刚掉血了！上一步操作被追责，扣除 {-actual_reward} 分！")
        #         if hasattr(self, 'last_state_text') and self.last_state_text == state_text:
        #             print(f"⚠️ [警告] 画面未变！上一步动作无效，追加扣除 5 分！")
        #             self.current_episode[-1]["step_reward"] -= 5
        # safe_action = []
        # if isinstance(action, list):
        #     for item in action:
        #         # 检查是不是大模型的 tool_call 对象
        #         if hasattr(item, 'function'):
        #             safe_action.append({
        #                 "name": item.function.name,
        #                 "arguments": item.function.arguments  # 这通常本身就是一个 JSON 字符串
        #             })
        #         else:
        #             safe_action.append(str(item))  # 其他奇怪的列表内容，直接转成字符串
        # else:
        #     # 如果传进来的不是列表，强行转成字符串保底
        #     safe_action = str(action)
        #
        #
        # step_data = {
        #     "floor": current_floor,  # 记录这是在第几层的操作
        #     "state": state_text,
        #     "action": safe_action,
        #     "hp_after": current_hp,
        #     "step_reward": reward  # 这一步的血量得失
        # }
        # self.current_episode.append(step_data)
        # self.last_hp = current_hp
            # ==========================================
            # 🌟 核心突破：回合交替时的“大结算”
            # ==========================================
            # 触发条件1：回合数增加了 (怪物刚打完你)
            # 触发条件2：楼层增加了 (战斗结束，到了下一层/篝火/商店)
        if current_round > self.last_round or current_floor > getattr(self, 'last_floor', current_floor):
            if self.hp_at_round_start is not None and current_hp is not None:
                round_reward = current_hp - self.hp_at_round_start

                print(f"🔄 [回合结算] 第 {self.last_round} 回合结束！该回合总血量变化: {round_reward}")

                # 倒序遍历录像，把这笔账分发给上一回合的所有动作！
                for step in reversed(self.current_episode):
                    if step.get("round") == self.last_round and step.get("floor") == getattr(self, 'last_floor',
                                                                                             current_floor):
                        step["step_reward"] += round_reward
                    elif step.get("round") < self.last_round or step.get("floor") != getattr(self, 'last_floor',
                                                                                             current_floor):
                        break  # 已经结算完上一回合了，停止往前找

            # 刷新回合初始血量，迎接新回合
            self.hp_at_round_start = current_hp

        # 更新当前楼层和回合追踪
        self.last_floor = current_floor
        self.last_round = current_round

        # ==========================================
        # 死亡判定 (死的时候也要强制结算当前回合！)
        # ==========================================
        if current_hp is not None and current_hp <= 0:
            print(f"💀 [系统] 血条清空！最终到达楼层: {current_floor}")
            if self.hp_at_round_start is not None and len(self.current_episode) > 0:
                death_penalty = current_hp - self.hp_at_round_start
                # 给这临死前的最后一个回合发最后一张罚单
                for step in reversed(self.current_episode):
                    if step.get("round") == self.last_round:
                        step["step_reward"] += death_penalty
                    else:
                        break
            self.finish_episode(current_floor)
            return

        # ==========================================
        # 无效动作（幻觉）惩罚逻辑（这个是当场结算的，不需要等回合结束）
        # ==========================================
        invalid_action_penalty = 0
        if hasattr(self, 'last_state_text') and self.last_state_text == state_text:
            invalid_action_penalty = -5
            print(f"⚠️ [警告] 动作 {action} 无效！当场扣除 5 分惩罚！")
        self.last_state_text = state_text

        # ==========================================
        # 清洗大模型的动作对象
        # ==========================================
        safe_action = []
        if isinstance(action, list):
            for item in action:
                if hasattr(item, 'function'):
                    safe_action.append({"name": item.function.name, "arguments": item.function.arguments})
                else:
                    safe_action.append(str(item))
        else:
            safe_action = str(action)

        # ==========================================
        # 记录新动作
        # ==========================================
        step_data = {
            "floor": current_floor,
            "round": current_round,  # 👈 把回合数也存进录像里，方便回溯验证
            "state": state_text,
            "action": safe_action,
            "hp_after": current_hp,
            "step_reward": invalid_action_penalty  # 默认只有可能的幻觉惩罚，血量惩罚等回合结束再加
        }

        self.current_episode.append(step_data)
        if current_hp is not None:
            self.last_hp = current_hp


        print(
            f"📼 [录像机] 楼层 {current_floor} | 回合 {current_round} | 动作: {safe_action} | 当前记录得分: {step_data['step_reward']}")


    def finish_episode(self, final_floor: int):
        """
        游戏结束（无论怎么死的），按最终到达的楼层结算终极奖励！
        """
        if not self.current_episode:
            return

        # ==========================================
        # 🌟 核心修改：按楼层给分！
        # 比如：每深入一层，终极得分加 10 分。
        # 死在第 3 层得 30 分，死在第 15 层得 150 分！
        # ==========================================
        terminal_reward = final_floor * 10
        print(f"🏁 [录像机] 游戏结束！最深到达: 第 {final_floor} 层 | 终极楼层奖金: {terminal_reward}")

        # 依然使用时间衰减（折扣因子）：越靠近死亡的操作，越要承担责任；
        # 越早期的优秀操作（为苟活到高层打下基础的），得分越高。
        discount_factor = 0.95
        current_terminal_bonus = terminal_reward

        for i in reversed(range(len(self.current_episode))):
            # 这一步的总得分 = (这步的血量得失) + (折扣后的楼层奖金)
            self.current_episode[i]["total_reward"] = self.current_episode[i]["step_reward"] + current_terminal_bonus
            # 奖金往前传递时，逐渐衰减
            current_terminal_bonus *= discount_factor

        # 保存为 JSONL
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.log_dir, f"episode_floor{final_floor}_{timestamp}.jsonl")

        with open(filename, "w", encoding="utf-8") as f:
            for step in self.current_episode:
                f.write(json.dumps(step, ensure_ascii=False) + "\n")

        print(f"💾 [录像机] 记录已保存至: {filename}")

        # 清空状态，准备下一局
        self.current_episode = []
        self.last_hp = None