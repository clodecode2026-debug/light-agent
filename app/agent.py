"""Основной цикл агента: вызов LLM, выполнение инструментов, итерации до ответа."""
import time
from datetime import datetime, timezone

from . import llm, memory, tools

MAX_STEPS = 8  # защита от бесконечного цикла вызовов инструментов

_step_counter = {"count": 0}
_last_activity = {"ts": time.time()}


def touch() -> None:
    """Отмечает активность — используется anti-sleep таймером."""
    _last_activity["ts"] = time.time()
    _step_counter["count"] = 0


def idle_seconds() -> float:
    return time.time() - _last_activity["ts"]


def state() -> dict:
    return {
        "idle_seconds": round(idle_seconds()),
        "tools_used": _step_counter["count"],
    }


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run(user_message: str, session_id: str = "default",
        history: list[dict] | None = None) -> dict:
    """Выполняет задачу пользователя и возвращает финальный ответ.

    Модель может вызывать инструменты многошагово: цикл повторяется,
    пока агент не вернёт текстовый ответ без вызовов инструментов.
    """
    touch()

    # Контекст: сжатая сводка прошлого + свежие сообщения + новый вопрос.
    # Сжимаем, а не обрезаем: старые сообщения сворачиваются в пересказ,
    # поэтому агент помнит важное, но не платит за всю переписку.
    #
    # Важно: сводка вклеивается в ТОТ ЖЕ системный промпт. Два system-сообщения
    # подряд модели читают плохо - она отвечает "OK" на первый попавшийся вопрос.
    system = tools.SYSTEM_PROMPT
    messages: list[dict] = []

    if history is not None:
        for m in history[-24:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})
    else:
        # build_context сам добавляет вопрос последним элементом, убираем его.
        built = memory.build_context(session_id, user_message)
        if built and built[0]["role"] == "system":
            system += "\n\n" + built[0]["content"]
            fresh = built[1:-1]
        else:
            fresh = built[:-1]
        for m in fresh:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})

    messages.insert(0, {"role": "system", "content": system})

    memory.add_message(session_id, "user", user_message)

    tool_specs = tools.build_tools()
    steps: list[str] = []
    provider_used = ""
    total_start = time.perf_counter()

    for step in range(MAX_STEPS):
        try:
            resp = llm.chat(messages, tools=tool_specs)
        except llm.LLMError as exc:
            _log(f"LLM недоступен: {exc}")
            return {
                "ok": False,
                "error": str(exc),
                "steps": steps,
                "elapsed": round(time.perf_counter() - total_start, 2),
            }

        provider_used = resp["provider"]

        # Нет вызовов инструментов — агент закончил
        if not resp["tool_calls"]:
            answer = resp["content"].strip() or "Готово."
            memory.add_message(session_id, "assistant", answer)
            _log(f"Готово за {round(time.perf_counter() - total_start, 2)}с "
                 f"через {provider_used}, шагов: {step}")
            return {
                "ok": True,
                "answer": answer,
                "steps": steps,
                "provider": provider_used,
                "elapsed": round(time.perf_counter() - total_start, 2),
            }

        # Выполняем инструменты
        messages.append({
            "role": "assistant",
            "content": resp["content"] or "",
            "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": tc["raw"] or "{}"}}
                for tc in resp["tool_calls"]
            ],
        })

        for tc in resp["tool_calls"]:
            _log(f"Инструмент {tc['name']}({list(tc['args'].keys())})")
            output = tools.execute(tc["name"], tc["args"])
            steps.append(f"{tc['name']}: {output[:200]}")
            _step_counter["count"] += 1
            messages.append({
                "role": "tool", "tool_call_id": tc["id"], "content": output,
            })

    # Лимит шагов исчерпан
    return {
        "ok": False,
        "error": f"Превышен лимит шагов ({MAX_STEPS}). Выполнено: {'; '.join(steps)}",
        "steps": steps,
        "provider": provider_used,
        "elapsed": round(time.perf_counter() - total_start, 2),
    }


def run_stream(user_message: str, session_id: str = "default",
               history: list[dict] | None = None):
    """Стриминг без инструментов — быстрый режим для простых вопросов."""
    touch()
    messages: list[dict] = [{"role": "system", "content": tools.SYSTEM_PROMPT}]
    stored = history if history is not None else memory.get_history(session_id)
    for m in stored[-20:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    full: list[str] = []
    try:
        for chunk in llm.stream(messages):
            full.append(chunk)
            yield chunk
    except llm.LLMError as exc:
        yield f"\n\n[Ошибка: {exc}]"
        return

    answer = "".join(full)
    memory.add_message(session_id, "user", user_message)
    memory.add_message(session_id, "assistant", answer)