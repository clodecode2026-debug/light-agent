"""Инструменты агента для управления инфраструктурой.

Философия: ключи хранятся в зашифрованном хранилище (vault.py) и
никогда не попадают в файлы проекта. Агент обращается к секретам
по имени, а значение подставляется само — в HTTP-запрос, в заголовок
или в переменную окружения на сервере провайдера.

Что здесь есть:
  secret_set / secret_list / secret_delete  — работа с хранилищем
  http_request                             — REST API любого провайдера
                                            с автоподстановкой секретов
  infra_env                                — переменные окружения на Render
  infra_deploy                             — запуск пересборки сервиса
  infra_deploy_status / infra_logs         — статус и логи
  infra_services / infra_create            — список и создание сервисов

Почему не CLI (aws-cli, render-cli, vercel):
Они весят 150+ МБ вместе с зависимостями. На Render free всего
512 МБ, и после установки CLI не остаётся места ни под приложение,
ни под временные файлы агента. HTTP-инструменты весят 0 байт и дают
тот же результат.
"""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import httpx

from . import config, vault

# Внутренняя сеть и облачные метаданные закрыты: иначе агент
# мог бы через http_request уйти читать чужие данные (SSRF).
BLOCKED_HOSTS = (
    "localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254",
    "metadata.google.internal", "instance-data",
)
ALLOWED_SCHEMES = ("https://",)


# ---------------------------------------------------------------------------
# Секреты
# ---------------------------------------------------------------------------

def tool_secret_set(name: str, value: str, note: str = "") -> str:
    """Сохраняет API-ключ в зашифрованное хранилище (вне проекта)."""
    res = vault.set_secret(name, value, note)
    if not res.get("ok"):
        return f"Ошибка: {res.get('error')}"
    verb = "обновлён" if res.get("action") == "updated" else "сохранён"
    return f"Секрет «{res['name']}» {verb} в хранилище (зашифрован)"


def tool_secret_list() -> str:
    """Показывает список секретов. Значения не показываются."""
    items = vault.list_secrets()
    if not items:
        return ("Хранилище пустое. Используй secret_set, чтобы сохранить "
                "ключ, например RENDER_API_KEY.")
    lines = [f"В хранилище секретов: {len(items)}", ""]
    for s in items:
        note = f" — {s['note']}" if s.get("note") else ""
        lines.append(f"  {s['name']}{note}")
    lines.append("")
    lines.append("Значения спрятаны: они не показываются и не лежат в файлах.")
    return "\n".join(lines)


def tool_secret_delete(name: str) -> str:
    """Удаляет секрет из хранилища."""
    res = vault.delete_secret(name)
    if not res.get("ok"):
        return f"Ошибка: {res.get('error')}"
    return f"Секрет «{res['deleted']}» удалён"


# ---------------------------------------------------------------------------
# HTTP-запросы к провайдерам
# ---------------------------------------------------------------------------

def _resolve_secret(token: str) -> tuple[str, bool]:
    """Если значение вида @NAME - достаёт секрет из хранилища."""
    token = (token or "").strip()
    if token.startswith("@") and len(token) > 1:
        res = vault.get_secret(token[1:])
        if res.get("ok"):
            return res["value"], True
        return "", False
    return token, False


def _apply_auth(headers: dict, auth_secret: str) -> tuple[dict, str]:
    """Подставляет заголовок Authorization из хранилища."""
    if not auth_secret:
        return headers, ""
    value, ok = _resolve_secret(auth_secret)
    if not ok:
        return headers, f"секрет «{auth_secret.lstrip('@')}» не найден"
    name = auth_secret.lstrip("@").upper()
    if name.startswith(("GITHUB_", "VERCEL_")):
        headers["Authorization"] = f"Bearer {value}"
    else:
        headers["Authorization"] = value
    return headers, ""


