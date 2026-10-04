"""Хранение истории диалогов в Supabase.

Если Supabase не настроен — агент работает без постоянной памяти,
используя только переданную в запросе историю.
"""
from datetime import datetime, timezone

from . import config

_client = None
_unavailable = False

TABLE = "agent_messages"


def _get_client():
    global _client, _unavailable
    if _unavailable:
        return None
    if _client is not None:
        return _client
    if not config.memory_enabled():
        _unavailable = True
        return None
    try:
        from supabase import create_client

        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        return _client
    except Exception:
        _unavailable = True
        return None


def ensure_schema() -> bool:
    """Проверяет, что таблица сообщений доступна.

    Создавать её нужно один раз вручную в Supabase SQL Editor: у клиента
    нет прав на DDL, а RPC exec в Supabase не существует. Поэтому здесь
    мы только проверяем доступ и создаём таблицу, если она уже есть.
    """
    client = _get_client()
    if client is None:
        return False
    try:
        client.table(TABLE).select("id").limit(1).execute()
        return True
    except Exception:
        return False


def add_message(session_id: str, role: str, content: str) -> bool:
    client = _get_client()
    if client is None:
        return False
    try:
        client.table("agent_messages").insert({
            "session_id": session_id, "role": role, "content": content[:8000],
        }).execute()
        return True
    except Exception:
        return False


def get_history(session_id: str, limit: int = 20) -> list[dict]:
    """Последние сообщения сессии в порядке возрастания."""
    client = _get_client()
    if client is None:
        return []
    try:
        resp = (
            client.table("agent_messages")
            .select("role, content")
            .eq("session_id", session_id)
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        rows = resp.data or []
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    except Exception:
        return []


def clear_session(session_id: str) -> bool:
    client = _get_client()
    if client is None:
        return False
    try:
        client.table("agent_messages").delete().eq("session_id", session_id).execute()
        return True
    except Exception:
        return False


def status() -> dict:
    return {
        "enabled": _get_client() is not None,
        "service": "supabase",
    }


# ---------------------------------------------------------------------------
# Сжатие истории
# ---------------------------------------------------------------------------
# Зачем: история растёт бесконечно, и каждый запрос начинает платить за всю
# переписку. Обрезать нельзя - агент забудет важное. Поэтому старые сообщения
# не удаляются, а сворачиваются в короткий пересказ: что просил пользователь
# и что получилось. Свежие сообщения остаются дословно.

RECENT_MESSAGES = 12     # сколько последних сообщений идёт дословно
MAX_SUMMARY_CHARS = 2600  # предел длины сводки
MAX_FACT_CHARS = 220     # предел одной строки в сводке


def _condense(text: str, limit: int = MAX_FACT_CHARS) -> str:
    """Одна строка-пересказ: первая фраза плюс длина."""
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[:limit].rsplit(" ", 1)[0] + "..."


def _build_summary(old: list[dict]) -> str:
    """Собирает сводку по сообщениям, которые не попали в окно свежих.

    Ответы агента вида "OK" и "18" бесполезны и только тратят место,
    поэтому они выбрасываются. Важны запросы пользователя и содержательные
    ответы - именно в них факты.
    """
    facts: list[str] = []
    for m in old:
        text = m.get("content", "")
        # Ответы агента почти всегда короткие служебные - не факт
        if m.get("role") != "user" and len(text.strip()) < 40:
            continue
        role = "Пользователь" if m.get("role") == "user" else "Агент"
        line = _condense(text)
        if line:
            facts.append(f"- {role}: {line}")

    if not facts:
        return ""

    summary = ("Пользователь ранее говорил (сжато). Используй эти факты, "
               "когда он про них спрашивает:\n") + "\n".join(facts)
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[:MAX_SUMMARY_CHARS].rsplit("\n", 1)[0] + "\n- ..."
    return summary


def build_context(session_id: str, user_message: str,
                  recent: int = RECENT_MESSAGES) -> list[dict]:
    """Готовит сообщения для LLM: сводка + свежие сообщения + новый вопрос.

    Возвращает список ровно в формате OpenAI Chat Completions.
    """
    # Забираем с запасом: часть пойдёт в сводку, часть - дословно.
    # limit считается по строкам, а нужен запас на 3x, иначе старая
    # история обрезается и факты из неё теряются.
    stored = get_history(session_id, limit=recent * 4)

    messages: list[dict] = []
    if len(stored) <= recent:
        fresh, old = stored, []
    else:
        fresh, old = stored[-recent:], stored[:-recent]

    summary = _build_summary(old)
    if summary:
        # Как системная вставка: факты из прошлого, без новых инструкций.
        messages.append({
            "role": "system",
            "content": "ИЗ БОЛЕЕ РАННЕГО РАЗГОВОРА (сжато, чтобы не повторять "
                       "дословно). Это факты из прошлого - используй их, когда "
                       "пользователь про них спрашивает:\n" + summary,
        })

    for m in fresh:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages


def stats(session_id: str) -> dict:
    """Сколько всего сообщений в сессии."""
    client = _get_client()
    if client is None:
        return {"messages": 0}
    try:
        resp = (client.table(TABLE)
                .select("id", count="exact")
                .eq("session_id", session_id)
                .execute())
        return {"messages": resp.count or 0}
    except Exception:
        return {"messages": 0}