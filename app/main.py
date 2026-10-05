"""FastAPI: REST API, SSE-стриминг, файловый менеджер.

Производительность на бесплатном Render (512 МБ RAM, 1 CPU):
- блокирующие вызовы LLM уходят в поток через ThreadPoolExecutor,
  поэтому сервер не зависает, даже если агент думает 40 секунд;
- SSE отдаёт события по мере поступления, а не в конце;
- у каждого запроса есть таймаут и возможность отмены.
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (agent, config, infra, keepsleep, llm, memory, storage,
               tools, vault)

WEB_DIR = config.BASE_DIR / "web"

# Мусор, который уборщик вправе удалять. Всё остальное не трогаем.
CLEANABLE_PREFIXES = ("tmp_", "diag_", "test_")
CLEANABLE_SUFFIXES = (".tmp", ".log", ".bak", ".old")

# Сколько живёт SSE-соединение, чтобы не держать поток вечно
SSE_MAX_SECONDS = 300


@asynccontextmanager
async def lifespan(app: FastAPI):
    if memory.ensure_schema():
        print("[start] Supabase schema ready", flush=True)
    # Хранилище секретов: таблица создаётся сама через Management API
    vres = vault.ensure_table()
    print(f"[start] vault: {vres}", flush=True)
    if storage.ensure_bucket():
        print(f"[start] bucket {config.S3_BUCKET} ready", flush=True)
    keepsleep.start()
    yield
    await keepsleep.stop()


app = FastAPI(title="Light Agent", version="2.0", lifespan=lifespan)


# ---------------- Схемы ----------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field("default", max_length=100)


class SessionRequest(BaseModel):
    session_id: str = Field("default", max_length=100)


class FileBody(BaseModel):
    path: str = Field(..., max_length=500)
    content: str = ""


class PathBody(BaseModel):
    path: str = Field(..., max_length=500)


# ---------------- Служебное ----------------

def _safe(rel: str):
    """Путь внутри рабочей папки.

    Попытка выйти за пределы даёт 400, а не 500.
    """
    try:
        return tools._safe_path(rel or ".")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _sse(event: str, data: dict) -> str:
    """Форматирует одно SSE-событие."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------- Базовые ----------------

