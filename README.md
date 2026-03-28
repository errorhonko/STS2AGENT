# STS2AGENT

一个用于连接《Slay the Spire 2》并驱动自动决策的最小 Agent 骨架。

## 现状判断

截至 2026-03-27，我没有查到稳定的官方公开 API 或模组接入文档，因此这个项目采用三层结构：

1. `bridge` 负责和游戏通信
2. `policy` 负责根据状态做决策
3. `loop` 负责驱动 Agent 主循环

这样后续无论你接的是：

- 模组导出的本地 HTTP/WebSocket 接口
- 本地文件/命名管道
- 屏幕识别 + 输入模拟
- 内存读取 / Hook

都只需要替换 `bridge` 层。

## 当前实现

当前提供两种联调方式：

### 1. `FileBridge`

- 从 `runtime/state.json` 读取游戏状态
- 把动作写入 `runtime/action.json`

适合先把 Agent 决策链路跑通。

### 2. HTTP 测试 Agent

用于和你已有的外部插件做联调：

- `GET /health` 检查服务是否在线
- `POST /v1/ping` 测试插件到 Agent 的链路
- `POST /v1/act` 发送游戏状态并获取动作

## 项目结构

```text
src/sts2agent/
  bridge.py    # 游戏连接接口与文件桥接实现
  cli.py       # 命令行入口
  http_agent.py# HTTP 联调用测试 Agent
  loop.py      # 主循环
  models.py    # 状态、动作数据模型
  policy.py    # 一个简单的基线策略
tests/
  test_policy.py
```

## 快速开始

### 1. 启动 HTTP 测试 Agent

```powershell
python -m src.sts2agent.cli serve --host 127.0.0.1 --port 8765
```

### 2. 测试握手

```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:8765/health `
  -Method GET
```

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8765/v1/ping `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"plugin":"sts2-test","message":"hello"}'
```

### 3. 测试动作返回

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8765/v1/act `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "screen_type":"COMBAT",
    "energy":3,
    "hand":[
      {"id":"strike","name":"Strike","cost":1,"tags":["ATTACK"]},
      {"id":"bash","name":"Bash","cost":2,"tags":["ATTACK","VULNERABLE"]}
    ],
    "enemies":[
      {"id":"cultist","name":"Cultist","hp":48,"intent":"ATTACK"}
    ],
    "available_actions":["PLAY_CARD","END_TURN"]
  }'
```

返回体里的 `action` 就是你的插件后续需要执行的动作。

## 文件模式

### 1. 准备一个示例状态

在项目根目录创建 `runtime/state.json`：

```json
{
  "screen_type": "COMBAT",
  "player_hp": 68,
  "max_hp": 80,
  "energy": 3,
  "gold": 99,
  "deck_size": 14,
  "hand": [
    {"id": "strike", "name": "Strike", "cost": 1, "tags": ["ATTACK"]},
    {"id": "defend", "name": "Defend", "cost": 1, "tags": ["SKILL", "BLOCK"]},
    {"id": "bash", "name": "Bash", "cost": 2, "tags": ["ATTACK", "VULNERABLE"]}
  ],
  "enemies": [
    {"id": "cultist", "name": "Cultist", "hp": 48, "intent": "ATTACK"}
  ],
  "available_actions": ["PLAY_CARD", "END_TURN"]
}
```

### 2. 运行 Agent

```powershell
python -m src.sts2agent.cli run-once
```

### 3. 查看 Agent 输出动作

Agent 会生成 `runtime/action.json`，例如：

```json
{
  "action_type": "PLAY_CARD",
  "target_id": "cultist",
  "card_id": "bash",
  "reason": "Picked highest-priority playable attack."
}
```

## 真实接入 STS2 的推荐顺序

### 路线 A：模组桥接

最稳妥。思路是：

1. 在游戏侧做一个 Mod
2. 把当前战斗状态导出为 JSON
3. 读取 Agent 返回的动作
4. 在游戏内执行对应点击/选牌/结束回合

你最终只需要新增一个 `Sts2ModBridge`，实现和 `GameBridge` 一样的方法。

### 路线 B：视觉识别 + 输入自动化

如果短期内没有官方/社区模组接口，这是最容易起步的方案：

1. 截图识别当前界面
2. OCR / 模板匹配提取手牌、能量、敌人意图
3. Agent 输出动作
4. 用输入模拟点击 UI

缺点是脆弱，UI 改动后容易失效。

### 路线 C：内存/Hook

能力最强，但开发和维护成本最高，也最容易随版本变动失效。

## 给外部插件的最小协议建议

你的插件如果只是先做联调，最小实现可以是：

1. 游戏里抓到当前状态后，组装成 `POST /v1/act` 的 JSON
2. Agent 返回 `{ "ok": true, "action": { ... } }`
3. 插件根据 `action_type` 和附带字段执行对应游戏动作

建议优先支持这几个字段：

- `screen_type`
- `energy`
- `hand`
- `enemies`
- `available_actions`

动作侧先支持：

- `PLAY_CARD`
- `END_TURN`
- `NO_OP`

## 下一步建议

如果你愿意，我们下一步可以直接往其中一个方向继续：

1. 我帮你把这个 HTTP 协议对齐成你插件的实际字段
2. 我直接补一个 WebSocket 版本，适合持续推状态
3. 我把当前规则策略换成“纯测试回包 Agent”，专门验证连通性
4. 我们开始定义真实战斗决策需要的状态字段

## 参考来源

- [Steam 商店页面（Slay the Spire 2）](https://store.steampowered.com/app/2868840/Slay_the_Spire_2/)
- [Mega Crit 官网](https://megacrit.com/)