def tool_http_request(method: str, url: str, headers: str = "",
                      body: str = "", auth_secret: str = "",
                      timeout: int = 60) -> str:
    """Делает HTTP-запрос к API облачного провайдера.

    В заголовках можно писать @NAME - значение секрета подставится само.
    Так ключ не попадает ни в файлы проекта, ни в логи агента.

    Пример - список сервисов Render:
      method=GET
      url=https://api.render.com/v1/services
      auth_secret=@RENDER_API_KEY
    """
    method = (method or "GET").upper().strip()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
        return f"Недопустимый метод: {method}"

    url = (url or "").strip()
    if not url.startswith(ALLOWED_SCHEMES):
        return ("Только https://. Для локальных адресов есть отдельные "
                "инструменты инфраструктуры.")
    host = url.split("//", 1)[1].split("/")[0].lower()
    if any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS):
        return f"Адрес {host} заблокирован"

    # Заголовки приходят строкой JSON или по одному на строку
    hdr: dict = {}
    raw_headers = (headers or "").strip()
    if raw_headers:
        try:
            hdr = json.loads(raw_headers)
        except json.JSONDecodeError:
            for line in raw_headers.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    hdr[k.strip()] = v.strip()
    if not isinstance(hdr, dict):
        return "Заголовки должны быть JSON-объектом"

    # Подстановка секретов вида "Bearer @TOKEN"
    for k, v in list(hdr.items()):
        if isinstance(v, str) and "@" in v:
            resolved, _ = _resolve_secret(v)
            if resolved:
                hdr[k] = resolved

    hdr, err = _apply_auth(hdr, auth_secret)
    if err:
        return f"Ошибка авторизации: {err}"

    payload = None
    raw_body = (body or "").strip()
    if raw_body:
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            payload = {"raw": raw_body}

    t = max(5, min(int(timeout or 60), 180))
    try:
        with httpx.Client(timeout=t, follow_redirects=True) as client:
            r = client.request(method, url, headers=hdr, json=payload)
    except httpx.TimeoutException:
        return f"Таймаут {t}с: провайдер не ответил"
    except Exception as exc:
        return f"Ошибка запроса: {type(exc).__name__}: {str(exc)[:200]}"

    text = r.text
    if len(text) > 4000:
        text = text[:4000] + f"\n...[обрезано, было {len(text)} символов]"
    return (f"{method} {url}\n"
            f"Статус: {r.status_code}\n"
            f"Ответ ({r.headers.get('content-type', '?')}):\n{text}")


# ---------------------------------------------------------------------------
# Render: инфраструктура
# ---------------------------------------------------------------------------

def _github_token() -> tuple[str, str]:
    """Достаёт GitHub token: сначала из vault, потом из env, потом из credentials.txt."""
    res = vault.get_secret("GITHUB_TOKEN")
    if res.get("ok") and res.get("value"):
        return res["value"].strip(), ""
    res = vault.get_secret("GITHUB_PERSONAL_ACCESS_TOKEN")
    if res.get("ok") and res.get("value"):
        return res["value"].strip(), ""
    for k in ("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN", "GH_TOKEN"):
        val = os.getenv(k, "").strip()
        if val:
            return val, ""
    try:
        from dotenv import dotenv_values
        cred_path = config.BASE_DIR / "credentials.txt"
        if cred_path.is_file():
            creds = dotenv_values(cred_path)
            for k in ("GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN"):
                if creds.get(k):
                    return creds[k].strip(), ""
    except Exception:
        pass
    return "", ("нет токена GitHub. Сохрани его: "
                "secret_set(name=GITHUB_TOKEN, value=ghp_...)")


def _render_key() -> tuple[str, str]:
    """Ключ Render: сначала из хранилища, потом из настроек."""
    res = vault.get_secret("RENDER_API_KEY")
    if res.get("ok"):
        return res["value"], ""
    if config.RENDER_API_KEY:
        return config.RENDER_API_KEY, ""
    return "", ("нет ключа Render. Сохрани его: "
                "secret_set(name=RENDER_API_KEY, value=...)")


def _render(method: str, path: str, payload: dict | None = None) -> dict:
    """Один вызов Render API с понятной ошибкой вместо исключения."""
    key, err = _render_key()
    if not key:
        return {"ok": False, "error": err}
    try:
        with httpx.Client(timeout=60.0) as c:
            r = c.request(method, f"https://api.render.com/v1{path}",
                          headers={"Authorization": f"Bearer {key}",
                                   "Accept": "application/json",
                                   "Content-Type": "application/json"},
                          json=payload)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:400]}
    if r.status_code >= 400:
        return {"ok": False, "status": r.status_code, "data": data}
    return {"ok": True, "status": r.status_code, "data": data}


