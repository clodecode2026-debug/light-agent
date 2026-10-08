"""Инструменты агента и системный промпт по официальному стандарту Claude Code.

Набор инструментов:
- bash: Выполнение команд терминала (git, pip, python, curl, тесты, скрипты).
- view: Просмотр файлов с номерами строк и срезами.
- edit: Хирургическая точечная замена блоков кода (old_str -> new_str).
- write: Создание или перезапись файлов.
- glob: Поиск файлов по маске.
- grep: Поиск по содержимому файлов через регулярные выражения.
- agent: Делегирование задач специализированным субагентам (researcher, coder, tester, devops, general).
- todo: Ведение чеклиста задач.
- web_search / fetch_url: Поиск и чтение информации в интернете.
"""
import ast
import difflib
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

from . import config
from . import subagent as _subagent

WORKSPACE = config.WORKSPACE


def _ws() -> Path:
    """Папка активного проекта."""
    return config.current_workspace()


def _safe_path(rel: str, project: str = "") -> Path:
    """Путь внутри рабочей папки проекта с защитой от directory traversal."""
    if not rel or not rel.strip():
        raise ValueError("Путь не указан")
    if ".." in rel or rel.startswith("/") or ":" in rel:
        raise ValueError("Недопустимый путь (выход за пределы проекта)")
    base = config.project_dir(project) if project else _ws()
    full = (base / rel).resolve()
    if not str(full).startswith(str(base.resolve())):
        raise ValueError("Путь выходит за пределы папки проекта")
    return full


# Расширения изображений для веб-интерфейса
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}
IMAGE_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".svg": "image/svg+xml", ".ico": "image/x-icon",
}


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXT


def image_mime(path: str) -> str:
    return IMAGE_MIME.get(Path(path).suffix.lower(), "application/octet-stream")


# ---------------- Синтаксическая валидация ----------------

def _lint_content(path: str, content: str) -> str | None:
    """Быстрая валидация синтаксиса при сохранении."""
    ext = Path(path).suffix.lower()
    if ext == ".py":
        try:
            ast.parse(content, filename=path)
        except SyntaxError as e:
            line_text = f"\n   Строка {e.lineno}: {e.text.strip()}" if e.text else ""
            return f"SyntaxError в строке {e.lineno}, символ {e.offset}: {e.msg}{line_text}"
    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return f"JSONDecodeError: строка {e.lineno}, символ {e.colno}: {e.msg}"
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        brackets = {"(": ")", "[": "]", "{": "}"}
        stack = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            for ch in line:
                if ch in brackets:
                    stack.append((ch, line_num))
                elif ch in brackets.values():
                    if not stack:
                        return f"Лишняя закрывающая скобка '{ch}' на строке {line_num}"
                    top, start_line = stack.pop()
                    if brackets[top] != ch:
                        return f"Несоответствие скобок: открыта '{top}' на строке {start_line}, закрыта '{ch}' на строке {line_num}"
        if stack:
            top, start_line = stack[-1]
            return f"Незакрытая скобка '{top}' на строке {start_line}"
    return None


# ---------------- Инструменты Claude Code ----------------

def tool_bash(command: str, timeout: int = 60) -> str:
    """Выполняет команду Bash в рабочей папке проекта."""
    command = (command or "").strip()
    if not command:
        return "Ошибка: пустая команда."

    # Собираем окружение (наследуем системное + переменные из .env)
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["PYTHONUNBUFFERED"] = "1"

    ws_dir = _ws()
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=str(ws_dir),
            capture_output=True,
            text=True,
            timeout=max(5, min(timeout, 600)),
            env=env,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        out = []
        if stdout:
            out.append(stdout)
        if stderr:
            out.append(f"[stderr]\n{stderr}")
        combined = "\n".join(out) if out else "(нет вывода)"
        
        # Обрезаем только при экстремально больших логах (> 32 КБ)
        if len(combined) > 32000:
            combined = combined[:16000] + f"\n...[вывод сокращен, всего {len(combined)} символов]...\n" + combined[-16000:]
            
        status_note = f"[Exit code: {proc.returncode}]" if proc.returncode != 0 else ""
        return f"{status_note}\n{combined}".strip()
    except subprocess.TimeoutExpired:
        return f"Таймаут выполнения команды ({timeout} сек)."
    except Exception as exc:
        return f"Ошибка запуска bash: {exc}"