@app.get("/health")
async def health():
    """Лёгкий эндпоинт для keepalive. Должен отвечать быстро."""
    return {
        "status": "ok",
        "idle_seconds": round(agent.idle_seconds()),
        "running_jobs": agent.state()["running_jobs"],
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница. Заголовки нужны для установки как приложение (PWA)."""
    resp = FileResponse(WEB_DIR / "index.html")
    # Service worker нельзя отдавать из кэша HTTP — иначе браузер
    # не увидит обновление и приложение застрянет на старой версии.
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.get("/manifest.json")
async def manifest():
    """Манифест PWA. Отдаём из /static, но с правильным Content-Type."""
    path = WEB_DIR / "static" / "manifest.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Манифест не найден")
    return FileResponse(path, media_type="application/manifest+json")


@app.get("/api/status")
async def status():
    return {
        "providers": [
            {"name": p["name"], "models": p["models"], "base_url": p["base_url"]}
            for p in config.providers()
        ],
        "llm_stats": llm.stats(),
        "memory": memory.status(),
        "storage": storage.status(),
        "anti_sleep": keepsleep.status(),
        "instructions": keepsleep.instructions(),
        "workspace": str(config.WORKSPACE),
        "agent": agent.state(),
        "tools": [t["function"]["name"] for t in tools.build_tools()],
        "infra": infra.status(),
    }


# ---------------- Чат ----------------

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Обычный запрос: ждём полный ответ."""
    try:
        job = agent.submit(req.session_id, req.message)
        return await asyncio.to_thread(job.result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE-стриминг: события приходят по мере работы агента.

    События:
      step    — номер итерации
      tool    — модель вызвала инструмент
      done    — финальный ответ
      error   — что-то пошло не так
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    job_holder: dict = {}

    def on_event(kind: str, payload: dict) -> None:
        # Обработчик крутится в потоке агента - кладём в очередь потокобезопасно.
        loop.call_soon_threadsafe(queue.put_nowait, (kind, payload))

    async def gen():
        started = time.monotonic()
        try:
            job_holder["job"] = agent.submit(req.session_id, req.message,
                                            on_event=on_event)
            yield _sse("open", {"session_id": req.session_id})

            while True:
                if time.monotonic() - started > SSE_MAX_SECONDS:
                    job_holder["job"].cancel()
                    yield _sse("error", {"error": "Превышен лимит времени"})
                    return

                # Отдаём накопленные события, не блокируя поток агента
                while not queue.empty():
                    kind, payload = queue.get_nowait()
                    yield _sse(kind, payload)

                job = job_holder.get("job")
                if job and job.done():
                    # Дрениж остаток очереди перед финалом
                    await asyncio.sleep(0.05)
                    while not queue.empty():
                        kind, payload = queue.get_nowait()
                        yield _sse(kind, payload)
                    result = job.result()
                    yield _sse("done", result)
                    return

                await asyncio.sleep(0.08)

        except asyncio.CancelledError:
            job = job_holder.get("job")
            if job:
                job.cancel()
            raise
        except Exception as exc:
            yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(gen(),
                             media_type="text/event-stream",
                             headers={
                                 "Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no",
                                 "Connection": "keep-alive",
                             })


@app.post("/api/cancel")
async def cancel(req: SessionRequest):
    """Останавливает текущую задачу сессии."""
    ok = agent.cancel(req.session_id)
    return {"ok": ok, "session_id": req.session_id,
            "message": "Задача отменена" if ok else "Нечего отменять"}


# ---------------- Память ----------------

@app.post("/api/reset")
async def reset(req: SessionRequest):
    ok = memory.clear_session(req.session_id)
    return {"ok": ok, "session_id": req.session_id}


@app.get("/api/sessions")
async def sessions():
    """Список сессий с историей - их можно переключать в интерфейсе."""
    return {"sessions": memory.list_sessions()}


# ---------------- Файлы ----------------

@app.get("/api/tree")
async def api_tree(path: str = ".", depth: int = Query(4, ge=1, le=10)):
    """Структура проекта вложенным списком."""
    base = config.WORKSPACE

    def build(p, level: int) -> list[dict]:
        if level > depth:
            return []
        items: list[dict] = []
        try:
            entries = sorted(p.iterdir(),
                             key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:
            return []
        for e in entries:
            rel = str(e.relative_to(base)).replace("\\", "/")
            if e.is_dir():
                items.append({"type": "dir", "name": e.name, "path": rel,
                              "children": build(e, level + 1)})
            else:
                try:
                    size = e.stat().st_size
                except OSError:
                    size = 0
                items.append({
                    "type": "image" if tools.is_image(e.name) else "file",
                    "name": e.name, "path": rel, "size": size,
                })
        return items

    return {"path": path, "tree": build(_safe(path), 1),
            "workspace": str(base)}


@app.get("/api/raw")
async def api_raw(path: str):
    """Отдаёт файл как есть - браузер сам поймёт, картинка это или нет."""
    full = _safe(path)
    if not full.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(full)


@app.get("/api/file")
async def api_read(path: str):
    """Читает текстовый файл для просмотра и правки."""
    full = _safe(path)
    if not full.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    if tools.is_image(path):
        return {"path": path, "is_image": True,
                "mime": tools.image_mime(path),
                "size": full.stat().st_size}
    try:
        if full.stat().st_size > 400_000:
            return {"path": path, "too_big": True,
                    "message": "Файл больше 400 КБ - скачай его вместо просмотра"}
        return {"path": path, "is_image": False,
                "content": full.read_text(encoding="utf-8", errors="replace")}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/file")
async def api_save_file(body: FileBody):
    """Сохраняет содержимое файла."""
    if not body.path.strip():
        raise HTTPException(status_code=400, detail="Не указан путь")
    if tools.is_image(body.path):
        raise HTTPException(status_code=400,
                            detail="Картинку нельзя править текстом")
    full = _safe(body.path)
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(body.content, encoding="utf-8")
        return {"ok": True, "path": body.path, "size": full.stat().st_size}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mkdir")
async def api_mkdir(body: PathBody):
    """Создаёт папку."""
    if not body.path.strip():
        raise HTTPException(status_code=400, detail="Не указан путь")
    full = _safe(body.path)
    try:
        full.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": body.path}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/file")
async def api_delete(path: str, recursive: bool = False):
    """Удаляет файл или папку."""
    full = _safe(path)
    try:
        if full.is_dir():
            if any(full.iterdir()) and not recursive:
                raise HTTPException(
                    status_code=400,
                    detail="Папка не пустая. Повтори с recursive=true")
            import shutil
            shutil.rmtree(full) if recursive else full.rmdir()
        elif full.is_file():
            full.unlink()
        else:
            raise HTTPException(status_code=404, detail="Не найдено")
        return {"ok": True, "path": path}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """Загружает файл с компьютера в рабочую папку."""
    name = os.path.basename((file.filename or "").replace("\\", "/"))
    if not name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")

    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=413,
                            detail="Файл больше 5 МБ - сначала сожми его")

    full = _safe(".") / name
    full.write_bytes(data)
    return {"ok": True, "name": name, "size": len(data), "path": name,
            "is_image": tools.is_image(name)}


@app.post("/api/rename")
async def api_rename(body: dict):
    """Переименовывает или перемещает файл."""
    src = (body or {}).get("source", "")
    dst = (body or {}).get("destination", "")
    if not src or not dst:
        raise HTTPException(status_code=400, detail="Нужны source и destination")
    result = tools.tool_move_file(src, dst)
    if result.startswith("Ошибка"):
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "message": result}


