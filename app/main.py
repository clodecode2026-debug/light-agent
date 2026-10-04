"""FastAPI приложение: REST API + веб-интерфейс."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, config, keepsleep, llm, memory, storage

WEB_DIR = config.BASE_DIR / "web"

# Какие файлы уборщик вправе удалять. Всё остальное (в т.ч. "keep_*")
# не трогаем — вдруг это результат работы, который просили сохранить.
CLEANABLE_PREFIXES = ("tmp_", "diag_", "test_")
CLEANABLE_SUFFIXES = (".tmp", ".log", ".bak", ".old")
# Файлы моложе этого (в днях) оставляем в покое.
FRESH_DAYS = 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    if memory.ensure_schema():
        print("[start] схема Supabase готова", flush=True)
    if storage.ensure_bucket():
        print(f"[start] бакет {config.S3_BUCKET} готов", flush=True)
    keepsleep.start()
    yield
    await keepsleep.stop()


app = FastAPI(title="Light Agent", version="1.0", lifespan=lifespan)


# ---------------- Схемы ----------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = "default"


class ResetRequest(BaseModel):
    session_id: str = "default"


# ---------------- Эндпоинты ----------------

@app.get("/health")
async def health():
    """Лёгкий эндпоинт для keepalive. Должен отвечать быстро."""
    return {
        "status": "ok",
        "idle_seconds": round(agent.idle_seconds()),
        "ts": datetime_now(),
    }


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/status")
async def status():
    chain = config.providers()
    return {
        "providers": [
            {"name": p["name"], "models": p["models"], "base_url": p["base_url"]}
            for p in chain
        ],
        "llm_stats": llm.stats(),
        "memory": memory.status(),
        "storage": storage.status(),
        "anti_sleep": keepsleep.status(),
        "instructions": keepsleep.instructions(),
        "workspace": str(config.WORKSPACE),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Основной эндпоинт: агент выполняет задачу с инструментами."""
    try:
        result = agent.run(req.message, req.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Стриминг ответа. Инструменты не используются."""
    def generate():
        try:
            for chunk in agent.run_stream(req.message, req.session_id):
                yield chunk
        except Exception as exc:
            yield f"\n\n[Ошибка: {exc}]"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@app.post("/api/reset")
async def reset(req: ResetRequest):
    ok = memory.clear_session(req.session_id)
    return {"ok": ok, "session_id": req.session_id}


@app.get("/api/files")
async def files(prefix: str = ""):
    """Список файлов в облачном хранилище."""
    return {"files": storage.list_keys(prefix)}


@app.get("/api/workspace")
async def workspace():
    """Файлы рабочей папки."""
    from . import tools
    return {"listing": tools.tool_list_files(".")}


# ---------------- Уборка (вызывается из GitHub Actions) ----------------

def _require_admin(authorization: str | None) -> None:
    """Проверка токена админа для опасных операций."""
    expected = config.ADMIN_TOKEN
    if not expected or expected == "dev-token":
        raise HTTPException(
            status_code=503,
            detail="ADMIN_TOKEN не настроен - уборка отключена",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Нужен заголовок Authorization")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status_code=403, detail="Неверный токен")


class CleanupRequest(BaseModel):
    dry_run: bool = True
    max_age_hours: int = 24


def _plan_cleanup(max_age_hours: int) -> list[dict]:
    """Находит мусор, который можно удалить. Ничего не удаляет."""
    import time

    ws = config.WORKSPACE
    now = time.time()
    victims: list[dict] = []

    for path in ws.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        # Пользовательские файлы не трогаем: только явный мусор.
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
    """Уборка рабочей папки. Запускается из GitHub Actions по расписанию.

    Удаляет только очевидный мусор (tmp_*, *.log, *.bak) старше max_age_hours.
    Файлы, которые агент сделал по заданию, остаются нетронутыми.
    """
    _require_admin(authorization)

    victims = _plan_cleanup(max(1, req.max_age_hours))
    freed = sum(v["size"] for v in victims)
    removed: list[str] = []

    if not req.dry_run:
        for v in victims:
            target = config.WORKSPACE / v["name"]
            try:
                target.unlink()
                removed.append(v["name"])
            except OSError:
                pass

    return {
        "ok": True,
        "dry_run": req.dry_run,
        "found": len(victims),
        "removed": len(removed),
        "freed_bytes": freed,
        "removed_files": removed,
        "files": victims if req.dry_run else [],
    }


@app.get("/admin/cleanup/preview")
async def admin_cleanup_preview(max_age_hours: int = 24,
                                authorization: str | None = Header(default=None)):
    """Показать, что уборка удалит, ничего не удаляя."""
    _require_admin(authorization)
    victims = _plan_cleanup(max(1, max_age_hours))
    return {
        "found": len(victims),
        "freed_bytes": sum(v["size"] for v in victims),
        "files": victims,
    }


def datetime_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------- Файлы: загрузка, просмотр, папки ----------------

def _safe(rel: str):
    """Путь внутри рабочей папки.

    Защита от выхода за её пределы: попытка указать ../ приводит
    к 400, а не к необработанному исключению.
    """
    from .tools import _safe_path
    try:
        return _safe_path(rel or ".")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/tree")
async def api_tree(path: str = ".", depth: int = 3):
    """Структура проекта: папки и файлы вложенным списком."""
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
                items.append({"type": "file", "name": e.name, "path": rel,
                              "size": size})
        return items

    return {"path": path, "tree": build(_safe(path), 1),
            "workspace": str(base)}


@app.get("/api/files/download")
async def api_download(path: str):
    """Скачать файл из рабочей папки."""
    full = _safe(path)
    if not full.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(full, filename=full.name)


@app.get("/api/file")
async def api_read(path: str):
    """Прочитать текстовый файл - для просмотра и правки в браузере."""
    full = _safe(path)
    if not full.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    try:
        if full.stat().st_size > 400_000:
            return {"path": path, "too_big": True,
                    "message": "Файл больше 400 КБ - скачай его вместо просмотра"}
        return {"path": path,
                "content": full.read_text(encoding="utf-8", errors="replace")}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class FileBody(BaseModel):
    path: str
    content: str = ""


@app.put("/api/file")
async def api_save_file(body: FileBody):
    """Сохранить содержимое файла - правка из браузера."""
    if not body.path.strip():
        raise HTTPException(status_code=400, detail="Не указан путь")
    full = _safe(body.path)
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(body.content, encoding="utf-8")
        return {"ok": True, "path": body.path, "size": full.stat().st_size}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mkdir")
async def api_mkdir(body: FileBody):
    """Создать папку."""
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
    """Удалить файл или папку."""
    full = _safe(path)
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


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """Загрузить файл с компьютера в рабочую папку агента.

    Агент сразу видит файл и может его читать, править и запускать.
    """
    name = os.path.basename((file.filename or "").replace("\\", "/"))
    if not name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")

    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=413,
                            detail="Файл больше 5 МБ - сначала сожми его")

    full = _safe(".") / name
    full.write_bytes(data)
    return {"ok": True, "name": name, "size": len(data), "path": name}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")