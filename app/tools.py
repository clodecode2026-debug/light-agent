"""Инструменты агента: файлы, веб-поиск, выполнение кода."""
import io
import re
import subprocess
import sys

import httpx

from . import config

WORKSPACE = config.WORKSPACE

SYSTEM_PROMPT = """Ты — лёгкий автономный ИИ-агент. Работаешь в облаке на сервере.

Твои возможности:
- Создаёшь, читаешь и правишь файлы в рабочей папке.
- Создаёшь и удаляешь папки, перемещаешь и переименовываешь файлы.
- Ищешь информацию в интернете.
- Выполняешь Python-код для вычислений и проверки гипотез.
- Сохраняешь файлы в облачное хранилище.
- Работаешь с файлами, которые пользователь загрузил через интерфейс.

Правила работы:
1. Файлы создаёт и изменяет ТОЛЬКО через инструменты. В ответе описывай результат словами, а не кодом в блоке.
2. Код запускай через инструмент execute_code или run_python_file, а не предлагай пользователю запустить его самому.
3. Если задача требует нескольких шагов - выполняй их по очереди, а не описывай будущие шаги вместо выполнения.
4. Создавая проект, сначала сделай папки через make_dir, потом файлы внутри них.
5. Чтобы посмотреть структуру проекта, вызывай tree, а не list_files.
6. Отвечай кратко и по делу, на языке пользователя.
7. Не выдумывай результаты инструментов: если инструмент вернул ошибку - сообщи об этом.
"""

_DANGEROUS = re.compile(
    r"(rm\s+-rf|:\(\)\s*\{|mkfs|dd\s+if=|shutdown|reboot|"
    r"curl\s+.*\|\s*(ba)?sh|wget\s+.*\|\s*(ba)?sh)",
    re.IGNORECASE,
)

SEARCH_URL = "https://html.duckduckgo.com/html/?q={}"


def _safe_path(rel: str) -> str:
    """Путь внутри рабочей папки — защита от выхода за её пределы."""
    if not rel or not rel.strip():
        raise ValueError("Путь не указан")
    if ".." in rel or rel.startswith("/") or ":" in rel:
        raise ValueError("Недопустимый путь")
    full = (WORKSPACE / rel).resolve()
    if not str(full).startswith(str(WORKSPACE.resolve())):
        raise ValueError("Путь выходит за пределы рабочей папки")
    return full


# ---------------- Файлы ----------------

def tool_write_file(path: str, content: str) -> str:
    """Создаёт или перезаписывает текстовый файл в рабочей папке."""
    try:
        full = _safe_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        size = len(content.encode("utf-8"))
        return f"Записан файл {path} ({size} байт)"
    except Exception as exc:
        return f"Ошибка записи: {exc}"


def tool_read_file(path: str) -> str:
    """Читает текстовый файл из рабочей папки."""
    try:
        full = _safe_path(path)
        if not full.exists():
            return f"Файл не найден: {path}"
        data = full.read_text(encoding="utf-8", errors="replace")
        if len(data) > 40000:
            return f"{path}\n\n[файл обрезан до 40000 символов]\n{data[:40000]}"
        return f"{path}\n\n{data}"
    except Exception as exc:
        return f"Ошибка чтения: {exc}"


def tool_list_files(directory: str = ".") -> str:
    """Показывает список файлов и папок в рабочей директории."""
    try:
        full = _safe_path(directory or ".")
        if not full.exists():
            return f"Директория не найдена: {directory}"
        entries = sorted(full.iterdir())
        if not entries:
            return f"{directory} — пусто"
        lines = []
        for e in entries[:200]:
            if e.is_dir():
                lines.append(f"[dir]  {e.name}/")
            else:
                lines.append(f"       {e.name} ({e.stat().st_size} Б)")
        return "\n".join(lines)
    except Exception as exc:
        return f"Ошибка: {exc}"


def tool_delete_file(path: str) -> str:
    """Удаляет файл из рабочей папки."""
    try:
        full = _safe_path(path)
        if full.is_dir():
            return "Это папка - используй delete_dir"
        if not full.exists():
            return f"Файл не найден: {path}"
        full.unlink()
        return f"Удалён файл {path}"
    except Exception as exc:
        return f"Ошибка удаления: {exc}"


# ---------------- Папки ----------------

