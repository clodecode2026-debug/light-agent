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

import json

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


def tool_infra_env(service_id: str, action: str = "list",
                   name: str = "", value: str = "",
                   secret: bool = False) -> str:
    """Управляет переменными окружения сервиса на Render.

    action=list   - показать (значения секретов скрыты)
    action=set    - добавить или обновить переменную
    action=delete - удалить переменную
    secret=true   - сохранить значение как секрет (не показывать в UI)
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
            k = e.get("key", "?")
            v = e.get("value")
            shown = "•••" if (e.get("type") == "secret" or not v) else v
            lines.append(f"  {k} = {shown}")
        return "\n".join(lines)

    if not name.strip():
        return "Нужно имя переменной (name)"
    key_enc = name.strip()

    if action == "delete":
        res = _render("DELETE", f"/services/{sid}/env-vars/{key_enc}")
        if not res["ok"]:
            return f"Ошибка: {res.get('error') or res.get('data')}"
        return f"Переменная {key_enc} удалена"

    payload = {"key": key_enc, "value": value,
               "type": "secret" if secret else "plain"}
    res = _render("PUT", f"/services/{sid}/env-vars", payload)
    if not res["ok"]:
        # На новую переменную PUT может не сработать - пробуем POST
        res = _render("POST", f"/services/{sid}/env-vars", payload)
    if not res["ok"]:
        return f"Ошибка: {res.get('error') or res.get('data')}"
    kind = "секретом" if secret else "обычным значением"
    return f"Переменная {key_enc} сохранена на сервисе {sid} как {kind}"


def tool_infra_deploy(service_id: str, clear_cache: bool = False) -> str:
    """Запускает новый деплой сервиса - собирает свежую версию кода."""
    sid = (service_id or "").strip()
    if not sid:
        return "Нужен service_id. Вызови infra_services."
    res = _render("POST", f"/services/{sid}/deploys",
                  {"clearCache": bool(clear_cache)})
    if not res["ok"]:
        return f"Ошибка запуска деплоя: {res.get('error') or res.get('data')}"
    d = res["data"]
    dep = d.get("deploy", d) if isinstance(d, dict) else {}
    return f"Деплой запущен: id={dep.get('id')} статус={dep.get('status')}"


def tool_infra_deploy_status(deploy_id: str) -> str:
    """Показывает статус деплоя."""
    did = (deploy_id or "").strip()
    if not did:
        return "Нужен deploy_id"
    res = _render("GET", f"/deploys/{did}")
    if not res["ok"]:
        return f"Ошибка: {res.get('error') or res.get('data')}"
    d = res["data"]
    dep = d.get("deploy", d) if isinstance(d, dict) else {}
    commit = ""
    if isinstance(dep.get("commit"), dict):
        commit = str(dep["commit"].get("message", ""))[:80]
    return (f"Деплой {dep.get('id')}\n"
            f"  статус:   {dep.get('status')}\n"
            f"  commit:   {commit}\n"
            f"  обновлён: {dep.get('updatedAt')}")


def tool_infra_logs(deploy_id: str, tail: int = 60) -> str:
    """Показывает последние строки логов деплоя."""
    did = (deploy_id or "").strip()
    if not did:
        return "Нужен deploy_id. Возьми его из infra_deploy_status"
    n = max(10, min(int(tail or 60), 300))
    res = _render("GET", f"/deploys/{did}/logs?tail={n}")
    if not res["ok"]:
        return f"Ошибка: {res.get('error') or res.get('data')}"
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


def status() -> dict:
    """Состояние инфраструктурных инструментов для /api/status."""
    key, _ = _render_key()
    return {
        "vault": vault.status(),
        "render": bool(key),
        "management_api": bool(config.SUPABASE_ACCESS_TOKEN
                               and config.SUPABASE_PROJECT_REF),
    }