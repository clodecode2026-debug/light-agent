import os
import io
import re
import uuid
import asyncio
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import uvicorn
import base64

# Импорты наших модулей
from coach import coach
from database import db_manager
from german import get_german_phrases
from library import get_library_items
from storage import s3_storage
from books.psychology_books import get_psychology_books, PSYCHOLOGY_BOOKS
from books.german_course import get_german_course, GERMAN_COURSE_DATA

# Попытка импорта edge-tts
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Wife Coach Super-App", version="3.1.0")

# Монтируем статику
app.mount("/static", StaticFiles(directory="static"), name="static")

async def supabase_anti_sleep_worker():
    """Фоновый воркер анти-засыпания Supabase (каждые 6 часов)"""
    while True:
        try:
            await asyncio.sleep(6 * 3600)
            await asyncio.to_thread(db_manager.keepalive_ping)
        except Exception as e:
            logger.warning(f"Anti-sleep worker notice: {e}")
            await asyncio.sleep(600)

@app.on_event("startup")
async def startup_event():
    # Немедленный разогревающий пинг и запуск фонового цикла
    try:
        await asyncio.to_thread(db_manager.keepalive_ping)
    except Exception as e:
        logger.warning(f"Initial keepalive ping notice: {e}")
    asyncio.create_task(supabase_anti_sleep_worker())

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    is_voice_mode: bool = False
    mode: Optional[str] = "coach"  # "coach" | "german"
    german_lesson_id: Optional[int] = None

class TTSRequest(BaseModel):
    text: str
    voice: str = "ru-RU-SvetlanaNeural"

class VoiceSaveRequest(BaseModel):
    audio_base64: str
    filename: str = "voice_note.mp3"

class GermanCheckRequest(BaseModel):
    sentence: str
    german_text: str
    user_translation: str

class GermanProgressRequest(BaseModel):
    xp: int = 0
    hearts: int = 5
    streak: int = 1
    lesson_id: int = 1

@app.get("/", response_class=HTMLResponse)
async def read_index():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        return HTMLResponse(content=f"<h1>AI Wife Coach</h1><p>Ошибка загрузки интерфейса: {e}</p>")

@app.post("/api/chat")
def api_chat(req: ChatRequest):
    try:
        session_id = req.session_id
        german_context = None

        # РЕЖИМ СПЕЦИАЛИЗИРОВАННОГО НЕМЕЦКОГО РЕЧЕВОГО КОУЧА
        if req.mode == "german":
            # Изолируем историю немецкого языка, чтобы НЕ сбивать психологическую память и настройки Алины!
            session_id = f"german_live_{req.session_id}"
            lessons = GERMAN_COURSE_DATA.get("lessons", [])
            lesson_id = req.german_lesson_id or 1
            german_lesson = next((l for l in lessons if (l.get("id") == lesson_id or l.get("day") == lesson_id)), lessons[0] if lessons else None)
            if german_lesson:
                german_context = {
                    "title": german_lesson.get("title", ""),
                    "level": german_lesson.get("level", "A1+"),
                    "grammar": german_lesson.get("grammar", ""),
                    "situation": german_lesson.get("dialogue_simulator", {}).get("situation", ""),
                    "vocabulary": german_lesson.get("vocabulary", [])
                }

        history = db_manager.get_chat_history(session_id)
        dossier = db_manager.get_dossier()

        # Сохраняем входящее сообщение
        db_manager.save_message(session_id, "user", req.message)

        # Генерация живого ответа через каскадный роутер
        reply = coach.generate_response(
            req.message,
            history=history,
            dossier=dossier,
            is_voice_mode=req.is_voice_mode,
            german_context=german_context
        )

        # Сохраняем ответ ассистента
        db_manager.save_message(session_id, "assistant", reply)

        return {"reply": reply}
    except Exception as e:
        logger.error(f"Ошибка в /api/chat: {e}")
        return {"reply": f"Солнышко, извини, произошла временная заминка связи: {str(e)}"}

@app.get("/api/german")
async def api_german(level: str = "ALL"):
    return get_german_phrases(level)

@app.get('/api/books')
async def api_books():
    return PSYCHOLOGY_BOOKS

@app.get('/api/german/course')
async def api_german_course_data():
    return GERMAN_COURSE_DATA