def tool_make_dir(path: str) -> str:
    """Создаёт папку вместе с промежуточными."""
    try:
        full = _safe_path(path)
        if full.is_dir():
            return f"Папка уже существует: {path}"
        if full.exists():
            return f"По этому пути уже есть файл: {path}"
        full.mkdir(parents=True, exist_ok=True)
        return f"Создана папка: {path}"
    except Exception as exc:
        return f"Ошибка создания папки: {exc}"


def tool_delete_dir(path: str, recursive: bool = False) -> str:
    """Удаляет папку. Непустую - только с recursive."""
    try:
        full = _safe_path(path)
        if not full.is_dir():
            return f"Это не папка: {path}"
        if any(full.iterdir()) and not recursive:
            return (f"Папка {path} не пустая. Повтори с recursive=true, "
                    f"если нужно удалить её целиком.")
        import shutil
        if recursive:
            shutil.rmtree(full)
        else:
            full.rmdir()
        return f"Удалена папка: {path}"
    except Exception as exc:
        return f"Ошибка удаления папки: {exc}"


def tool_move_file(source: str, destination: str) -> str:
    """Перемещает или переименовывает файл."""
    try:
        src = _safe_path(source)
        dst = _safe_path(destination)
        if not src.exists():
            return f"Не найдено: {source}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_dir():
            dst = dst / src.name
        src.replace(dst)
        return f"Перемещено: {source} -> {dst.relative_to(WORKSPACE)}"
    except Exception as exc:
        return f"Ошибка перемещения: {exc}"


def tool_tree(path: str = ".", max_depth: int = 3) -> str:
    """Показывает дерево файлов и папок."""
    try:
        root = _safe_path(path or ".")
        if not root.exists():
            return f"Не найдено: {path}"

        out = [f"{path or '.'}/"]

        def walk(d, depth: int) -> None:
            if depth > max_depth:
                out.append("  " * depth + "...")
                return
            try:
                entries = sorted(d.iterdir(),
                                 key=lambda p: (not p.is_dir(), p.name.lower()))
            except Exception:
                return
            for e in entries:
                indent = "  " * depth + ("+-- " if depth else "|   ")
                if e.is_dir():
                    out.append(f"{indent}{e.name}/")
                    walk(e, depth + 1)
                else:
                    out.append(f"{indent}{e.name} ({e.stat().st_size} Б)")

        walk(root, 1)
        return "\n".join(out[:400])
    except Exception as exc:
        return f"Ошибка: {exc}"


# ---------------- Выполнение кода ----------------

def tool_execute_code(code: str) -> str:
    """Выполняет Python-код и возвращает результат. Для вычислений и проверки."""
    if _DANGEROUS.search(code):
        return "Отклонено: код содержит опасную конструкцию"
    try:
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(  # noqa: S102 - намеренный sandbox на уровне строк
                compile(code, "<agent>", "exec"),
                {"__name__": "__main__"},
            )
        out = buf.getvalue()
        return out[-8000:] if out else "Код выполнен, вывода нет"
    except Exception:
        import traceback
        return traceback.format_exc()[-3000:]


