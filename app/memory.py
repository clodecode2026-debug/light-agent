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