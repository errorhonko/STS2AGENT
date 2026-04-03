# STS2AGENT

一个面向《Slay the Spire 2》/ STS2 的实验型智能体项目。它通过 MCP 连接游戏侧工具，用大模型读取实时局面、调用游戏动作，并结合本地 RAG 知识库与轨迹记录能力，完成自动决策。

目前仓库已经包含：

- 基于 MCP 的游戏状态读取与动作调用
- 基于 OpenAI 兼容接口的决策循环
- 基于 ChromaDB 的本地知识检索
- 轨迹录制与数据落盘
- 若干 demo / 原型模块

## 项目结构

```text
STS2AGENT/
├─ main.py                  # 项目入口，启动 MCP 客户端和主决策循环
├─ llm_engine.py            # Agent 主逻辑：读取状态、检索知识、发起工具调用
├─ mcp_client.py            # 连接 STS2 MCP server，并代理工具调用
├─ sts2_rag_client.py       # 本地 Chroma 知识库检索封装
├─ prompts.py               # PromptRouter 原型
├─ agent_core/              # 早期 Agent 架构实验代码
├─ memory/                  # 轨迹记录与记忆相关逻辑
├─ data/                    # 卡牌 / 遗物数据与本地 Chroma 持久化数据
├─ training_data/           # 录制出的 episode JSONL
├─ demo/                    # 连接测试与早期 demo
└─ STS2MCP/                 # 本地 STS2 MCP 项目（默认被 .gitignore 忽略）
```

## 工作流程

项目主流程如下：

1. `main.py` 创建 `MCPClient` 和 `LLM`。
2. `MCPClient` 通过 `uv run --directory <STS2_MCP_PATH> python server.py` 启动并连接 STS2 MCP 服务。
3. `llm_engine.py` 周期性读取游戏状态：
   - 获取 JSON 版状态
   - 获取 Markdown 版状态
   - 判断当前屏幕类型
   - 按需检索本地 RAG 知识
4. 大模型基于当前局面和检索结果决定下一步动作。
5. 模型通过 tool call 调用 MCP 工具执行动作。
6. `memory/memory_recorder.py` 记录状态、动作和奖励信息，输出到 `training_data/*.jsonl`。


## 环境变量

项目通过 `.env` 读取配置。可以参考仓库中的 `.env.example.py`，建议整理成 `.env` 文件：

```env
STS2_MCP_PATH=.\STS2MCP\mcp

LLM_MODEL_ID=qwen3.5-2b
LLM_API_KEY=your_api_key
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_TIMEOUT=60
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=1000
```

字段说明：

- `STS2_MCP_PATH`：本地 STS2 MCP 服务目录
- `LLM_MODEL_ID`：要调用的模型名
- `LLM_API_KEY`：OpenAI 兼容服务的 API Key
- `LLM_BASE_URL`：OpenAI 兼容接口地址
- `LLM_TIMEOUT`：请求超时秒数
- `LLM_TEMPERATURE`：采样温度，建议保持较低
- `LLM_MAX_TOKENS`：单次最大输出 token 数