def tool_run_python_file(path: str) -> str:
    """Запускает существующий Python-файл из рабочей папки."""
    try:
        full = _safe_path(path)
        if not full.exists():
            return f"Файл не найден: {path}"
        proc = subprocess.run(
            [sys.executable, str(full)], cwd=str(WORKSPACE),
            capture_output=True, text=True, timeout=120,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return f"[код {proc.returncode}]\n{output[-8000:]}"
    except subprocess.TimeoutExpired:
        return "Таймаут выполнения (120 сек)"
    except Exception as exc:
        return f"Ошибка запуска: {exc}"


# ---------------- Веб ----------------

def tool_web_search(query: str, max_results: int = 5) -> str:
    """Ищет информацию в интернете и возвращает сниппеты результатов."""
    try:
        with httpx.Client(timeout=20, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (agent)"}) as c:
            resp = c.get("https://html.duckduckgo.com/html/",
                         params={"q": query})
        html = resp.text
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        links = re.findall(r'class="result__a"[^>]*href="(.*?)"', html, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)

        def clean(s: str) -> str:
            return re.sub(r"<.*?>", "", s).strip()

        out = []
        for i, title in enumerate(titles[:max_results]):
            snippet = clean(snippets[i]) if i < len(snippets) else ""
            url = links[i] if i < len(links) else ""
            out.append(f"{i + 1}. {clean(title)}\n   {url}\n   {snippet[:300]}")
        return "\n\n".join(out) if out else "Ничего не найдено"
    except Exception as exc:
        return f"Ошибка поиска: {exc}"


def tool_fetch_url(url: str) -> str:
    """Открывает URL и возвращает текст страницы без HTML-разметки."""
    try:
        with httpx.Client(timeout=20, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (agent)"}) as c:
            resp = c.get(url)
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", resp.text,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<.*?>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:15000] if text else "Пустая страница"
    except Exception as exc:
        return f"Ошибка загрузки: {exc}"


def tool_cloud_upload(filename: str) -> str:
    """Выгружает файл из рабочей папки в облачное хранилище Storj S3."""
    from . import storage
    try:
        full = _safe_path(filename)
        if not full.exists():
            return f"Файл не найден: {filename}"
        key = f"workspace/{filename}"
        storage.upload_file(key, str(full))
        return f"Выгружено в облако: {key} ({full.stat().st_size} Б)"
    except Exception as exc:
        return f"Ошибка выгрузки: {exc}"



def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    """Собирает описание инструмента в формате OpenAI function calling."""
    params: dict = {"type": "object", "properties": properties}
    if required:
        params["required"] = required
    return {"type": "function", "function": {
        "name": name, "description": description, "parameters": params}}


_P = {"type": "string", "description": "Путь относительно рабочей папки"}


def build_tools() -> list[dict]:
    """Описания всех инструментов агента в формате function calling."""
    return [
        _tool("write_file", "Создаёт или перезаписывает текстовый файл.",
              {"path": _P, "content": {"type": "string", "description": "Содержимое файла"}},
              ["path", "content"]),
        _tool("read_file", "Читает текстовый файл. Для просмотра содержимого.",
              {"path": _P}, ["path"]),
        _tool("list_files", "Показывает содержимое директории. По умолчанию '.'.",
              {"directory": {"type": "string", "description": "Директория, по умолчанию '.'"}}),
        _tool("tree", "Показывает дерево файлов и папок - удобно, когда их много.",
              {"path": _P,
               "max_depth": {"type": "integer", "description": "Максимальная глубина, по умолчанию 3"}},
              ["path"]),
        _tool("make_dir", "Создаёт папку, включая промежуточные. Сделай это перед созданием файлов проекта.",
              {"path": _P}, ["path"]),
        _tool("delete_dir", "Удаляет папку. Если непустая - требуется recursive=true.",
              {"path": _P,
               "recursive": {"type": "boolean", "description": "Удалять вместе с содержимым"}},
              ["path"]),
        _tool("move_file", "Перемещает или переименовывает файл.",
              {"source": {"type": "string", "description": "Откуда"},
               "destination": {"type": "string", "description": "Куда"}},
              ["source", "destination"]),
        _tool("delete_file", "Удаляет файл (не папку).",
              {"path": _P}, ["path"]),
        _tool("execute_code", "Выполняет Python-код и возвращает вывод. Для вычислений и проверки гипотез.",
              {"code": {"type": "string"}}, ["code"]),
        _tool("run_python_file", "Запускает Python-файл из рабочей папки и возвращает вывод.",
              {"path": _P}, ["path"]),
        _tool("web_search", "Ищет информацию в интернете.",
              {"query": {"type": "string"},
               "max_results": {"type": "integer", "description": "Сколько результатов (по умолч. 5)"}},
              ["query"]),
        _tool("fetch_url", "Загружает страницу по адресу и возвращает её текст.",
              {"url": {"type": "string"}}, ["url"]),
        _tool("cloud_upload", "Выгружает файл из рабочей папки в облачное хранилище Storj.",
              {"filename": {"type": "string", "description": "Имя файла в рабочей папке"}},
              ["filename"]),
    ]


_REGISTRY: dict[str, object] = {
    "write_file": tool_write_file,
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "tree": tool_tree,
    "make_dir": tool_make_dir,
    "delete_dir": tool_delete_dir,
    "move_file": tool_move_file,
    "delete_file": tool_delete_file,
    "execute_code": tool_execute_code,
    "run_python_file": tool_run_python_file,
    "web_search": tool_web_search,
    "search_web": tool_web_search,
    "search": tool_web_search,
    "fetch_url": tool_fetch_url,
    "cloud_upload": tool_cloud_upload,
}


def execute(name: str, args: dict) -> str:
    """Вызывает инструмент по имени."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return f"Неизвестный инструмент: {name}"
    try:
        return str(fn(**args))
    except TypeError as exc:
        return f"Неверные аргументы для {name}: {exc}"
    except Exception as exc:
        return f"Ошибка инструмента {name}: {exc}"