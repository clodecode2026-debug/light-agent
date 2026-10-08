"""Главный исполнительный цикл агента по архитектуре Claude Code.

Особенности:
- Чистый ReAct-цикл (Reasoning + Acting).
- Поддержка отмены пользователем на лету (cancel).
- Потоковая передача событий (SSE) для красивого отображения в веб-интерфейсе.
- Безопасное сжатие контекста сообщений без потери ключевых целей.
- Защита от зацикливаний на повторяющихся ошибках инструментов.
"""
import threading
import time
from concurrent.futures import Future as _Future
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import config, llm, memory, tools

MAX_STEPS = 500          # Неограниченный простор для масштабного сканирования и работы
MAX_TOOL_OUTPUT = 32000  # До 32 КБ вывода инструмента (хватает для сотен файлов без обрезки)
MAX_LOOP_REPEATS = 4     # Предотвращение зацикливания на одинаковых вызовах

_step_counter = {"count": 0}
_last_activity = {"ts": time.time()}
_active_cancel: dict[str, threading.Event] = {}


def touch() -> None:
    _last_activity["ts"] = time.time()
    _step_counter["count"] = 0


def idle_seconds() -> float:
    return time.time() - _last_activity["ts"]


def state() -> dict:
    return {
        "idle_seconds": round(idle_seconds()),
        "tools_used": _step_counter["count"],
        "running_jobs": len(_active_cancel),
    }


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] [ClaudeCode] {msg}", flush=True)


def cancel(session_id: str) -> bool:
    ev = _active_cancel.get(session_id)
    if ev is None:
        return False
    ev.set()
    _log(f"Cancel requested for session: {session_id}")
    return True


def _build_messages(session_id: str, user_message: str,
                    history: list[dict] | None, project: str = "default") -> list[dict]:
    """Собирает контекст сообщений с актуальным системным промптом."""
    system_prompt = tools.get_claude_system_prompt(project)
    messages: list[dict] = []

    if history is not None:
        for m in history[-24:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})
    else:
        built = memory.build_context(session_id, user_message, project=project)
        for m in built[:-1]:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})

    messages.insert(0, {"role": "system", "content": system_prompt})
    return messages