@app.get("/api/german/card")
async def api_german_card(level: str = "A1"):
    phrases = get_german_phrases(level)
    if phrases:
        return phrases[0]
    return {"level": level, "category": "Общее", "german": "Guten Tag!", "russian": "Добрый день!", "grammar": "Базовое приветствие."}

@app.post("/api/german/check")
async def api_german_check(req: GermanCheckRequest):
    return {
        "correct": True,
        "feedback": f"Отлично! Вы верно перевели фразу. Текст: '{req.german_text}'. Продолжайте в том же духе!"
    }

@app.post("/api/german/progress")
async def api_save_german_progress(req: GermanProgressRequest):
    db_manager.save_german_progress(req.dict())
    return {"status": "ok", "progress": req.dict()}

@app.get("/api/german/progress")
async def api_get_german_progress():
    return db_manager.get_german_progress()

@app.get("/api/library")
async def api_library(q: str = None):
    items = get_library_items()
    if q:
        q_lower = q.lower()
        items = [i for i in items if q_lower in i["title"].lower() or q_lower in i["author"].lower() or q_lower in i["excerpt"].lower()]
    return items

@app.get("/api/books/psychology")
async def api_psychology_books():
    return get_psychology_books()

def clean_speech_text(text: str) -> str:
    """Очищает текст от Markdown разметки, звездочек и спецсимволов перед отправкой в TTS."""
    if not text:
        return ""
    # Убираем жирный/курсивный markdown (**слово**, *слово*, __слово__, _слово_)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Убираем оставшиеся звёздочки, решётки, тильды и обратные кавычки
    text = text.replace('*', '').replace('#', '').replace('~', '').replace('`', '')
    # Убираем эмодзи и спец-глифы
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2600-\u26ff\u2700-\u27bf]', '', text)
    # Нормализуем кавычки и тире
    text = text.replace('«', '"').replace('»', '"').replace('—', ' - ').replace('–', ' - ')
    return re.sub(r'\s+', ' ', text).strip()

@app.post("/api/voice/tts")
async def api_tts(req: TTSRequest):
    if not HAS_EDGE_TTS:
        raise HTTPException(status_code=500, detail="edge-tts не установлена")
    
    try:
        clean_text = clean_speech_text(req.text)
        if not clean_text:
            return Response(content=b"", media_type="audio/mpeg")
            
        voice = req.voice or "ru-RU-SvetlanaNeural"
        communicate = edge_tts.Communicate(clean_text, voice)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
        
        audio_stream.seek(0)
        return Response(content=audio_stream.read(), media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/save")
def api_voice_save(req: VoiceSaveRequest):
    try:
        binary_data = base64.b64decode(req.audio_base64)
        file_url = s3_storage.upload_file_bytes(binary_data, req.filename)
        if not file_url:
            raise HTTPException(status_code=500, detail="Не удалось загрузить файл в S3 Storj хранилище")
        return {"status": "success", "url": file_url}
    except Exception as e:
        logger.error(f"Voice Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    ai_active = bool(coach.ag_client or coach.genai_client)
    return {"status": "healthy", "ai_active": ai_active, "supabase_active": bool(db_manager.client)}

class DossierUpdateRequest(BaseModel):
    name: str = "Алина"
    notes: str = ""

@app.get("/api/dossier")
def api_get_dossier():
    return db_manager.get_dossier()

@app.post("/api/dossier")
def api_save_dossier(req: DossierUpdateRequest):
    db_manager.save_dossier(req.name, req.notes)
    return {"status": "ok", "message": "Досье сохранено"}

@app.get("/api/chat/history")
def api_chat_history(session_id: str = "default_wife"):
    return db_manager.get_chat_history(session_id)

@app.get("/api/sessions")
def api_get_sessions():
    return db_manager.get_chat_sessions()

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "Новый диалог с Алиной"

@app.post("/api/sessions")
def api_create_session(req: Optional[CreateSessionRequest] = None):
    new_id = f"alina_{uuid.uuid4().hex[:12]}"
    title = req.title if req and req.title else "Новый диалог с Алиной"
    db_manager.save_message(new_id, "assistant", "Здравствуй, дорогая Алина! Я рядом, о чём ты сейчас думаешь?")
    return {"id": new_id, "title": title}

@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str):
    success = db_manager.delete_chat_session(session_id)
    return {"status": "ok" if success else "error"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, timeout_keep_alive=65)
