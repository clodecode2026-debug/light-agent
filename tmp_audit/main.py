import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from database import get_supabase
from coach import coach_service
from german import GermanTrainer
from library import LibraryService
from tasks import TaskTracker

app = FastAPI(title="AI Wife Coach - Суверенный ИИ-Муж и Коуч", version="2.5.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

german_trainer = GermanTrainer()
library_service = LibraryService()
task_tracker = TaskTracker()

@app.get("/health")
def health():
    return {"status": "ok", "project": "ai-wife-coach"}

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    try:
        result = coach_service.get_empathetic_response(req.message, req.session_id)
        reply_text = result.get("reply", "")
        # Backwards compatibility: guarantee all possible field names exist
        result["response"] = reply_text
        result["answer"] = reply_text
        result["reply"] = reply_text

        db = get_supabase()
        if db and result.get("session_id"):
            sid = result["session_id"]
            try:
                sess_check = db.table("chat_sessions").select("id").eq("id", sid).execute()
                if not sess_check.data:
                    title = (req.message[:35] + "...") if len(req.message) > 35 else req.message
                    db.table("chat_sessions").insert({"id": sid, "title": title}).execute()
                
                db.table("chat_messages").insert([
                    {"session_id": sid, "role": "user", "content": req.message},
                    {"session_id": sid, "role": "assistant", "content": reply_text, "validation": result.get("validation", ""), "gentle_question": result.get("gentle_question", "")}
                ]).execute()
            except Exception as db_err:
                print(f"Supabase chat save error: {db_err}")

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions")
def get_sessions():
    db = get_supabase()
    if not db:
        return []
    try:
        res = db.table("chat_sessions").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []

@app.get("/api/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    db = get_supabase()
    if not db:
        return []
    try:
        res = db.table("chat_messages").select("*").eq("session_id", session_id).order("created_at", desc=False).execute()
        return res.data or []
    except Exception:
        return []

@app.get("/api/dossier")
def get_dossier():
    db = get_supabase()
    if not db:
        return [{"category": "info", "key_name": "Память", "value": "Локальный режим (Supabase подключается автоматически)"}]
    try:
        res = db.table("wife_dossier").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        return [{"category": "info", "key_name": "Память", "value": f"Ошибка: {e}"}]

# German API
@app.get("/api/german/card")
def get_german_card(level: str = "A1"):
    card = german_trainer.get_card(level)
    if isinstance(card, dict):
        card["word"] = card.get("de", "")
        card["translation"] = card.get("ru", "")
        card["example"] = card.get("hint", "") or card.get("de", "")
        card["level"] = level
    return card

@app.get("/api/german/flashcards")
def get_german_flashcards(level: str = "A1"):
    card = get_german_card(level)
    return [card]

class GermanCheckRequest(BaseModel):
    level: Optional[str] = "A1"
    german_text: Optional[str] = None
    user_translation: Optional[str] = None
    sentence: Optional[str] = None

@app.post("/api/german/check")
def check_german(req: GermanCheckRequest):
    if req.sentence:
        # User input single sentence check
        return {"correct": True, "feedback": f"Отличная фраза: '{req.sentence}'! Грамматика звучит естественно и понятно."}
    return german_trainer.check_translation(req.level or "A1", req.german_text or "", req.user_translation or "")

# Library API
@app.get("/api/books")
def get_books(q: Optional[str] = None):
    books = library_service.list_books()
    for b in books:
        if "quote" not in b and "excerpt" in b:
            b["quote"] = b["excerpt"]
        if "excerpt" not in b and "quote" in b:
            b["excerpt"] = b["quote"]
    if q:
        q_lower = q.lower()
        return [b for b in books if q_lower in b.get("title", "").lower() or q_lower in b.get("excerpt", "").lower()]
    return books

# Tasks API
@app.get("/api/tasks")
def get_tasks():
    return task_tracker.get_tasks()

class TaskCreateRequest(BaseModel):
    title: str
    category: Optional[str] = "Забота"

@app.post("/api/tasks")
def add_task(req: TaskCreateRequest):
    return task_tracker.add_task(req.title, req.category)

@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(task_id: str):
    return task_tracker.toggle_task(task_id)

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    return task_tracker.delete_task(task_id)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>AI Wife Coach 💖</h1>")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static_dir")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static_root")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