def run(user_message: str, session_id: str = "default",
        history: list[dict] | None = None,
        on_event=None, cancel_event: threading.Event | None = None,
        project: str = "default", model: str | None = None) -> dict:
    """Главный цикл выполнения задачи."""
    if cancel_event is None:
        cancel_event = _active_cancel.setdefault(session_id, threading.Event())

    def emit(kind: str, payload: dict) -> None:
        if on_event is None:
            return
        try:
            on_event(kind, payload)
        except Exception:
            pass

    config.set_current_project(project)
    touch()
    messages = _build_messages(session_id, user_message, history, project=project)
    memory.add_message(session_id, "user", user_message, project=project)

    tool_specs = tools.build_tools()
    steps_log: list[str] = []
    provider_used = ""
    total_start = time.perf_counter()
    call_signatures: dict[str, int] = {}
    max_steps_allowed = MAX_STEPS

    try:
        step = 0
        while step < max_steps_allowed:
            step += 1
            if cancel_event.is_set():
                return {
                    "ok": False, "cancelled": True,
                    "error": "Задача отменена пользователем",
                    "answer": "⏹ Задача отменена пользователем.",
                    "steps": steps_log, "provider": provider_used,
                    "elapsed": round(time.perf_counter() - total_start, 2),
                }

            emit("step", {"index": step, "max": max_steps_allowed})

            # Умное сжатие контекста при разрастании цепочки сообщений (>26 сообщений)
            if len(messages) > 26:
                # Сохраняем системный промпт, первое сообщение пользователя и последние 16 реплик
                condensed_summary = {
                    "role": "user",
                    "content": f"[System Context: Ранее выполненные шаги (всего {step} шагов): " +
                               "; ".join(steps_log[-6:]) + "]"
                }
                messages = [messages[0], messages[1], condensed_summary] + messages[-16:]

            try:
                resp = llm.chat(messages, tools=tool_specs, model=model, temperature=0.2)
            except llm.LLMError as exc:
                _log(f"LLM Error: {exc}")
                return {
                    "ok": False, "error": str(exc),
                    "answer": f"⚠️ Ошибка сервиса модели: {exc}",
                    "steps": steps_log,
                    "elapsed": round(time.perf_counter() - total_start, 2),
                }

            provider_used = resp["provider"]

            # Если модель не вызвала инструменты — это финальный ответ
            if not resp.get("tool_calls"):
                answer = (resp.get("content") or "").strip() or "Готово."
                memory.add_message(session_id, "assistant", answer, project=project)
                _log(f"Completed in {round(time.perf_counter() - total_start, 2)}s, steps: {step}")
                return {
                    "ok": True, "answer": answer, "steps": steps_log,
                    "provider": provider_used,
                    "elapsed": round(time.perf_counter() - total_start, 2),
                }

            # Добавляем реплику ассистента с вызовами инструментов
            messages.append({
                "role": "assistant",
                "content": resp.get("content") or "",
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": tc.get("raw") or "{}"}}
                    for tc in resp["tool_calls"]
                ],
            })

            loop_detected = False
            for tc in resp["tool_calls"]:
                if cancel_event.is_set():
                    break

                tname = tc["name"]
                targs = tc.get("args") or {}
                sig = f"{tname}:{tc.get('raw', '')}"
                call_signatures[sig] = call_signatures.get(sig, 0) + 1

                if call_signatures[sig] >= MAX_LOOP_REPEATS:
                    loop_detected = True
                    _log(f"Loop detected on tool {tname} ({call_signatures[sig]} repeats)")

                preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in list(targs.items())[:3])
                emit("tool", {"name": tname, "args": targs, "preview": preview})
                _log(f"Tool call: {tname}({preview})")

                if loop_detected:
                    output = (
                        f"⛔ Предупреждение: Инструмент {tname} вызван повторно с теми же аргументами уже {call_signatures[sig]} раз. "
                        f"Остановитесь, смените подход или дайте ответ пользователю."
                    )
                else:
                    output = tools.execute(tname, targs)

                trimmed = output[:MAX_TOOL_OUTPUT]
                if len(output) > MAX_TOOL_OUTPUT:
                    trimmed += f"\n...[обрезано, всего было {len(output)} символов]"

                steps_log.append(f"{tname}: {output[:140]}")
                _step_counter["count"] += 1
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": trimmed,
                })

            # Динамическое расширение лимита шагов при продуктивной работе (практически без лимита)
            if step >= max_steps_allowed - 2 and not loop_detected and max_steps_allowed < 2000:
                max_steps_allowed += 50
                _log(f"Extended max_steps to {max_steps_allowed}")

        err_msg = f"Выполнен максимальный лимит шагов ({max_steps_allowed})."
        recent = ("\nПоследние операции:\n" + "\n".join(f"- {s}" for s in steps_log[-5:])) if steps_log else ""
        return {
            "ok": False,
            "error": err_msg,
            "answer": f"⚠️ {err_msg}{recent}\n\nНапишите «продолжай», если требуется продолжить работу.",
            "steps": steps_log,
            "provider": provider_used,
            "elapsed": round(time.perf_counter() - total_start, 2),
        }
    finally:
        _active_cancel.pop(session_id, None)


def run_stream(user_message: str, session_id: str = "default",
               history: list[dict] | None = None, project: str = "default",
               model: str | None = None):
    """Стриминг текста без инструментов."""
    config.set_current_project(project)
    touch()
    messages = _build_messages(session_id, user_message, history, project=project)

    full: list[str] = []
    try:
        for chunk in llm.stream(messages, model=model):
            full.append(chunk)
            yield chunk
    except llm.LLMError as exc:
        yield f"\n\n[Ошибка: {exc}]"
        return

    answer = "".join(full).strip()
    if answer:
        memory.add_message(session_id, "assistant", answer, project=project)


# Пул потоков для выполнения задач агента
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="claude_agent")


def submit(session_id: str, message: str, history=None,
           on_event=None, project: str = "default",
           model: str | None = None) -> "Job":
    """Запускает задачу агента в пуле потоков."""
    ev = threading.Event()
    _active_cancel[session_id] = ev
    fut = _pool.submit(run, message, session_id, history, on_event, ev, project, model)
    return Job(fut, session_id)


class Job:
    """Обёртка над Future с возможностью отмены."""

    def __init__(self, fut: _Future, session_id: str):
        self._fut = fut
        self._session_id = session_id

    def done(self) -> bool:
        return self._fut.done()

    def result(self, timeout: float | None = None) -> dict:
        return self._fut.result(timeout=timeout)

    def cancel(self) -> bool:
        return cancel(self._session_id)