# ---------------- Облачное хранилище ----------------

@app.get("/api/files")
async def files(prefix: str = ""):
    return {"files": storage.list_keys(prefix)}


# ---------------- Секреты (шифрованное хранилище) ----------------

@app.post("/admin/vault")
async def vault_set(body: dict,
                    authorization: str | None = Header(default=None)):
    """Сохраняет секрет в зашифрованное хранилище.

    Требует токен админа: через веб-интерфейс ключ не должен попасть
    в историю браузера или в логи.
    """
    _require_admin(authorization)
    name = (body or {}).get("name", "")
    value = (body or {}).get("value", "")
    note = (body or {}).get("note", "")
    res = vault.set_secret(name, value, note)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@app.get("/api/vault")
async def vault_list():
    """Список секретов. Значения НЕ отдаются - только имена и заметки."""
    items = vault.list_secrets()
    return {"secrets": items, "status": vault.status()}


@app.delete("/admin/vault")
async def vault_delete(name: str,
                       authorization: str | None = Header(default=None)):
    """Удаляет секрет."""
    _require_admin(authorization)
    res = vault.delete_secret(name)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


# ---------------- Уборка (GitHub Actions) ----------------

def _require_admin(authorization: str | None) -> None:
    expected = config.ADMIN_TOKEN
    if not expected or expected == "dev-token":
        raise HTTPException(status_code=503,
                            detail="ADMIN_TOKEN не настроен - уборка отключена")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Нужен заголовок Authorization")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status_code=403, detail="Неверный токен")


class CleanupRequest(BaseModel):
    dry_run: bool = True
    max_age_hours: int = 24


def _plan_cleanup(max_age_hours: int) -> list[dict]:
    """Находит мусор для удаления. Ничего не удаляет."""
    ws = config.WORKSPACE
    now = time.time()
    victims: list[dict] = []

    for path in ws.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if not (name.startswith(CLEANABLE_PREFIXES)
                or name.endswith(CLEANABLE_SUFFIXES)):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        age_h = (now - stat.st_mtime) / 3600
        if age_h < max_age_hours:
            continue
        victims.append({
            "name": str(path.relative_to(ws)),
            "size": stat.st_size,
            "age_hours": round(age_h, 1),
        })
    return victims


@app.post("/admin/cleanup")
async def admin_cleanup(req: CleanupRequest,
                         authorization: str | None = Header(default=None)):
    """Уборка рабочей папки. Запускается из GitHub Actions по расписанию."""
    _require_admin(authorization)

    victims = _plan_cleanup(max(1, req.max_age_hours))
    freed = sum(v["size"] for v in victims)
    removed: list[str] = []

    if not req.dry_run:
        for v in victims:
            try:
                (config.WORKSPACE / v["name"]).unlink()
                removed.append(v["name"])
            except OSError:
                pass

    return {"ok": True, "dry_run": req.dry_run, "found": len(victims),
            "removed": len(removed), "freed_bytes": freed,
            "removed_files": removed,
            "files": victims if req.dry_run else []}


@app.get("/admin/cleanup/preview")
async def admin_cleanup_preview(max_age_hours: int = 24,
                                authorization: str | None = Header(default=None)):
    """Показывает, что уборка удалит, ничего не удаляя."""
    _require_admin(authorization)
    victims = _plan_cleanup(max(1, max_age_hours))
    return {"found": len(victims),
            "freed_bytes": sum(v["size"] for v in victims),
            "files": victims}


# ---------------- Ошибки ----------------

@app.exception_handler(404)
async def not_found(request, exc):
    """404 в JSON, а не HTML - интерфейсу так удобнее."""
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Не найдено"}, status_code=404)
    return JSONResponse({"detail": "Страница не найдена"}, status_code=404)


# Статика лежит в web/static, а монтируется под /static
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")