def _ocr_and_describe_image(full_path: Path, rel_path: str, custom_prompt: str = "") -> str:
    """Извлекает текст (OCR) и визуальное описание скана/изображения через Vision API."""
    try:
        import base64
        import httpx

        raw_bytes = full_path.read_bytes()
        size = len(raw_bytes)
        if size > 6_000_000:
            return f"Изображение {rel_path} ({size} байт) слишком большое для прямого OCR (макс. 6 МБ)."

        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        mime = image_mime(str(full_path))
        
        headers = {
            "Authorization": f"Bearer {config.AG_API_KEY}",
            "Content-Type": "application/json",
        }
        url = f"{config.AG_BASE_URL.rstrip('/')}/chat/completions"
        prompt = custom_prompt.strip() if custom_prompt else (
            "Ты — высококвалифицированный аналитик документов, медицинских сканов и изображений. "
            "Внимательно изучи прикреплённое изображение. "
            "1. Сделай полный и точный OCR: выпиши ВЕСЬ текст на картинке дословно, ничего не пропуская: "
            "медицинские заключения (Befund, Beurteilung, Diagnose, МРТ, КТ, УЗИ), диагнозы, параметры, сегменты (L4, L5, S1 и др.), числа, заключения врачей, печати. "
            "2. Если это медицинский скан (МРТ, рентген, КТ) или диаграмма — опиши видимые патологии и анатомические структуры. "
            "3. Сделай структурированный вывод и резюме на русском языке."
        )

        # Модели с активной поддержкой Vision на шлюзе
        for vision_model in ["gpt-4o", "gemini-3.8-flash", "claude-3-5-sonnet-20241022"]:
            try:
                r = httpx.post(
                    url,
                    headers=headers,
                    json={
                        "model": vision_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                                ]
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.2
                    },
                    timeout=40.0
                )
                if r.status_code == 200:
                    ans = r.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if ans:
                        return f"=== РАСПОЗНАННЫЙ ТЕКСТ И АНАЛИЗ СКАНА/ИЗОБРАЖЕНИЯ {rel_path} ({size} байт, модель: {vision_model}) ===\n{ans}"
            except Exception:
                continue
        return f"Изображение {rel_path} ({size} байт, mime: {mime}). OCR-модуль не вернул распознанный текст."
    except Exception as exc:
        return f"Ошибка OCR-анализа изображения {rel_path}: {exc}"


def tool_view(path: str, view_range: list[int] | None = None) -> str:
    """Читает файл (текст, код, изображения/сканы с OCR, docx, pdf) с номерами строк."""
    try:
        full = _safe_path(path)
        if not full.exists():
            return f"Файл не найден: {path}"
        if full.is_dir():
            entries = sorted(full.iterdir())
            lines = [f"Директория: {path}/"]
            for e in entries[:150]:
                lines.append(f"  {'[DIR] ' if e.is_dir() else '      '}{e.name}")
            return "\n".join(lines)

        # Распознавание изображений и сканов через Vision/OCR
        if is_image(str(full)):
            size = full.stat().st_size
            if full.suffix.lower() == ".svg":
                text = full.read_text(encoding="utf-8", errors="replace")
                return f"SVG-изображение {path} ({size} байт):\n{text[:3000]}"
            return _ocr_and_describe_image(full, path)

        # Чтение документов DOCX
        if full.suffix.lower() == ".docx":
            import zipfile
            import xml.etree.ElementTree as ET
            try:
                with zipfile.ZipFile(str(full)) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    texts = [node.text for node in tree.iter() if node.text]
                    doc_text = "\n".join(" ".join(texts).split("  "))
                    return f"=== Документ DOCX {path} ===\n{doc_text[:20000]}"
            except Exception as exc:
                return f"Ошибка чтения docx {path}: {exc}"

        # Чтение документов PDF
        if full.suffix.lower() == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(full))
                pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
                if pdf_text.strip():
                    return f"=== Текст PDF документа {path} ({len(reader.pages)} стр.) ===\n{pdf_text[:20000]}"
            except Exception:
                pass

        raw = full.read_text(encoding="utf-8", errors="replace")
        all_lines = raw.splitlines()
        total_lines = len(all_lines)

        start = 1
        end = total_lines
        if view_range and len(view_range) >= 2:
            start = max(1, view_range[0])
            end = min(total_lines, view_range[1])

        out = []
        for i in range(start, end + 1):
            line_content = all_lines[i - 1]
            out.append(f"{i:>5} | {line_content}")

        header = f"=== {path} (строки {start}-{end} из {total_lines}) ===\n"
        return header + "\n".join(out)
    except Exception as exc:
        return f"Ошибка чтения {path}: {exc}"


