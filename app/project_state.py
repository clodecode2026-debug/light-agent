"""Архитектурный паспорт проекта (Project State Memory).

Хранит постоянную память о проекте:
- Основная цель и назначение
- Стек технологий
- Структура ключевых файлов
- Принятые архитектурные решения
- Текущий статус и следующий шаг

Сохраняется в двух местах:
1. В корне проекта в файле `.project_state.json` и читаемом `PROJECT.md`.
2. В Supabase (если подключен), чтобы память сохранялась при любых перезапусках сервера.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

DEFAULT_STATE: dict[str, Any] = {
    "goal": "Разработка проекта",
    "tech_stack": [],
    "architecture": {},
    "key_decisions": [],
    "current_status": "В процессе разработки",
    "updated_at": "",
}


def _get_project_dir(project: str = "") -> Path:
    proj = (project or config.get_current_project() or "default").strip() or "default"
    p = config.project_dir(proj)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_state(project: str = "") -> dict[str, Any]:
    """Загружает паспорт проекта из .project_state.json или создаёт по умолчанию."""
    pdir = _get_project_dir(project)
    fpath = pdir / ".project_state.json"
    if fpath.is_file():
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = dict(DEFAULT_STATE)
                merged.update(data)
                return merged
        except Exception:
            pass

    # Если файла ещё нет, пробуем автодетект по существующим файлам
    state = dict(DEFAULT_STATE)
    proj_name = (project or config.get_current_project() or "default").strip()
    state["project_name"] = proj_name

    detected_stack = []
    files = {}
    for item in pdir.iterdir():
        if item.name.startswith(".") or item.name in ("__pycache__", "venv"):
            continue
        if item.name.endswith(".py"):
            detected_stack.append("Python")
            files[item.name] = "Python модуль"
        elif item.name in ("package.json", "index.html", "app.js"):
            detected_stack.append("JavaScript/Web")
            files[item.name] = "Web компонент"
        elif item.name.endswith(".json"):
            files[item.name] = "JSON конфигурация/данные"

    if detected_stack:
        state["tech_stack"] = list(dict.fromkeys(detected_stack))
    if files:
        state["architecture"] = files

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state, project=project)
    return state


def save_state(state: dict[str, Any], project: str = "") -> None:
    """Сохраняет паспорт в .project_state.json, в PROJECT.md и в Supabase."""
    pdir = _get_project_dir(project)
    proj_name = (project or config.get_current_project() or "default").strip()
    state["project_name"] = proj_name
    state["updated_at"] = datetime.now(timezone.utc).isoformat()

    # 1. Локальный JSON
    fpath = pdir / ".project_state.json"
    try:
        fpath.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 2. Читаемый человеком PROJECT.md в корне проекта
    md_path = pdir / "PROJECT.md"
    try:
        md_content = _generate_markdown(state)
        md_path.write_text(md_content, encoding="utf-8")
    except Exception:
        pass

    # 3. Синхронизация в Supabase (если доступен)
    try:
        from . import memory
        client = memory._get_client()
        if client:
            client.table("agent_facts").upsert({
                "key": f"passport:{proj_name}",
                "value": json.dumps(state, ensure_ascii=False),
                "project": proj_name,
                "updated_at": state["updated_at"],
            }).execute()
    except Exception:
        pass


def _generate_markdown(state: dict[str, Any]) -> str:
    """Генерирует аккуратный Markdown файл паспорта проекта."""
    lines = [
        f"# Паспорт проекта: {state.get('project_name', 'Проект')}",
        "",
        f"**Цель:** {state.get('goal', '—')}",
        "",
        f"**Статус:** {state.get('current_status', '—')}",
        f"**Обновлено:** {state.get('updated_at', '—')[:19].replace('T', ' ')} UTC",
        "",
        "## Стек технологий",
    ]
    stack = state.get("tech_stack") or []
    if isinstance(stack, list) and stack:
        lines.append(", ".join(f"`{s}`" for s in stack))
    elif isinstance(stack, str) and stack:
        lines.append(stack)
    else:
        lines.append("—")

    lines.extend(["", "## Ключевые файлы и модули"])
    arch = state.get("architecture") or {}
    if arch and isinstance(arch, dict):
        for fname, desc in arch.items():
            lines.append(f"- **`{fname}`**: {desc}")
    else:
        lines.append("—")

    lines.extend(["", "## Принятые решения"])
    decisions = state.get("key_decisions") or []
    if isinstance(decisions, list) and decisions:
        for d in decisions:
            lines.append(f"- {d}")
    elif isinstance(decisions, str) and decisions:
        lines.append(decisions)
    else:
        lines.append("—")

    lines.append("")
    return "\n".join(lines)


def format_passport_prompt(project: str = "") -> str:
    """Генерирует компактную сводку паспорта для системного промпта (~200 токенов)."""
    state = load_state(project)
    proj_name = state.get("project_name") or (project or "default")

    goal = state.get("goal") or "Разработка"
    status = state.get("current_status") or "В процессе"

    stack = state.get("tech_stack")
    if isinstance(stack, list):
        stack_str = ", ".join(stack) if stack else "не указан"
    else:
        stack_str = str(stack) or "не указан"

    arch_lines = []
    arch = state.get("architecture") or {}
    if isinstance(arch, dict):
        for k, v in list(arch.items())[:12]:
            arch_lines.append(f"  • {k}: {v}")
    arch_str = "\n".join(arch_lines) if arch_lines else "  • файлов пока нет"

    dec_lines = []
    decisions = state.get("key_decisions") or []
    if isinstance(decisions, list):
        for d in decisions[:8]:
            dec_lines.append(f"  • {d}")
    elif isinstance(decisions, str) and decisions:
        dec_lines.append(f"  • {decisions}")
    dec_str = "\n".join(dec_lines) if dec_lines else "  • нет специальных ограничений"

    return (
        f"=== АРХИТЕКТУРНЫЙ ПАСПОРТ ПРОЕКТА '{proj_name}' ===\n"
        f"🎯 ЦЕЛЬ: {goal}\n"
        f"🛠 СТЕК: {stack_str}\n"
        f"📌 СТАТУС: {status}\n"
        f"📁 КЛЮЧЕВЫЕ ФАЙЛЫ:\n{arch_str}\n"
        f"💡 ПРИНЯТЫЕ РЕШЕНИЯ:\n{dec_str}\n"
        f"ПОМНИ ЭТИ ДАННЫЕ И НЕ ТЕРЯЙ КОНТЕКСТ ПРОЕКТА!\n"
        f"=================================================="
    )


def update_state(
    goal: str = "",
    tech_stack: str = "",
    decisions: str = "",
    status: str = "",
    files_summary: str = "",
    project: str = "",
) -> dict[str, Any]:
    """Точечно обновляет поля паспорта проекта."""
    state = load_state(project)

    if (goal or "").strip():
        state["goal"] = goal.strip()

    if (tech_stack or "").strip():
        raw_items = [s.strip() for s in tech_stack.split(",") if s.strip()]
        current = state.get("tech_stack") or []
        if isinstance(current, list):
            for it in raw_items:
                if it not in current:
                    current.append(it)
            state["tech_stack"] = current
        else:
            state["tech_stack"] = raw_items

    if (status or "").strip():
        state["current_status"] = status.strip()

    if (decisions or "").strip():
        new_decs = [d.strip() for d in decisions.split(";") if d.strip()]
        current_decs = state.get("key_decisions") or []
        if isinstance(current_decs, list):
            for nd in new_decs:
                if nd not in current_decs:
                    current_decs.append(nd)
            state["key_decisions"] = current_decs
        else:
            state["key_decisions"] = new_decs

    if (files_summary or "").strip():
        arch = state.get("architecture") or {}
        if not isinstance(arch, dict):
            arch = {}
        for part in files_summary.split(";"):
            part = part.strip()
            if ":" in part:
                fname, desc = part.split(":", 1)
                arch[fname.strip()] = desc.strip()
        state["architecture"] = arch

    save_state(state, project=project)
    return state


def auto_record_file(path: str, summary: str = "", project: str = "") -> None:
    """Автоматически регистрирует созданный файл в паспорте."""
    fname = Path(path).name
    if fname.startswith(".") or fname in ("PROJECT.md", ".project_state.json"):
        return
    state = load_state(project)
    arch = state.get("architecture") or {}
    if not isinstance(arch, dict):
        arch = {}

    if fname not in arch:
        arch[fname] = summary or f"Файл {Path(path).suffix}"
        state["architecture"] = arch
        save_state(state, project=project)


# ---------------- Инструменты агента ----------------

def tool_project_state_get(project: str = "") -> str:
    """Возвращает текущий архитектурный паспорт проекта."""
    state = load_state(project)
    return _generate_markdown(state)


def tool_project_state_update(
    goal: str = "",
    tech_stack: str = "",
    decisions: str = "",
    status: str = "",
    files_summary: str = "",
) -> str:
    """Обновляет архитектурный паспорт проекта (цель, стек, ключевые файлы, решения, статус).
    Используй при начале проекта, при принятии архитектурных решений или смене статуса разработки,
    чтобы агент никогда не забывал контекст.

    Параметры:
      goal — цель или назначение проекта
      tech_stack — список технологий через запятую (например: 'FastAPI, SQLite, Tailwind')
      decisions — новые принятые архитектурные решения через точку с запятой (например: 'Вход только через Telegram; Храним пароли в bcrypt')
      status — текущий статус (например: 'Сделали модели БД, пишем эндпоинты')
      files_summary — описание файлов через точку с запятой (например: 'auth.py: токены; main.py: запуск API')
    """
    updated = update_state(
        goal=goal,
        tech_stack=tech_stack,
        decisions=decisions,
        status=status,
        files_summary=files_summary,
    )
    return (
        f"✅ Паспорт проекта обновлён!\n\n"
        f"{_generate_markdown(updated)}"
    )