def tool_infra_services() -> str:
    """Показывает все сервисы на Render: статус, адреса, репозитории."""
    res = _render("GET", "/services")
    if not res["ok"]:
        return f"Ошибка: {res.get('error') or res.get('data')}"
    items = res["data"] if isinstance(res["data"], list) else []
    if not items:
        return ("Сервисов нет. Создать можно через infra_create, "
                "но надёжнее - через render.yaml в репозитории.")
    lines = [f"Сервисов на Render: {len(items)}", ""]
    for s in items:
        svc = s.get("service", s)
        det = s.get("serviceDetails", {})
        lines.append(f"{svc.get('name', '?')}  [{svc.get('type', '?')}]")
        lines.append(f"   id:     {svc.get('id', '?')}")
        lines.append(f"   url:    {det.get('url') or '—'}")
        lines.append(f"   repo:   {det.get('githubRepo') or '—'} "
                     f"ветка: {det.get('branch') or '—'}")
        lines.append("")
    return "\n".join(lines)


def _render_set_env(service_id: str, key: str, value: str) -> dict:
    """Записывает одну переменную окружения.

    Render API принимает ТОЛЬКО PUT на путь с именем переменной:
      PUT /v1/services/<id>/env-vars/<KEY>   -> 200
    А варианты PUT/POST/PATCH на коллекцию дают 400 «invalid JSON»
    или 405 Method Not Allowed. Это проверено на живом сервере.
    """
    return _render("PUT", f"/services/{service_id}/env-vars/{key}",
                   {"value": value})


def _render_delete_env(service_id: str, key: str) -> dict:
    """Удаляет переменную окружения."""
    return _render("DELETE", f"/services/{service_id}/env-vars/{key}")


def tool_infra_env(service_id: str, action: str = "list",
                   name: str = "", value: str = "",
                   secret: bool = False) -> str:
    """Управляет переменными окружения сервиса на Render.

    action=list   - показать (значения секретов скрыты)
    action=set    - добавить или обновить переменную
    action=delete - удалить переменную

    Пример: infra_env(service_id="srv-xxx", action="set",
                      name="OPENROUTER_API_KEY", value="sk-or-...", secret=true)
    """
    sid = (service_id or "").strip()
    if not sid:
        return ("Нужен service_id. Вызови infra_services - там есть id "
                "каждого сервиса.")
    action = (action or "list").lower().strip()

    if action == "list":
        res = _render("GET", f"/services/{sid}/env-vars")
        if not res["ok"]:
            return f"Ошибка: {res.get('error') or res.get('data')}"
        items = res["data"] if isinstance(res["data"], list) else []
        if not items:
            return "Переменных окружения нет"
        lines = [f"Переменных: {len(items)}", ""]
        for e in items:
            # Render оборачивает каждую переменную в {"envVar": {...}}
            v = e.get("envVar", e) if isinstance(e, dict) else {}
            k = v.get("key", "?")
            val = v.get("value")
            # Значение показываем только если это не секрет
            shown = "•••" if (v.get("type") == "secret" or not val) else val
            lines.append(f"  {k} = {shown}")
        return "\n".join(lines)

    key_enc = (name or "").strip()
    if not key_enc:
        return "Нужно имя переменной (name)"

    if action == "delete":
        res = _render_delete_env(sid, key_enc)
        if not res.get("ok"):
            return f"Ошибка удаления: {res.get('error') or res.get('data')}"
        return f"Переменная {key_enc} удалена"

    res = _render_set_env(sid, key_enc, value or "")
    if not res.get("ok"):
        return (f"Ошибка сохранения (код {res.get('status')}): "
                f"{res.get('error') or res.get('data')}\n"
                "Проверь, что сервис существует и значение не пустое.")
    kind = "секретом" if secret else "обычным значением"
    return (f"Переменная {key_enc} сохранена на сервисе {sid} как {kind}. "
            f"Чтобы сервис увидел её, нужен новый деплой: infra_deploy.")


