import asyncio
import json
import os
import re
from enum import Enum
from typing import Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI

from memory.memory_recorder import TrajectoryRecorder
from sts2_rag_client import STS2RAGClient

load_dotenv()

SYSTEM_PROMPT = """
You are an autonomous Slay the Spire 2 agent.

On every loop:
1. Read the current game state carefully.
2. Use retrieved build knowledge as supporting context, especially for card rewards, relic/event choices, and long-term deck direction.
3. In combat, prioritize exact tactical correctness from the live board state over generic build advice.
4. Use tools to take the next action. Prefer making one concrete tool call each loop.
5. Only reply with plain text if you are blocked or a tool is unavailable.

Important rules:
- Card indices and target ids must match the latest state exactly.
- End the turn when you have no better legal action.
- For rewards, events, shops, rest sites, and card selection screens, choose the strongest progression line available.
- Retrieved knowledge is guidance, not a substitute for current-state calculation.
""".strip()


class ExecutionMode(Enum):
    BATCH = "batch"
    SEQUENTIAL = "sequential"


class LLM:
    def __init__(
        self,
        mcp_client,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        mcp_server_path: Optional[str] = None,
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        **kwargs,
    ):
        self.recorder = TrajectoryRecorder()
        self.mode = mode
        self.mcp_client = mcp_client
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.model = model or os.getenv("LLM_MODEL_ID")
        self.temperature = self._coerce_float(kwargs.get("temperature"), os.getenv("LLM_TEMPERATURE"), default=0.2)
        self.max_tokens = self._coerce_int(kwargs.get("max_tokens"), os.getenv("LLM_MAX_TOKENS"), default=1000)
        self.timeout = self._coerce_float(kwargs.get("timeout"), os.getenv("LLM_TIMEOUT"), default=60)

        if not self.api_key or self.api_key == "null":
            raise ValueError("LLM_API_KEY is not configured.")

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        self.history: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.rag_client = self._init_rag_client()

    async def start_thinking_loop(self):
        print("[Agent] Connected. Starting decision loop.")
        while True:
            print("\n--- New Loop ---")
            await self.decide_and_act()
            await asyncio.sleep(3)

    async def decide_and_act(self):
        print("[Agent] Fetching latest game state...")
        state_json_raw = await self.mcp_client.get_state(format="json")
        state_markdown = await self.mcp_client.get_state(format="markdown")
        state_obj = self._parse_state_json(state_json_raw)
        state_type = self._get_state_type(state_obj, state_markdown)
        rag_context = self._build_rag_context(state_obj, state_markdown, state_type)
        message = self._build_user_message(state_obj, state_json_raw, state_markdown, state_type, rag_context)

        print(f"[Agent] State type: {state_type}")
        if rag_context:
            print("[Agent] Retrieved build guidance for this state.")
        else:
            print("[Agent] No extra build guidance retrieved for this state.")

        self.history.append({"role": "user", "content": message})
        self._trim_history()

        request_messages = self._build_request_messages()
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=self._json_safe(request_messages),
            tools=self._json_safe(self._build_openai_tools()),
            tool_choice="auto",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        ai_message = response.choices[0].message
        tool_calls = ai_message.tool_calls or []
        self.recorder.record_step(state_markdown, tool_calls)

        if tool_calls:
            print(f"[Agent] Model requested {len(tool_calls)} tool call(s).")
            self.history.append(self._assistant_message_to_history(ai_message))
            if self.mode == ExecutionMode.BATCH:
                for call in tool_calls:
                    await self.execute_single_call(call)
            else:
                await self.execute_single_call(tool_calls[0])
        else:
            print(f"[Agent] Model replied with text: {ai_message.content}")
            self.history.append({"role": "assistant", "content": ai_message.content or ""})

    async def execute_single_call(self, tool_call):
        func_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments or "{}")
        print(f"[Agent] Executing: {func_name} {args}")
        result = await self.mcp_client.call_tool(func_name, args)
        self.history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result),
            }
        )



    def _build_request_messages(self) -> list[dict[str, Any]]:
        latest_state_message = ""
        system_message = SYSTEM_PROMPT

        for message in self.history:
            role = message.get("role")
            content = message.get("content", "")
            if role == "system" and content:
                system_message = content
            elif role == "user" and content:
                latest_state_message = content

        if not latest_state_message:
            latest_state_message = "Read the latest game state and choose the next action."

        latest_state_message = (
            f"{latest_state_message}\n\n"
            "Final instruction: decide the single best next action for the current state only. "
            "Use exactly one tool call if a legal tool action is available."
        )

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": latest_state_message},
        ]

    @staticmethod
    def _assistant_message_to_history(ai_message: Any) -> dict[str, Any]:
        tool_calls = []
        for call in ai_message.tool_calls or []:
            tool_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments or "{}",
                    },
                }
            )
        message = {
            "role": "assistant",
            "content": ai_message.content or "",
        }
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message

    def _init_rag_client(self) -> Optional[STS2RAGClient]:
        try:
            client = STS2RAGClient()
            stats = client.stats()
            print(
                f"[RAG] Loaded {stats['document_count']} docs from {stats['persist_dir']} "
                f"({stats['collection_name']})."
            )
            return client
        except Exception as exc:
            print(f"[RAG] Disabled: {exc}")
            return None

    def _build_openai_tools(self) -> list[dict[str, Any]]:
        openai_tools: list[dict[str, Any]] = []
        for tool in self.mcp_client.tools:
            if tool.name.startswith("mp_"):
                continue
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": self._remove_none(tool.inputSchema)
                        if tool.inputSchema
                        else {"type": "object", "properties": {}},
                    },
                }
            )
        return openai_tools

    def _build_user_message(
        self,
        state_obj: dict[str, Any] | None,
        state_json_raw: str,
        state_markdown: str,
        state_type: str,
        rag_context: str,
    ) -> str:
        structured_state = self._format_state_json(state_obj, state_json_raw)
        sections = [
            f"Current screen: {state_type}",
            "Structured game state:",
            structured_state,
            "Readable game state:",
            state_markdown,
        ]
        if rag_context:
            sections.extend(["Retrieved build guidance:", rag_context])
        sections.extend(
            [
                "Decision instruction:",
                "Use the current game state first, use the retrieved guidance as supporting evidence, and take the next best action now.",
            ]
        )
        return "\n\n".join(section for section in sections if section)

    def _build_rag_context(
        self,
        state_obj: dict[str, Any] | None,
        state_markdown: str,
        state_type: str,
    ) -> str:
        if not self.rag_client:
            return ""

        character = self._extract_character(state_obj)
        sections: list[tuple[str, str]] = []

        if character:
            overview = self._safe_context(
                query=f"{character} archetypes overview core plan",
                top_k=3,
                character=character,
                doc_types=["character_overview", "archetype"],
            )
            if overview:
                sections.append(("Character overview", overview))

        if state_type == "event":
            for relic_query in self._extract_event_relic_queries(state_obj)[:3]:
                relic_context = self._safe_context(
                    query=relic_query,
                    top_k=2,
                    character=character,
                    doc_types=["relic", "relic_archetype_relation"],
                )
                if relic_context:
                    sections.append((f"Event option: {relic_query}", relic_context))

        if state_type in {"card_reward", "card_select"}:
            if character:
                build_context = self._safe_context(
                    query=f"{character} core enabler filler pollution cards",
                    top_k=4,
                    character=character,
                    doc_types=["archetype", "card_archetype_relation"],
                )
                if build_context:
                    sections.append(("Build priorities", build_context))

            for card_name in self._extract_card_names_from_markdown(state_markdown)[:4]:
                card_context = self._safe_context(
                    query=f"{card_name} role synergy archetype",
                    top_k=2,
                    character=character,
                    doc_types=["card", "card_archetype_relation"],
                )
                if card_context:
                    sections.append((f"Card option: {card_name}", card_context))

        elif state_type in {"monster", "elite", "boss"}:
            for relic_name in self._extract_relic_names(state_obj)[:2]:
                relic_context = self._safe_context(
                    query=f"{relic_name} synergy",
                    top_k=2,
                    character=character,
                    doc_types=["relic", "relic_archetype_relation"],
                )
                if relic_context:
                    sections.append((f"Relic synergy: {relic_name}", relic_context))

        if not sections:
            return ""

        deduped: list[str] = []
        seen = set()
        for title, content in sections:
            block = f"## {title}\n{content}".strip()
            if block not in seen:
                seen.add(block)
                deduped.append(block)
        return "\n\n".join(deduped)

    def _safe_context(self, **kwargs) -> str:
        try:
            result = self.rag_client.build_context(**kwargs)
        except Exception as exc:
            print(f"[RAG] Query failed: {exc}")
            return ""
        return result.get("context_text", "") if result.get("matches") else ""

    @staticmethod
    def _extract_card_names_from_markdown(state_markdown: str) -> list[str]:
        names: list[str] = []
        for line in state_markdown.splitlines():
            match = re.match(r"^- \[(\d+)\] \*\*(.+?)\*\*", line.strip())
            if match:
                names.append(match.group(2).strip())
        return names

    @staticmethod
    def _extract_event_relic_queries(state_obj: dict[str, Any] | None) -> list[str]:
        if not state_obj:
            return []
        options = state_obj.get("event", {}).get("options", [])
        queries: list[str] = []
        for option in options:
            if not isinstance(option, dict):
                continue
            label = option.get("relic_name") or option.get("title")
            if label:
                queries.append(str(label))
        return queries

    @staticmethod
    def _extract_relic_names(state_obj: dict[str, Any] | None) -> list[str]:
        if not state_obj:
            return []
        relics = state_obj.get("player", {}).get("relics", [])
        names: list[str] = []
        for relic in relics:
            if not isinstance(relic, dict):
                continue
            label = relic.get("name") or relic.get("id")
            if label:
                names.append(str(label))
        return names

    def _extract_character(self, state_obj: dict[str, Any] | None) -> str | None:
        if not state_obj:
            return None
        raw = state_obj.get("player", {}).get("character")
        if not raw:
            return None
        normalized = str(raw).strip().lower()
        mapping = {
            "the ironclad": "ironclad",
            "ironclad": "ironclad",
            "the silent": "silent",
            "silent": "silent",
            "the defect": "defect",
            "defect": "defect",
            "watcher": "watcher",
            "the watcher": "watcher",
            "the exile": "exile",
            "exile": "exile",
        }
        return mapping.get(normalized, normalized.replace("the ", ""))

    @staticmethod
    def _get_state_type(state_obj: dict[str, Any] | None, state_markdown: str) -> str:
        if state_obj and state_obj.get("state_type"):
            return str(state_obj["state_type"]).lower()
        first_line = state_markdown.strip().splitlines()[0] if state_markdown.strip() else ""
        if "Game State:" in first_line:
            return first_line.split("Game State:", 1)[1].strip().lower()
        return "unknown"

    @staticmethod
    def _parse_state_json(state_json_raw: str) -> dict[str, Any] | None:
        if not state_json_raw:
            return None
        try:
            parsed = json.loads(state_json_raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _format_state_json(state_obj: dict[str, Any] | None, state_json_raw: str) -> str:
        if state_obj is not None:
            return json.dumps(state_obj, ensure_ascii=False, indent=2)
        return state_json_raw

    def _trim_history(self) -> None:
        if len(self.history) <= 12:
            return
        self.history = [self.history[0]] + self.history[-11:]


    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): LLM._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [LLM._json_safe(item) for item in value]
        if hasattr(value, "model_dump"):
            try:
                dumped = value.model_dump(mode="json", by_alias=True)
            except TypeError:
                dumped = value.model_dump()
            return LLM._json_safe(dumped)
        if hasattr(value, "dict"):
            return LLM._json_safe(value.dict())
        if hasattr(value, "__dict__"):
            return LLM._json_safe(vars(value))
        return str(value)

    @staticmethod
    def _remove_none(obj):
        if isinstance(obj, dict):
            return {k: LLM._remove_none(v) for k, v in obj.items() if v is not None}
        if isinstance(obj, list):
            return [LLM._remove_none(item) for item in obj if item is not None]
        return obj

    @staticmethod
    def _coerce_float(*values, default: float) -> float:
        for value in values:
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default

    @staticmethod
    def _coerce_int(*values, default: int) -> int:
        for value in values:
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return default
