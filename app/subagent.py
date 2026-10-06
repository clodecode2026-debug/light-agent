"""Управление субагентами: запуск специализированных изолированных агентов.

Субагенты работают на том же сервере с тем же API-ключом Antigravity Pro,
но имеют:
- собственный специализированный системный промпт;
- изолированный контекст сообщений (не засоряют историю основного чата);
- строго ограниченный набор инструментов (без возможности рекурсивно плодить субагентов);
- защиту от зависаний (лимит шагов и таймаут).
"""
import concurrent.futures
import time
from typing import Any

from . import config, llm

MAX_SUBAGENT_STEPS = 6
SUBAGENT_TIMEOUT_SECONDS = 75

ROLE_PRESETS: dict[str, dict[str, Any]] = {
    "researcher": {
        "title": "Исследователь (Researcher)",
        "default_model": "antigravity-3.8-flash",
        "allowed_tools": {
            "web_search", "fetch_url", "github_search",
            "read_file", "grep", "list_files", "tree", "view_image",
        },
        "system_prompt": (
            "Ты — автономный субагент-исследователь (Researcher).\n"
            "Твоя задача — исследовать информацию в интернете, документации или на GitHub, "
            "изучить файлы проекта и подготовить для главного агента чёткую структурированную выжимку.\n"
            "ПРАВИЛА:\n"
            "1. Не создавай и не изменяй файлы проекта (ты работаешь только в режиме чтения и поиска).\n"
            "2. Предоставляй только проверенные факты, точные ссылки и конкретные примеры кода/API.\n"
            "3. Отвечай кратко, ёмко, по существу поставленной задачи."
        ),
    },
    "coder": {
        "title": "Разработчик (Coder)",
        "default_model": "antigravity-3.8-pro",
        "allowed_tools": {
            "write_file", "edit_file", "read_file", "validate_code",
            "list_files", "grep", "tree",
        },
        "system_prompt": (
            "Ты — автономный субагент-разработчик (Coder).\n"
            "Твоя задача — написать, доработать или отрефакторить конкретный модуль/файл проекта строго по заданию главного агента.\n"
            "ПРАВИЛА:\n"
            "1. Создавай чистый, рабочий, документированный код через write_file или edit_file.\n"
            "2. ОБЯЗАТЕЛЬНО проверяй синтаксис: если при записи возникло предупреждение автопроверки, немедленно исправь его.\n"
            "3. После написания вызывай validate_code для проверки созданных файлов.\n"
            "4. В конце кратко отчитайся, какие файлы созданы/изменены и что в них реализовано."
        ),
    },
    "tester": {
        "title": "Тестировщик и Ревьюер (Tester / QA)",
        "default_model": "antigravity-3.8-flash",
        "allowed_tools": {
            "read_file", "validate_code", "run_test",
            "execute_code", "run_python_file", "list_files", "grep",
        },
        "system_prompt": (
            "Ты — автономный субагент-тестировщик и ревьюер (Tester / QA).\n"
            "Твоя задача — протестировать код проекта, запустить валидацию и тесты, выявить баги и краевые случаи.\n"
            "ПРАВИЛА:\n"
            "1. Запускай validate_code и run_test, при необходимости проверяй логику через execute_code / run_python_file.\n"
            "2. Проверь обработку ошибок, валидацию входных данных, типизацию и импорты.\n"
            "3. В отчёте укажи:\n"
            "   - Статус проверок (пройдено / ошибки);\n"
            "   - Конкретные найденные баги и файлы/строки, где они находятся;\n"
            "   - Рекомендации по исправлению."
        ),
    },
    "custom": {
        "title": "Специалист (Custom Agent)",
        "default_model": "antigravity-3.8-flash",
        "allowed_tools": {
            "read_file", "write_file", "edit_file", "validate_code",
            "run_test", "execute_code", "run_python_file",
            "web_search", "fetch_url", "github_search",
            "list_files", "tree", "grep",
        },
        "system_prompt": (
            "Ты — автономный специализированный субагент.\n"
            "Твоя задача — выполнить порученную главным агентом подзадачу качественно и без лишних слов.\n"
            "Используй доступные инструменты и в конце предоставь конкретный результат."
        ),
    },
}


