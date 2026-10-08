import httpx, json, sys

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

client = httpx.Client(verify=False, timeout=180.0)

task_msg = """[РЕЦЕНЗИЯ АРХИТЕКТОРА И ДИРЕКТИВА НА РЕАЛИЗАЦИЮ]

Отличная работа по анализу и проектированию схемы! Таблицы (wife_dossier, chat_sessions, chat_messages, care_tasks, library_books) уже созданы в Supabase и переменные окружения SUPABASE_URL и SUPABASE_KEY синхронизированы.

Теперь критические замечания и корректировки, которые ОБЯЗАТЕЛЬНО нужно учесть:

1. АКТУАЛЬНОСТЬ МОДЕЛЕЙ (Октябрь 2026):
Никаких устаревших моделей Gemini 1.5! Используй стек моделей Gemini 2.5:
- Основная рабочая лошадка: gemini-2.5-flash
- Глубокие психологические разборы: gemini-2.5-pro
- Fallback: при ошибке квот или сетевом сбое — бережный локальный психологический движок.

2. ДОСЬЕ ЖЕНЫ ("ПОМНИТЬ ВСЁ О НЕЙ"):
- При каждом ответе психолога подгружай факты из wife_dossier в системный промпт ("Что мы знаем о ней").
- После каждого сообщения пользователя запускай фоновое извлечение новых фактов и сохраняй в wife_dossier.
- Добавь эндпоинт GET /api/dossier и отдельную вкладку/раздел в интерфейсе ("💖 Обо мне"), чтобы видеть всю накопленную память.

3. МУЛЬТИЧАТЫ В ИНТЕРФЕЙСЕ (как в ChatGPT):
- Добавь сайдбар/выдвижное меню с историей сессий, кнопкой "+ Новый чат", возможностью переключаться между разными темами разговоров.

4. ЖИВОЙ ГОЛОС:
- В интерфейсе добавить микрофон (SpeechRecognition) для надиктовывания мыслей.
- Добавить кнопку воспроизведения ответа (Web SpeechSynthesis) с мягким теплым тембром.

5. РЕАЛИЗАЦИЯ И ПУШ В GITHUB:
- Внеси изменения в код ai-wife-coach (database.py, coach.py, main.py, static/index.html, static/app.js).
- Обнови автотесты и запусти их.
- Закоммить и запушь код в репозиторий clodecode2026-debug/ai-wife-coach.

Приступай к реализации! Жду отчет о внесенных изменениях и результатах тестов."""

payload = {
    "message": task_msg,
    "session_id": "auditor_supervision_01",
    "project": "default"
}

try:
    r = client.post("https://light-agent.onrender.com/api/chat", json=payload)
    data = r.json()
    with open("agent_reply.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("DONE. Status:", r.status_code)
    print("Answer snippet:", data.get("answer", "")[:300])
except Exception as e:
    print("ERROR:", e)
