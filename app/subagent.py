"""Модуль субагентов по стандарту Claude Code.

Каждый субагент:
- Запускается в изолированном контексте сообщений (не засоряет основной диалог).
- Имеет чёткую специализацию и доступ только к необходимым инструментам.
- Работает автономно до выполнения подзадачи или исчерпания лимита шагов.
- Возвращает структурированный отчёт главному агенту.
"""
import concurrent.futures
import time
from typing import Any, Callable

from . import config, llm

MAX_SUBAGENT_STEPS = 40
SUBAGENT_TIMEOUT_SECONDS = 600

SUBAGENT_ROLES: dict[str, dict[str, Any]] = {
    "researcher": {
        "title": "Researcher / Explorer",
        "description": "Исследование кодовой базы, документации, поиск в интернете и GitHub. Только чтение.",
        "default_model": "antigravity-3.8-flash",
        "allowed_tools": {"view", "glob", "grep", "web_search", "fetch_url"},
        "system_prompt": (
            "You are an expert Researcher/Explorer subagent.\n"
            "Your task is to investigate the codebase, find relevant files, read documentation or search the web.\n"
            "GUIDELINES:\n"
            "- You operate in READ-ONLY mode. Do not write or edit any files.\n"
            "- Find facts, line numbers, function signatures, and root causes.\n"
            "- Provide concise, exact findings so the primary agent can take action directly."
        ),
    },
    "coder": {
        "title": "Coder / Software Engineer",
        "description": "Написание нового кода, точечный рефакторинг и исправление модулей.",
        "default_model": "antigravity-3.8-pro",
        "allowed_tools": {"view", "edit", "write", "glob", "grep", "bash"},
        "system_prompt": (
            "You are an expert Coder subagent.\n"
            "Your task is to implement or refactor a specific module/function according to the primary agent's instructions.\n"
            "GUIDELINES:\n"
            "- Prefer editing existing files with `edit` rather than creating new ones.\n"
            "- Maintain codebase style, imports, and clean structure.\n"
            "- Verify code syntax and logic before finishing.\n"
            "- Report clearly which files and lines were modified."
        ),
    },
    "tester": {
        "title": "Tester / QA & Verification",
        "description": "Запуск тестов, поиск краевых случаев, проверка работоспособности сервиса.",
        "default_model": "antigravity-3.8-flash",
        "allowed_tools": {"bash", "view", "glob", "grep"},
        "system_prompt": (
            "You are an expert QA and Testing subagent.\n"
            "Your task is to run unit tests, integration tests, or smoke tests and verify correctness.\n"
            "GUIDELINES:\n"
            "- Use `bash` to execute tests (pytest, unittest, npm test) and check return codes.\n"
            "- Report failing assertions, stack traces, and exact files/lines that need fixing.\n"
            "- If all tests pass, report clear confirmation."
        ),
    },
    "devops": {
        "title": "DevOps / Infrastructure Engineer",
        "description": "Управление серверами, API облачных провайдеров, настройка окружения и git.",
        "default_model": "antigravity-3.8-flash",
        "allowed_tools": {"bash", "view", "edit", "write"},
        "system_prompt": (
            "You are an expert DevOps subagent.\n"
            "Your task is to configure environments, install dependencies, manage git, and call cloud APIs.\n"
            "GUIDELINES:\n"
            "- Use `bash` to execute commands (pip, npm, git, curl) and inspect outputs.\n"
            "- Only perform operations explicitly requested in the task.\n"
            "- Report command output, status codes, and environment health."
        ),
    },
    "general": {
        "title": "General Purpose Autonomous Agent",
        "description": "Универсальный автономный агент для сложных многосоставных задач.",
        "default_model": "antigravity-3.8-flash",
        "allowed_tools": {"view", "edit", "write", "bash", "glob", "grep", "web_search", "fetch_url"},
        "system_prompt": (
            "You are an expert General-Purpose autonomous subagent.\n"
            "Your task is to solve the assigned subproblem carefully, efficiently, and with minimal overhead.\n"
            "Use the provided tools and provide a clear, technical end-of-task summary."
        ),
    },
}


def list_roles() -> list[dict]:
    """Возвращает список доступных ролей субагентов для инструментов."""
    return [
        {
            "role": k,
            "title": v["title"],
            "description": v["description"],
            "tools": sorted(list(v["allowed_tools"])),
        }
        for k, v in SUBAGENT_ROLES.items()
    ]


def run_subagent(
    role: str,
    task: str,
    model: str = "",
    project: str = "",
    on_event: Callable[[str, dict], None] | None = None,
) -> str:
    """Выполняет задачу в изолированном контексте субагента."""
    from . import tools

    role_key = (role or "general").strip().lower()
    preset = SUBAGENT_ROLES.get(role_key, SUBAGENT_ROLES["general"])
    chosen_model = (model or "").strip() or preset["default_model"]
    allowed_tool_names = preset["allowed_tools"]

    # Формируем набор спецификаций инструментов, разрешённых роли
    all_specs = tools.build_tools()
    tool_specs = [
        spec for spec in all_specs
        if spec["function"]["name"] in allowed_tool_names
    ]

    messages: list[dict] = [
        {"role": "system", "content": preset["system_prompt"]},
        {"role": "user", "content": f"SUBAGENT TASK ({preset['title']}):\n{task}"},
    ]

    history_log: list[str] = []
    start_time = time.perf_counter()

    def emit_sub(kind: str, payload: dict) -> None:
        if on_event:
            try:
                on_event("subagent", {"role": role_key, "kind": kind, **payload})
            except Exception:
                pass

    emit_sub("start", {"task": task[:120]})

    step = 0
    while step < MAX_SUBAGENT_STEPS:
        step += 1
        if time.perf_counter() - start_time > SUBAGENT_TIMEOUT_SECONDS:
            return (
                f"⏱️ Субагент [{preset['title']}] превысил таймаут ({SUBAGENT_TIMEOUT_SECONDS} сек).\n"
                f"Выполненные шаги:\n" + "\n".join(f"- {h}" for h in history_log)
            )

        try:
            resp = llm.chat(messages, tools=tool_specs, model=chosen_model, temperature=0.3)
        except Exception as exc:
            return f"❌ Ошибка вызова модели субагента [{preset['title']}]: {exc}"

        tool_calls = resp.get("tool_calls") or []
        if not tool_calls:
            # Модель дала финальный ответ
            answer = (resp.get("content") or "").strip()
            emit_sub("done", {"summary": answer[:150]})
            return f"### Результат субагента [{preset['title']}]:\n\n{answer}"

        messages.append({
            "role": "assistant",
            "content": resp.get("content") or "",
            "tool_calls": [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc.get("raw") or "{}"}}
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            tname = tc["name"]
            targs = tc.get("args") or {}

            # Защита от несанкционированного инструмента
            if tname not in allowed_tool_names:
                out = f"Инструмент '{tname}' не разрешён для роли {role_key}."
            else:
                emit_sub("tool", {"tool": tname, "args": targs})
                out = tools.execute(tname, targs)

            preview = f"{tname}: {out[:120]}..." if len(out) > 120 else f"{tname}: {out}"
            history_log.append(preview)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": out[:6000],
            })

    return (
        f"⚠️ Субагент [{preset['title']}] достиг лимита шагов ({MAX_SUBAGENT_STEPS}).\n"
        f"Выполненные операции:\n" + "\n".join(f"- {h}" for h in history_log[-5:])
    )