def _execute_subagent(role: str, task: str, model: str = "", project: str = "") -> str:
    """Внутренний цикл выполнения субагента."""
    from . import tools

    role_key = (role or "custom").strip().lower()
    preset = ROLE_PRESETS.get(role_key, ROLE_PRESETS["custom"])
    title = preset["title"]
    chosen_model = (model or "").strip() or preset["default_model"]

    # Изолируем проект
    proj = project or config.get_current_project()
    config.set_current_project(proj)

    # Формируем список разрешённых инструментов
    allowed = preset["allowed_tools"]
    all_specs = tools.build_tools()
    tool_specs = [s for s in all_specs if s.get("function", {}).get("name") in allowed]

    messages = [
        {"role": "system", "content": preset["system_prompt"]},
        {"role": "user", "content": task},
    ]

    steps_log: list[str] = []
    final_answer = ""
    start_t = time.perf_counter()

    for step in range(MAX_SUBAGENT_STEPS):
        try:
            resp = llm.chat(messages, tools=tool_specs, model=chosen_model)
        except Exception as exc:
            return (
                f"❌ Субагент [{title}] завершился с ошибкой LLM: {exc}\n"
                f"Выполненные шаги: {', '.join(steps_log) if steps_log else 'нет'}"
            )

        tool_calls = resp.get("tool_calls", [])
        if not tool_calls:
            final_answer = (resp.get("content") or "").strip()
            break

        # Добавляем вызов модели в историю
        messages.append({
            "role": "assistant",
            "content": resp.get("content") or "",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["raw"] or "{}"},
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            t_name = tc.get("name", "")
            t_args = tc.get("args", {})
            if t_name not in allowed:
                out = f"Инструмент '{t_name}' запрещён для субагента {title}."
            else:
                out = tools.execute(t_name, t_args)

            steps_log.append(f"{t_name}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(out)[:5000],
            })

    elapsed = round(time.perf_counter() - start_t, 2)
    if not final_answer:
        try:
            # Если субагент израсходовал лимит шагов на вызовы инструментов, просим его подвести итог
            messages.append({
                "role": "user",
                "content": "Сформулируй краткий финальный отчёт по результатам выполненных действий и проверок.",
            })
            resp = llm.chat(messages, tools=None, model=chosen_model)
            final_answer = (resp.get("content") or "").strip()
        except Exception:
            final_answer = f"Завершено. Вызовы инструментов: {', '.join(steps_log)}."

    if not final_answer:
        final_answer = f"Шаги выполнены: {', '.join(steps_log)}."

    return (
        f"✅ [Результат субагента: {title}]\n"
        f"Модель: {chosen_model} | Время: {elapsed}с | Шагов: {len(steps_log)}\n\n"
        f"{final_answer}"
    )


def tool_delegate_task(role: str, task: str, model: str = "") -> str:
    """Делегирует подзадачу автономному субагенту с изолированным контекстом.

    Роли:
      - 'researcher': Поиск в интернете, документации, коде и на GitHub (режим чтения).
      - 'coder': Разработка, правка и написание файлов с автовалидацией кода.
      - 'tester': Запуск автотестов, синтаксический анализ и поиск краевых случаев.
      - 'custom': Универсальный субагент под нестандартные задачи.

    Параметры:
      role — роль субагента ('researcher', 'coder', 'tester', 'custom')
      task — подробное описание задачи с контекстом
      model — модель (по умолчанию: antigravity-3.8-flash для быстрого ресерча/тестов,
              antigravity-3.8-pro для сложного кодинга)
    """
    if not (task or "").strip():
        return "Ошибка: не указано задание для субагента (task)."

    cur_proj = config.get_current_project()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_execute_subagent, role=role, task=task, model=model, project=cur_proj)
        try:
            return fut.result(timeout=SUBAGENT_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            return (
                f"⏱️ Превышен лимит времени выполнения субагента ({SUBAGENT_TIMEOUT_SECONDS} сек). "
                f"Субагент '{role}' был остановлен."
            )
        except Exception as exc:
            return f"❌ Ошибка при выполнении субагента '{role}': {exc}"


def tool_subagent_roles() -> str:
    """Возвращает информацию о доступных ролях субагентов и их возможностях."""
    lines = ["Доступные роли субагентов в системе:"]
    for key, p in ROLE_PRESETS.items():
        tools_str = ", ".join(sorted(p["allowed_tools"]))
        lines.append(f"\n• **{p['title']}** (`{key}`):")
        lines.append(f"  Модель по умолчанию: `{p['default_model']}`")
        lines.append(f"  Разрешённые инструменты: {tools_str}")
    return "\n".join(lines)