def tool_edit(path: str, old_str: str, new_str: str) -> str:
    """Точечно заменяет фрагмент текста old_str на new_str в файле."""
    try:
        full = _safe_path(path)
        if not full.is_file():
            return f"Файл не найден: {path}"

        content = full.read_text(encoding="utf-8", errors="replace")
        count = content.count(old_str)

        if count == 0:
            lines = content.splitlines()
            target_first = (old_str.splitlines() or [""])[0].strip()
            close_matches = difflib.get_close_matches(target_first, [ln.strip() for ln in lines], n=1, cutoff=0.6)
            hint = f"\nВозможно вы имели в виду строку: «{close_matches[0]}»" if close_matches else ""
            return f"Фрагмент old_str не найден в файле {path}.{hint}\nПроверьте отступы и символы через view."

        if count > 1:
            return (
                f"Фрагмент old_str встречается в файле {path} {count} раз. "
                f"Укажите больше окружающих строк для однозначной замены."
            )

        updated = content.replace(old_str, new_str, 1)
        full.write_text(updated, encoding="utf-8")

        lint_err = _lint_content(path, updated)
        lint_note = f"\n⚠️ Замечена синтаксическая ошибка: {lint_err}" if lint_err else ""
        return f"✅ Файл {path} успешно обновлен.{lint_note}"
    except Exception as exc:
        return f"Ошибка редактирования: {exc}"


def tool_write(path: str, content: str) -> str:
    """Создаёт или перезаписывает файл в проекте."""
    try:
        full = _safe_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        size = len(content.encode("utf-8"))
        lint_err = _lint_content(path, content)
        lint_note = f"\n⚠️ Замечена синтаксическая ошибка: {lint_err}" if lint_err else ""
        return f"✅ Записан файл {path} ({size} байт).{lint_note}"
    except Exception as exc:
        return f"Ошибка записи: {exc}"


def tool_glob(pattern: str, path: str = ".") -> str:
    """Ищет файлы по маске (например: '*.py', 'src/**/*.js')."""
    try:
        base = _safe_path(path)
        matches = []
        for p in base.rglob("*"):
            if any(part in (".git", "__pycache__", ".venv", "node_modules") for part in p.parts):
                continue
            rel = p.relative_to(_ws()).as_posix()
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
                matches.append(f"{'[DIR] ' if p.is_dir() else '      '}{rel}")
            if len(matches) >= 5000:
                matches.append(f"...и ещё файлы (показано 5000 совпадений)")
                break
        if not matches:
            return f"Файлы по маске '{pattern}' не найдены."
        return "\n".join(matches)
    except Exception as exc:
        return f"Ошибка glob: {exc}"


