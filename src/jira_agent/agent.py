"""ReAct-style agent loop over LLM tool calling (Ollama or cloud)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from jira_agent.config import Settings
from jira_agent.llm import LLMClient
from jira_agent.prompts import build_system_prompt
from jira_agent.tools import ToolRegistry, ollama_tool_schemas


ProgressCallback = Callable[[str], None]


@dataclass
class AgentTurn:
    role: str
    content: str
    tool_name: str | None = None


@dataclass
class AgentResult:
    answer: str
    turns: list[AgentTurn] = field(default_factory=list)
    tool_calls: int = 0


class JiraAgent:
    def __init__(
        self,
        settings: Settings,
        llm: LLMClient,
        tools: ToolRegistry,
        *,
        project_keys: list[str] | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.tools = tools
        self.project_keys = project_keys or list(settings.jira_project_keys)
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": build_system_prompt(
                    language=settings.agent_language,
                    project_keys=self.project_keys,
                    schema_id=settings.assets_object_schema_id,
                    model=f"{llm.provider_name}/{llm.model_name}",
                ),
            }
        ]

    def ask(
        self,
        user_message: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> AgentResult:
        self.messages.append({"role": "user", "content": user_message})
        turns: list[AgentTurn] = []
        tool_calls_count = 0
        schemas = ollama_tool_schemas()

        for _round in range(self.settings.agent_max_tool_rounds):
            if on_progress:
                on_progress(
                    f"{self.llm.provider_name} ({self.llm.model_name}) думает…"
                )

            assistant = self.llm.chat(self.messages, tools=schemas)
            content = (assistant.get("content") or "").strip()
            raw_tool_calls = assistant.get("tool_calls") or []

            # Persist assistant message exactly as returned (needed for tool round-trip)
            self.messages.append(assistant)

            if not raw_tool_calls:
                answer = content or "Не удалось получить ответ модели."
                turns.append(AgentTurn(role="assistant", content=answer))
                return AgentResult(answer=answer, turns=turns, tool_calls=tool_calls_count)

            for call in raw_tool_calls:
                tool_calls_count += 1
                fn = call.get("function") or {}
                name = fn.get("name") or call.get("name") or ""
                arguments = fn.get("arguments")
                call_id = call.get("id") or f"call_{tool_calls_count}"
                if on_progress:
                    on_progress(f"Инструмент: {name}({_short_args(arguments)})")

                result = self.tools.execute(name, arguments)
                turns.append(
                    AgentTurn(
                        role="tool",
                        content=result,
                        tool_name=name,
                    )
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "tool_name": name,
                        "name": name,
                        "content": result,
                    }
                )

        # Exhausted tool rounds — force a final answer without tools
        if on_progress:
            on_progress("Лимит вызовов инструментов — финальный ответ…")
        self.messages.append(
            {
                "role": "user",
                "content": (
                    "Достигнут лимит вызовов инструментов. "
                    "Дай итоговый ответ на основе уже полученных данных."
                ),
            }
        )
        final = self.llm.chat(self.messages, tools=None)
        self.messages.append(final)
        answer = (final.get("content") or "").strip() or "Данных недостаточно для ответа."
        turns.append(AgentTurn(role="assistant", content=answer))
        return AgentResult(answer=answer, turns=turns, tool_calls=tool_calls_count)

    def reset(self) -> None:
        system = self.messages[0]
        self.messages = [system]


def _short_args(arguments: Any, limit: int = 120) -> str:
    if arguments is None:
        return ""
    if isinstance(arguments, (dict, list)):
        text = json.dumps(arguments, ensure_ascii=False)
    else:
        text = str(arguments)
    return text if len(text) <= limit else text[: limit - 1] + "…"