def tool_infra_deploy(service_id: str, clear_cache: bool = False) -> str:
    """Запускает новый деплой сервиса - собирает свежую версию кода.

    Нужен, чтобы сервис увидел новые переменные окружения: Render
    подставляет их только при новом деплое.
    """
    sid = (service_id or "").strip()
    if not sid:
        return "Нужен service_id. Вызови infra_services."
    # Render принимает для clearCache только строки "clear" / "do_not_clear",
    # а не true/false - проверено на живом сервере.
    payload = {"clearCache": "clear" if clear_cache else "do_not_clear"}
    res = _render("POST", f"/services/{sid}/deploys", payload)
    if not res["ok"]:
        return (f"Ошибка запуска деплоя: {res.get('error') or res.get('data')}\n"
                "Если сервис на бесплатном плане, деплой иногда недоступен "
                "через API - перезапусти его в панели Render.")
    d = res["data"]
    dep = d.get("deploy", d) if isinstance(d, dict) else {}
    return f"Деплой запущен: id={dep.get('id')} статус={dep.get('status')}"


def _render_find_deploy(deploy_id: str) -> tuple[dict, str]:
    """Находит данные деплоя, проверяя сервисы."""
    did = (deploy_id or "").strip()
    if not did:
        return {}, "Нужен deploy_id"
    # Сначала проверяем основной сервис
    main_sid = "srv-db1coonavr4c73b9vbu0"
    res = _render("GET", f"/services/{main_sid}/deploys/{did}")
    if res.get("ok"):
        return res["data"], main_sid

    # Если не там — перебираем сервисы
    svcs = _render("GET", "/services")
    if svcs.get("ok") and isinstance(svcs.get("data"), list):
        for item in svcs["data"]:
            sid = item.get("service", item).get("id")
            if sid and sid != main_sid:
                chk = _render("GET", f"/services/{sid}/deploys/{did}")
                if chk.get("ok"):
                    return chk["data"], sid
    return {}, ""


def tool_infra_deploy_status(deploy_id: str) -> str:
    """Показывает статус деплоя."""
    did = (deploy_id or "").strip()
    if not did:
        return "Нужен deploy_id"
    d, sid = _render_find_deploy(did)
    if not d:
        return f"Деплой {did} не найден среди сервисов Render"
    dep = d.get("deploy", d) if isinstance(d, dict) else {}
    commit = ""
    if isinstance(dep.get("commit"), dict):
        commit = str(dep["commit"].get("message", ""))[:80]
    return (f"Деплой {dep.get('id')}\n"
            f"  сервис:   {sid}\n"
            f"  статус:   {dep.get('status')}\n"
            f"  commit:   {commit}\n"
            f"  обновлён: {dep.get('updatedAt')}")


def tool_infra_logs(deploy_id: str, tail: int = 60) -> str:
    """Показывает последние строки логов деплоя."""
    did = (deploy_id or "").strip()
    if not did:
        return "Нужен deploy_id. Возьми его из infra_deploy_status"
    d, sid = _render_find_deploy(did)
    if not sid:
        return f"Деплой {did} не найден"
    n = max(10, min(int(tail or 60), 300))
    res = _render("GET", f"/services/{sid}/deploys/{did}/logs?tail={n}")
    if not res["ok"]:
        return f"Ошибка получения логов: {res.get('error') or res.get('data')}"
    return json.dumps(res["data"], ensure_ascii=False, indent=2)[:4000]


def tool_infra_create(name: str, repo: str, branch: str = "main",
                      plan: str = "free", kind: str = "web_service",
                      build_command: str = "", start_command: str = "",
                      owner_id: str = "") -> str:
    """Создаёт сервис на Render из GitHub-репозитория.

    Внимание: Render API при создании сервисов нестабилен и часто
    отвечает ошибкой про runtime. Если не вышло - создай сервис
    через Blueprint (render.yaml) в панели Render, это надёжнее.
    """
    if not name.strip() or not repo.strip():
        return "Нужны name и repo (например https://github.com/user/repo)"
    key, err = _render_key()
    if not key:
        return f"Ошибка: {err}"
    owner = (owner_id or config.RENDER_OWNER_ID or "").strip()
    if not owner:
        return ("Нужен owner_id. Найди его через Render API: GET /owners, "
                "возьми поле id (выглядит как tea-xxxx).")

    web_service = {"repo": repo.strip(), "branch": branch or "main"}
    if build_command:
        web_service["buildCommand"] = build_command
    if start_command:
        web_service["startCommand"] = start_command

    payload = {
        "ownerId": owner,
        "repo": repo.strip(),
        "name": name.strip(),
        "branch": branch or "main",
        "runtime": "python",
        "plan": plan or "free",
        "type": kind or "web_service",
        "autoDeployTrigger": "commit",
        "envVars": [],
        "serviceDetails": {"webService": web_service},
    }
    res = _render("POST", "/services", payload)
    if not res["ok"]:
        return ("Ошибка создания сервиса: "
                f"{res.get('error') or res.get('data')}\n"
                "Чаще всего Render не принимает поле runtime через API. "
                "Создай сервис через render.yaml - это надёжнее.")
    d = res["data"]
    s = d.get("service", d) if isinstance(d, dict) else {}
    return f"Сервис создан: {s.get('name')} id={s.get('id')}"