def tool_grep(pattern: str, path: str = ".", include: str = "") -> str:
    """Ищет регулярное выражение по содержимому файлов."""
    try:
        base = _safe_path(path)
        rx = re.compile(pattern)
        hits = []
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part in (".git", "__pycache__", ".venv", "node_modules") for part in p.parts):
                continue
            if include and not fnmatch.fnmatch(p.name, include):
                continue
            if is_image(str(p)) or p.stat().st_size > 5_000_000:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                for num, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        rel = p.relative_to(_ws()).as_posix()
                        hits.append(f"{rel}:{num}: {line.strip()[:140]}")
                        if len(hits) >= 1000:
                            break
            except Exception:
                continue
            if len(hits) >= 1000:
                hits.append(f"...показаны первые 1000 совпадений")
                break
        if not hits:
            return f"Ничего не найдено по регулярному выражению «{pattern}»."
        return "\n".join(hits)
    except Exception as exc:
        return f"Ошибка grep: {exc}"


def tool_agent(role: str, task: str, model: str = "") -> str:
    """Запускает специализированного субагента (researcher, coder, tester, devops, general)."""
    return _subagent.run_subagent(role=role, task=task, model=model)


_SESSION_TODOS: dict[str, list[str]] = {}


def tool_todo(action: str = "get", tasks: list[str] | None = None) -> str:
    """Управляет чеклистом задач текущей сессии (get, set, add, clear)."""
    proj = config.get_current_project()
    current = _SESSION_TODOS.setdefault(proj, [])
    action = (action or "get").lower()

    if action == "set" and tasks is not None:
        _SESSION_TODOS[proj] = [str(t) for t in tasks]
        current = _SESSION_TODOS[proj]
    elif action == "add" and tasks:
        current.extend([str(t) for t in tasks])
    elif action == "clear":
        _SESSION_TODOS[proj] = []
        return "План задач очищен."

    if not current:
        return "Список задач пуст."
    return "Текущий список задач:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(current))


def tool_web_search(query: str) -> str:
    """Ищет информацию в интернете."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
            resp = c.get("https://html.duckduckgo.com/html/", params={"q": query})
        html = resp.text
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        links = re.findall(r'class="result__a"[^>]*href="(.*?)"', html, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)

        def clean(s: str) -> str:
            return re.sub(r"<.*?>", "", s).strip()

        out = []
        for i, title in enumerate(titles[:5]):
            snip = clean(snippets[i]) if i < len(snippets) else ""
            url = links[i] if i < len(links) else ""
            out.append(f"{i+1}. {clean(title)}\n   {url}\n   {snip[:250]}")
        return "\n\n".join(out) if out else "Ничего не найдено."
    except Exception as exc:
        return f"Ошибка поиска: {exc}"


def tool_fetch_url(url: str) -> str:
    """Загружает страницу и возвращает текст без тегов."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
            resp = c.get(url)
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", resp.text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<.*?>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:12000] if text else "Пустая страница."
    except Exception as exc:
        return f"Ошибка загрузки страницы: {exc}"


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
        return f"Перемещено: {source} -> {destination}"
    except Exception as exc:
        return f"Ошибка перемещения: {exc}"


