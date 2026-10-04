"""FastAPI приложение: REST API + веб-интерфейс."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
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


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")