# ---------------------------------------------------------------------------
# GitHub: синхронизация и выгрузка проектов
# ---------------------------------------------------------------------------

def _git_blob_sha(data: bytes) -> str:
    """Вычисляет sha1 блоба в формате git."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _gh_req(url: str, token: str, method: str = "GET",
            payload: dict | None = None, timeout: float = 15.0) -> tuple[int, object]:
    """Быстрый надежный HTTP-запрос к GitHub API через urllib."""
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "LightAgent/2.0",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body[:300]
    except Exception as exc:
        return 0, str(exc)


def tool_github_search(query: str, language: str = "", max_results: int = 5, sort: str = "stars") -> str:
    """Ищет проекты и готовые шаблоны на GitHub.
    Параметры:
      query — ключевые слова для поиска (например 'telegram bot template', 'landing page', 'fastapi crm')
      language — язык программирования (например 'python', 'javascript', 'typescript', 'go')
      max_results — количество результатов (от 1 до 10, по умолчанию 5)
      sort — сортировка: 'stars' (по популярности/звёздам), 'forks', 'updated'
    """
    q_str = (query or "").strip()
    if not q_str:
        return "Укажи поисковый запрос (query), например 'telegram bot ai template'"

    if language and language.strip():
        q_str += f" language:{language.strip()}"

    token, _ = _github_token()
    encoded_q = urllib.parse.quote(q_str)
    n = max(1, min(int(max_results or 5), 10))
    sort_by = sort if sort in ("stars", "forks", "updated") else "stars"

    url = f"https://api.github.com/search/repositories?q={encoded_q}&sort={sort_by}&order=desc&per_page={n}"
    code, res = _gh_req(url, token, timeout=20.0)
    if code != 200 or not isinstance(res, dict):
        return f"Ошибка поиска на GitHub (код {code}): {res}"

    items = res.get("items", [])
    if not items:
        return f"По запросу '{query}' на GitHub ничего не найдено."

    lines = [f"Найдено репозиториев на GitHub (всего {res.get('total_count', len(items))}):", ""]
    for i, it in enumerate(items, 1):
        name = it.get("full_name", "?")
        repo_url = it.get("html_url", "")
        stars = it.get("stargazers_count", 0)
        desc = (it.get("description") or "Без описания").strip()
        lang = it.get("language") or "Не указан"
        lines.append(f"{i}. **{name}** — ⭐ {stars} | {lang}")
        lines.append(f"   URL: {repo_url}")
        lines.append(f"   {desc[:160]}")
        lines.append("")

    lines.append("💡 Чтобы скачать любой из этих проектов в текущую папку проекта, вызови:")
    lines.append("`github_clone(repo_url='https://github.com/owner/repo')`")
    return "\n".join(lines)


def tool_github_clone(repo_url: str, branch: str = "", dest_dir: str = "") -> str:
    """Скачивает и распаковывает репозиторий с GitHub прямо в рабочую папку текущего проекта.
    Позволяет взять готовый проект или шаблон и сразу начать его доработку.
    Параметры:
      repo_url — адрес репозитория (например 'https://github.com/owner/repo' или 'owner/repo')
      branch — ветка (если не указана, берётся ветка по умолчанию)
      dest_dir — подпапка в проекте (по умолчанию корень проекта '.')
    """
    raw_url = (repo_url or "").strip().rstrip("/")
    if not raw_url:
        return "Нужен URL репозитория GitHub (repo_url), например 'https://github.com/tiangolo/fastapi'"

    raw_url = raw_url.removesuffix(".git")
    if "github.com/" in raw_url:
        parts = raw_url.split("github.com/")[-1].split("/")
    else:
        parts = raw_url.split("/")

    if len(parts) < 2:
        return f"Не удалось распознать репозиторий в строке '{repo_url}'. Формат: https://github.com/owner/repo или owner/repo"

    owner, repo = parts[0].strip(), parts[1].strip()
    token, _ = _github_token()

    # 1. Если ветка не указана, узнаём default branch через API
    target_branch = (branch or "").strip()
    if not target_branch:
        code, repo_data = _gh_req(f"https://api.github.com/repos/{owner}/{repo}", token, timeout=15.0)
        if code == 200 and isinstance(repo_data, dict):
            target_branch = repo_data.get("default_branch") or "main"
        else:
            target_branch = "main"

    # 2. Скачиваем zip-архив
    zip_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{target_branch}"
    req = urllib.request.Request(
        zip_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "LightAgent/2.0",
        } if token else {"User-Agent": "LightAgent/2.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            zip_bytes = r.read()
    except urllib.error.HTTPError as e:
        return f"Ошибка скачивания репозитория {owner}/{repo} (HTTP {e.code}): {e.reason}"
    except Exception as exc:
        return f"Ошибка соединения при скачивании репозитория: {exc}"

    # 3. Распаковываем архив в папку проекта
    base = config.current_workspace()
    sub = (dest_dir or "").strip().lstrip("/\\")
    target_folder = (base / sub).resolve()
    if not str(target_folder).startswith(str(base.resolve())):
        return "Недопустимый путь назначения (выходит за пределы папки проекта)"
    target_folder.mkdir(parents=True, exist_ok=True)

    extracted_count = 0
    ignored_patterns = {".git/", "__pycache__/", ".DS_Store"}

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            namelist = zf.namelist()
            if not namelist:
                return f"Скачанный архив репозитория {owner}/{repo} пуст."

            root_prefix = namelist[0].split("/")[0] + "/"

            for member in zf.infolist():
                if any(ign in member.filename for ign in ignored_patterns):
                    continue
                if not member.filename.startswith(root_prefix):
                    continue

                rel_name = member.filename[len(root_prefix):]
                if not rel_name:
                    continue

                dest_file = (target_folder / rel_name).resolve()
                if not str(dest_file).startswith(str(target_folder.resolve())):
                    continue

                if member.is_dir():
                    dest_file.mkdir(parents=True, exist_ok=True)
                else:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_bytes(zf.read(member))
                    extracted_count += 1
    except Exception as exc:
        return f"Ошибка распаковки файлов репозитория: {exc}"

    cur_proj = config.get_current_project()
    return (
        f"✅ Репозиторий '{owner}/{repo}' (ветка: {target_branch}) успешно скачан и распакован!\n"
        f"Проект: '{cur_proj}' (папка: {target_folder.name})\n"
        f"Распаковано файлов: {extracted_count}\n"
        f"Все файлы проекта готовы к просмотру, запуску и редактированию!"
    )


def tool_github_sync(repo_name: str = "", branch: str = "main",
                     message: str = "Update project from Light Agent",
                     private: bool = False,
                     all_repo: bool = False) -> str:
    """Выгружает проект на GitHub. Создаёт репозиторий, если его ещё нет,
    и синхронизирует все файлы через GitHub API параллельно.

    Параметры:
      repo_name — имя репозитория на GitHub (по умолчанию имя активного проекта)
      branch    — ветка (по умолчанию main)
      message   — сообщение коммита
      private   — делать ли репозиторий приватным (по умолчанию false)
      all_repo  — выгрузить весь корневой репозиторий light-agent (по умолч. false)
    """
    token, err = _github_token()
    if not token:
        return f"Ошибка: {err}"

    # 1. Узнаём логин пользователя
    code, user_data = _gh_req("https://api.github.com/user", token)
    if code != 200 or not isinstance(user_data, dict):
        return f"Ошибка авторизации на GitHub (код {code}): {user_data}"
    owner = user_data.get("login")
    if not owner:
        return "Не удалось определить имя пользователя GitHub"

    # 2. Определяем имя репозитория
    cur_proj = config.get_current_project()
    target_repo = (repo_name or "").strip()
    if not target_repo:
        target_repo = "light-agent" if (cur_proj == "default" or all_repo) else cur_proj
    safe_repo = re.sub(r"[^a-zA-Z0-9_\-\.]", "-", target_repo).strip("-") or "my-project"
    branch = (branch or "main").strip()

    # 3. Проверяем наличие репозитория на GitHub, создаём если нет
    code, repo_info = _gh_req(f"https://api.github.com/repos/{owner}/{safe_repo}", token)
    if code == 404:
        create_payload = {
            "name": safe_repo,
            "private": bool(private),
            "auto_init": True,
            "description": f"Created via Light Agent ({cur_proj})",
        }
        c_code, c_res = _gh_req("https://api.github.com/user/repos", token, method="POST", payload=create_payload)
        if c_code not in (200, 201):
            return f"Ошибка создания репозитория {safe_repo} на GitHub (код {c_code}): {c_res}"
        time.sleep(1.5)

    # 4. Собираем файлы проекта для выгрузки
    FORBIDDEN_NAMES = {".env", ".secrets", "credentials.txt", "credentials.json", ".env.local"}
    files_to_sync: list[tuple[Path, str]] = []

    if all_repo or (safe_repo == "light-agent" and cur_proj == "default"):
        base_dir = config.BASE_DIR
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "workspace", "reports", ".venv", "venv", "env", "node_modules", ".pytest_cache", ".mypy_cache")]
            for f in files:
                if f in FORBIDDEN_NAMES or f.endswith((".pyc", ".log", ".tmp", ".key", ".pem")) or f == "orion.svg":
                    continue
                full = Path(root) / f
                try:
                    rel = full.relative_to(base_dir).as_posix()
                except Exception:
                    continue
                if rel.startswith("tests/cyr_") or rel.startswith("tests/render_") or rel.startswith("tests/deploy_"):
                    continue
                files_to_sync.append((full, rel))
    else:
        base_dir = config.current_workspace()
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv", "venv", "env", "node_modules")]
            for f in files:
                if f in FORBIDDEN_NAMES or f.endswith((".pyc", ".log", ".tmp")):
                    continue
                full = Path(root) / f
                try:
                    rel = full.relative_to(base_dir).as_posix()
                except Exception:
                    continue
                files_to_sync.append((full, rel))

    if not files_to_sync:
        readme = base_dir / "README.md"
        readme.write_text(f"# {safe_repo}\n\nProject created with Light Agent.\n", encoding="utf-8")
        files_to_sync.append((readme, "README.md"))

    # 5. Проверяем файлы параллельно, чтобы найти только изменившиеся
    uploaded = 0
    identical = 0
    errors: list[str] = []
    need_upload: list[tuple[str, str, str | None]] = []

    def check_file(item: tuple[Path, str]) -> tuple[str, str, str | None, str | None]:
        p, rel = item
        try:
            content_bytes = p.read_bytes()
            local_sha = _git_blob_sha(content_bytes)

            get_url = f"https://api.github.com/repos/{owner}/{safe_repo}/contents/{rel}?ref={branch}"
            get_code, get_data = _gh_req(get_url, token, timeout=12.0)
            remote_sha = None
            if get_code == 200 and isinstance(get_data, dict):
                remote_sha = get_data.get("sha")
                if remote_sha == local_sha:
                    return ("identical", rel, None, None)

            b64 = base64.b64encode(content_bytes).decode("ascii")
            return ("need_upload", rel, b64, remote_sha)
        except Exception as ex:
            return ("error", rel, str(ex), None)

    workers = min(10, max(2, len(files_to_sync)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for status_kind, rel, b64, r_sha in executor.map(check_file, files_to_sync):
            if status_kind == "identical":
                identical += 1
            elif status_kind == "need_upload":
                need_upload.append((rel, b64, r_sha))
            else:
                errors.append(f"{rel}: {b64}")

    # 6. Коммитим только изменившиеся файлы последовательно (защита от HTTP 409 conflict)
    for rel, b64, remote_sha in need_upload:
        put_url = f"https://api.github.com/repos/{owner}/{safe_repo}/contents/{rel}"
        put_success = False
        last_code = 0
        for attempt in range(4):
            put_payload = {
                "message": f"{message}: {rel}",
                "content": b64,
                "branch": branch,
            }
            if remote_sha:
                put_payload["sha"] = remote_sha

            put_code, put_data = _gh_req(put_url, token, method="PUT", payload=put_payload, timeout=25.0)
            last_code = put_code
            if put_code in (200, 201):
                uploaded += 1
                put_success = True
                break
            elif put_code == 409:
                time.sleep(0.5)
                g_code, g_data = _gh_req(f"https://api.github.com/repos/{owner}/{safe_repo}/contents/{rel}?ref={branch}", token, timeout=12.0)
                if g_code == 200 and isinstance(g_data, dict):
                    remote_sha = g_data.get("sha")
            else:
                time.sleep(0.3)

        if not put_success:
            errors.append(f"{rel} -> HTTP {last_code}")

    repo_url = f"https://github.com/{owner}/{safe_repo}"
    res_text = (
        f"✅ Проект '{cur_proj}' успешно выгружен на GitHub!\n"
        f"Репозиторий: {repo_url}\n"
        f"Ветка: {branch}\n"
        f"Файлов обновлено/создано: {uploaded}, без изменений: {identical}."
    )
    if errors:
        res_text += f"\nОшибок при передаче файлов ({len(errors)}): " + ", ".join(errors[:3])
    return res_text


def tool_infra_deploy_project(service_name: str = "",
                              repo_url: str = "", branch: str = "main",
                              clear_cache: bool = True) -> str:
    """Развёртывает проект на сервере Render.
    Если сервис с таким именем уже существует (например light-agent) — запускает свежий деплой.
    Если нет — создаёт веб-сервис на Render из указанного репозитория GitHub.
    """
    key, err = _render_key()
    if not key:
        return f"Ошибка: {err}"

    cur_proj = config.get_current_project()
    name = (service_name or "").strip()
    if not name:
        name = "light-agent" if cur_proj == "default" else cur_proj
    safe_name = re.sub(r"[^a-zA-Z0-9\-]", "-", name).strip("-").lower() or "light-agent"

    # 1. Проверяем существующие сервисы на Render
    services_res = _render("GET", "/services")
    if services_res.get("ok"):
        items = services_res.get("data", [])
        if isinstance(items, list):
            for item in items:
                svc = item.get("service", item)
                svc_name = svc.get("name", "").lower()
                if svc_name == safe_name or svc_name == safe_name.replace("-", "_"):
                    sid = svc.get("id")
                    det = svc.get("serviceDetails", {})
                    url = det.get("url") or f"https://{safe_name}.onrender.com"
                    dep_res = tool_infra_deploy(sid, clear_cache=clear_cache)
                    return (
                        f"✅ Сервис '{safe_name}' найден на Render (ID: {sid})!\n"
                        f"{dep_res}\n"
                        f"URL сервиса: {url}\n"
                        "Деплой запущен на сервере. Через 1-2 минуты проект будет обновлён и доступен в интернете."
                    )

    # 2. Если сервис не найден — создаём новый
    target_repo = (repo_url or "").strip()
    if not target_repo:
        token, _ = _github_token()
        owner = "clodecode2026-debug"
        if token:
            try:
                with httpx.Client(timeout=15.0) as c:
                    r = c.get("https://api.github.com/user", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
                    if r.status_code == 200:
                        owner = r.json().get("login") or owner
            except Exception:
                pass
        target_repo = f"https://github.com/{owner}/{safe_name}"

    owner_id = config.RENDER_OWNER_ID
    if not owner_id:
        owners_res = _render("GET", "/owners")
        if owners_res.get("ok") and isinstance(owners_res.get("data"), list) and owners_res["data"]:
            owner_id = owners_res["data"][0].get("owner", {}).get("id")

    res = tool_infra_create(
        name=safe_name,
        repo=target_repo,
        branch=branch or "main",
        plan="free",
        owner_id=owner_id or "",
    )
    return (
        f"Попытка создания нового сервиса '{safe_name}' на Render:\n{res}\n"
        f"Репозиторий источника: {target_repo}\n"
        f"Ожидаемый адрес сервиса: https://{safe_name}.onrender.com"
    )


def status() -> dict:
    """Состояние инфраструктурных инструментов для /api/status."""
    key, _ = _render_key()
    return {
        "vault": vault.status(),
        "render": bool(key),
        "management_api": bool(config.SUPABASE_ACCESS_TOKEN
                               and config.SUPABASE_PROJECT_REF),
    }