def tool_browser(url: str, action: str = "navigate", selector: str | None = None, text: str | None = None) -> str:
    """Управляет веб-браузером на мастер-сервере (переход, клик, ввод текста, скриншот)."""
    master_url = os.getenv("AG_BASE_URL", "https://agent-master-server.onrender.com/v1").replace("/v1", "").rstrip("/")
    api_key = os.getenv("AG_API_KEY", "sk-antigravity-master-roman")
    endpoint = f"{master_url}/api/browser/navigate"
    payload = {"url": url, "action": action}
    if selector:
        payload["selector"] = selector
    if text:
        payload["text"] = text
    try:
        with httpx.Client(timeout=45) as client:
            resp = client.post(endpoint, json=payload, headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code != 200:
            return f"Ошибка браузера (HTTP {resp.status_code}): {resp.text[:300]}"
        data = resp.json()
        out = [f"URL: {data.get('url', url)}", f"Заголовок: {data.get('title', '')}"]
        if data.get("text"):
            out.append(f"Текст страницы:\n{data['text'][:1500]}")
        b64 = data.get("screenshot_base64")
        if b64:
            import base64 as _b64
            shot_file = _ws() / "browser_screenshot.png"
            shot_file.write_bytes(_b64.b64decode(b64))
            out.append("Скриншот сохранён в проект: browser_screenshot.png")
        return "\n".join(out)
    except Exception as exc:
        return f"Ошибка обращения к браузеру: {exc}"


def tool_browser_import_cookies(cookies: str, url: str = "https://www.google.com") -> str:
    """Импортирует сессионные cookies пользователя в браузер мастера для авторизации в Google Flow / Gemini."""
    master_url = os.getenv("AG_BASE_URL", "https://agent-master-server.onrender.com/v1").replace("/v1", "").rstrip("/")
    api_key = os.getenv("AG_API_KEY", "sk-antigravity-master-roman")
    endpoint = f"{master_url}/api/browser/import-cookies"
    try:
        cookie_data = json.loads(cookies) if isinstance(cookies, str) and cookies.strip().startswith(("[", "{")) else cookies
        payload = {"cookies": cookie_data, "url": url}
        with httpx.Client(timeout=30) as client:
            resp = client.post(endpoint, json=payload, headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code == 200:
            return f"Cookies успешно импортированы для {url}."
        return f"Ошибка импорта cookies (HTTP {resp.status_code}): {resp.text[:300]}"
    except Exception as exc:
        return f"Ошибка импорта cookies: {exc}"


def _get_ffmpeg_cmd() -> list[str]:
    """Возвращает путь к исполняемому файлу FFmpeg (из imageio_ffmpeg или системный)."""
    try:
        import imageio_ffmpeg
        return [imageio_ffmpeg.get_ffmpeg_exe()]
    except Exception:
        return ["ffmpeg"]


def tool_video_extract_last_frame(video_path: str, output_name: str = "") -> str:
    """Извлекает последний кадр из MP4 видео для непрерывной генерации следующей сцены в Gemini Omni/Veo."""
    try:
        v_path = _safe_path(video_path)
        if not v_path.is_file():
            return f"Файл видео не найден: {video_path}"
        out_filename = output_name.strip() if output_name else f"{v_path.stem}_last_frame.png"
        out_path = _ws() / out_filename
        ffmpeg_bin = _get_ffmpeg_cmd()
        # -sseof -0.1 берёт кадр за 0.1 секунды до конца видео, гарантируя валидный финальный фрейм
        cmd = [*ffmpeg_bin, "-y", "-sseof", "-0.1", "-i", str(v_path), "-frames:v", "1", "-update", "1", str(out_path)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return f"Ошибка извлечения кадра FFmpeg (код {p.returncode}): {p.stderr[:300]}"
        if not out_path.is_file() or out_path.stat().st_size == 0:
            return f"Кадр не был сохранен: {out_filename}"
        return f"Последний кадр успешно извлечён: {out_filename} ({out_path.stat().st_size} байт). Готов как Starting Frame для следующей сцены."
    except Exception as exc:
        return f"Ошибка извлечения последнего кадра: {exc}"


def tool_video_concat(video_paths: list[str], output_name: str = "full_video.mp4") -> str:
    """Бесшовно склеивает список видеоклипов (MP4) в единый мастер-ролик через FFmpeg."""
    try:
        if not video_paths:
            return "Список видео пуст."
        real_paths = []
        for p in video_paths:
            sp = _safe_path(p)
            if not sp.is_file():
                return f"Видеофайл для склейки не найден: {p}"
            real_paths.append(sp)
        out_path = _ws() / output_name
        list_file = _ws() / "concat_list.tmp.txt"
        lines = [f"file '{p.resolve()}'" for p in real_paths]
        list_file.write_text("\n".join(lines), encoding="utf-8")
        ffmpeg_bin = _get_ffmpeg_cmd()
        cmd = [*ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            cmd_reencode = [*ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:v", "libx264", "-c:a", "aac", str(out_path)]
            p = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=120)
        try:
            list_file.unlink(missing_ok=True)
        except Exception:
            pass
        if p.returncode != 0:
            return f"Ошибка склейки FFmpeg: {p.stderr[:300]}"
        return f"Видео успешно склеено: {output_name} ({out_path.stat().st_size} байт, объединены {len(real_paths)} сцен)."
    except Exception as exc:
        return f"Ошибка склейки видео: {exc}"


# ---------------- Спецификации инструментов ----------------

def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def tool_image_generate(prompt: str, filename: str = "") -> str:
    """Генерирует фотореалистичное изображение по текстовому описанию и сохраняет в проект."""
    import urllib.parse
    import httpx
    import time

    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        return "Ошибка: пустой запрос для генерации изображения."

    safe_name = filename.strip() if filename else f"gen_{int(time.time())}.png"
    if not safe_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        safe_name += ".png"

    out_file = _safe_path(safe_name)
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"

    try:
        r = httpx.get(url, timeout=45.0, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(r.content)
            try:
                from . import storage
                if storage.status().get("enabled"):
                    storage.upload_file(safe_name, r.content)
            except Exception:
                pass
            return f"Изображение успешно создано и сохранено: {safe_name} ({len(r.content)} байт).\nОно доступно для просмотра и скачивания в проекте."
        return f"Не удалось сгенерировать изображение (сервис вернул статус {r.status_code})."
    except Exception as exc:
        return f"Ошибка при генерации изображения: {exc}"


def tool_inspect_image(path: str, prompt: str = "") -> str:
    """Анализирует любое изображение, скан МРТ/КТ, документ или график с помощью Vision/OCR."""
    try:
        full = _safe_path(path)
        if not full.exists():
            return f"Файл не найден: {path}"
        if not is_image(str(full)):
            return f"Файл {path} не является поддерживаемым изображением."
        return _ocr_and_describe_image(full, path, prompt)
    except Exception as exc:
        return f"Ошибка анализа изображения {path}: {exc}"


def build_tools() -> list[dict]:
    """Спецификации канонических инструментов Claude Code."""
    return [
        _tool(
            "bash",
            "Выполняет команду в Bash терминале (git, pip, python, curl, запуск тестов, проверка статуса).",
            {"command": {"type": "string", "description": "Команда bash для запуска"},
             "timeout": {"type": "integer", "description": "Таймаут в секундах (по умолч. 60)"}},
            ["command"],
        ),
        _tool(
            "view",
            "Читает файл с номерами строк и поддержкой срезов [start_line, end_line]. Также показывает списки директорий, читает DOCX, PDF и сканы/картинки (OCR).",
            {"path": {"type": "string", "description": "Путь к файлу или папке"},
             "view_range": {"type": "array", "items": {"type": "integer"}, "description": "[начало, конец] строк"}},
            ["path"],
        ),
        _tool(
            "edit",
            "Хирургически заменяет фрагмент old_str на new_str в существующем файле. Предпочитай edit полной перезаписи.",
            {"path": {"type": "string", "description": "Путь к файлу"},
             "old_str": {"type": "string", "description": "Точный исходный текст для замены"},
             "new_str": {"type": "string", "description": "Новый текст"}},
            ["path", "old_str", "new_str"],
        ),
        _tool(
            "write",
            "Создаёт новый файл или полностью перезаписывает существующий.",
            {"path": {"type": "string", "description": "Путь к файлу"},
             "content": {"type": "string", "description": "Содержимое файла"}},
            ["path", "content"],
        ),
        _tool(
            "glob",
            "Находит файлы по шаблону (например '*.py', 'src/**/*.tsx').",
            {"pattern": {"type": "string", "description": "Маска поиска"},
             "path": {"type": "string", "description": "Папка поиска (по умолч. .)"}},
            ["pattern"],
        ),
        _tool(
            "grep",
            "Быстрый поиск регулярного выражения по содержимому всех файлов проекта.",
            {"pattern": {"type": "string", "description": "Регулярное выражение для поиска"},
             "path": {"type": "string", "description": "Папка поиска"},
             "include": {"type": "string", "description": "Фильтр имен файлов (например '*.py')"}},
            ["pattern"],
        ),
        _tool(
            "agent",
            "Запускает автономного специализированного субагента в изолированном контексте. "
            "Роли: 'researcher' (исследование/поиск), 'coder' (написание модулей), "
            "'director' (сценарии, раскадровки, промпты для Gemini Omni/Veo), "
            "'tester' (запуск тестов/верификация), 'devops' (настройка серверов/git/окружения), 'general' (универсальный).",
            {"role": {"type": "string", "description": "Роль субагента"},
              "task": {"type": "string", "description": "Чёткое и детальное задание для субагента"},
              "model": {"type": "string", "description": "Модель (необязательно)"}},
            ["role", "task"],
        ),
        _tool(
            "todo",
            "Управляет чеклистом задач текущей сессии (action: 'get', 'set', 'add', 'clear').",
            {"action": {"type": "string", "description": "get, set, add или clear"},
             "tasks": {"type": "array", "items": {"type": "string"}, "description": "Список задач"}},
        ),
        _tool(
            "image_generate",
            "Генерирует фотореалистичное изображение, иллюстрацию или визуализацию по описанию и сохраняет файл в проект.",
            {"prompt": {"type": "string", "description": "Подробное текстовое описание картинки на английском или русском языке"},
             "filename": {"type": "string", "description": "Имя файла для сохранения (например 'image.png')"}},
            ["prompt"],
        ),
        _tool(
            "inspect_image",
            "Мультимодальный анализ изображений, сканов МРТ, справок и документов (OCR) с извлечением текста и диагнозов.",
            {"path": {"type": "string", "description": "Путь к изображению или скану в проекте"},
             "prompt": {"type": "string", "description": "Что именно найти или проанализировать на картинке (необязательно)"}},
            ["path"],
        ),
        _tool(
            "browser",
            "Автономный веб-браузер (Playwright): переходит по URL, делает клики, вводит текст, сохраняет скриншоты страницы. "
            "Используется для взаимодействия с Google Flow, веб-интерфейсами генерации видео и скачивания результатов.",
            {"url": {"type": "string", "description": "Полный адрес страницы"},
             "action": {"type": "string", "description": "navigate, click, type или screenshot"},
             "selector": {"type": "string", "description": "CSS-селектор элемента для клика или ввода"},
             "text": {"type": "string", "description": "Текст для ввода в поле (для action='type')"}},
            ["url"],
        ),
        _tool(
            "browser_import_cookies",
            "Импортирует сессионные cookies пользователя в браузер агента для авторизации в Google Flow / Gemini / Google Pro.",
            {"cookies": {"type": "string", "description": "JSON строка с cookies (экспортированная из личного браузера)"},
             "url": {"type": "string", "description": "Домен для применения cookies (по умолч. 'https://gemini.google.com')"}},
            ["cookies"],
        ),
        _tool(
            "video_extract_last_frame",
            "Извлекает последний кадр из MP4 видеофайла для передачи как Starting Frame следующей сцены в Gemini Omni/Veo (гарантирует непрерывность видеоряда без швов).",
            {"video_path": {"type": "string", "description": "Путь к исходному MP4 видеофайлу в проекте"},
             "output_name": {"type": "string", "description": "Имя сохраняемого PNG файла (по умолч. <video>_last_frame.png)"}},
            ["video_path"],
        ),
        _tool(
            "video_concat",
            "Бесшовно склеивает список видеоклипов MP4 в единый мастер-ролик через FFmpeg.",
            {"video_paths": {"type": "array", "items": {"type": "string"}, "description": "Список путей к сценам по порядку: ['scene_1.mp4', 'scene_2.mp4']"},
             "output_name": {"type": "string", "description": "Имя итогового файла (по умолч. 'full_video.mp4')"}},
            ["video_paths"],
        ),
        _tool(
            "web_search",
            "Поиск информации в интернете.",
            {"query": {"type": "string", "description": "Поисковый запрос"}},
            ["query"],
        ),
        _tool(
            "fetch_url",
            "Загружает веб-страницу и возвращает текстовое содержимое.",
            {"url": {"type": "string", "description": "Полный URL адрес"}},
            ["url"],
        ),
    ]


_REGISTRY = {
    "bash": tool_bash,
    "view": tool_view,
    "edit": tool_edit,
    "write": tool_write,
    "glob": tool_glob,
    "grep": tool_grep,
    "agent": tool_agent,
    "todo": tool_todo,
    "image_generate": tool_image_generate,
    "inspect_image": tool_inspect_image,
    "browser": tool_browser,
    "browser_import_cookies": tool_browser_import_cookies,
    "video_extract_last_frame": tool_video_extract_last_frame,
    "video_concat": tool_video_concat,
    "web_search": tool_web_search,
    "fetch_url": tool_fetch_url,
    "move_file": tool_move_file,
}


def execute(name: str, args: dict) -> str:
    """Выполняет инструмент по имени."""
    fn = _REGISTRY.get(name)
    if not fn:
        return f"Неизвестный инструмент: {name}"
    try:
        return str(fn(**args))
    except TypeError as exc:
        return f"Ошибка аргументов для {name}: {exc}"
    except Exception as exc:
        return f"Ошибка выполнения инструмента {name}: {exc}"


# ---------------- Системный промпт Claude Code ----------------

def get_claude_system_prompt(project: str = "") -> str:
    """Формирует оригинальный системный промпт Claude Code с подгрузкой CLAUDE.md."""
    base_prompt = """You are Claude Code, Anthropic's official agentic coding assistant for software engineering.
You operate directly in an autonomous developer environment with terminal, code navigation, and editing tools.

CORE WORKFLOW & PRINCIPLES:
1. SOFTWARE ENGINEERING FOCUS:
   - When given instructions, interpret them in the context of professional software engineering and the current working directory.
   - Investigate before modifying: use `view`, `glob`, `grep` to locate and read relevant files before writing or editing.
   - Make surgical edits: prefer `edit` over `write` to update existing files without blowing away comments or formatting.
   - Test and verify: use `bash` to run unit tests, type checkers, linters, or check server health after making changes.

2. SUBAGENTS (DELEGATION VIA `agent` TOOL):
   - You can launch specialized subagents with isolated context to avoid cluttering your own conversation:
     • 'researcher': read-only codebase exploration, doc search, web investigations.
     • 'coder': implementation or refactoring of isolated modules.
     • 'tester': executing test suites and diagnosing edge cases.
     • 'devops': environment management, deployment, server API calls, and git tasks.
     • 'general': multi-step autonomous tasks.
   - When delegating, brief the subagent like a smart colleague: explain the goal, context, relevant paths, and expected output.

3. RESTRAINT, REVERSIBILITY & STRICT DISCIPLINE:
   - Perform ONLY the tasks requested by the user. Match the scope of your actions to what was actually requested.
   - NEVER make unsolicited git commits, git pushes, or external deployments unless the user explicitly requested them.
   - NEVER promise on words what you haven't executed: do not report that something is built, tested, or deployed without running the corresponding tools.
   - Take local, reversible actions freely; ask or confirm before taking destructive or hard-to-reverse actions.

4. MULTIMODAL & VISION:
   - You can examine images, medical scans (MRI, CT, X-ray), screenshots, diagrams, and documents using the `inspect_image` tool (runs high-precision Multimodal Vision OCR).
   - The `view` tool automatically inspects and extracts text from `.docx`, `.pdf`, and image files (`.jpg`, `.png`).
   - You can synthesize images and visuals via the `image_generate` tool.

5. COMMUNICATION STYLE:
   - Concise, direct, technical, and actionable.
   - State what you are doing before major steps.
   - Provide clean end-of-turn summaries: what was changed, test status, and what is ready.
   - Respond in the language used by the user (default to Russian if the user speaks Russian).
"""

    # Подгружаем CLAUDE.md проекта, если он существует
    ws = config.project_dir(project) if project else _ws()
    claude_md = ws / "CLAUDE.md"
    project_rules = ""
    if claude_md.is_file():
        try:
            content = claude_md.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                project_rules = f"\n\nPROJECT INSTRUCTIONS (CLAUDE.md):\n{content}\n"
        except Exception:
            pass

    return base_prompt + project_rules


SYSTEM_PROMPT = get_claude_system_prompt()