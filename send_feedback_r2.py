import httpx, json, sys

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

client = httpx.Client(verify=False, timeout=180.0)

task_msg = """[РАЗБОР ОШИБОК ОТ АРХИТЕКТОРА]

Ты отлично написал database.py, coach.py, main.py и фронтенд, но остановился из-за ошибки в тестах и лимита шагов. 

Вот точная причина падения тестов:
1. `test_coach.py` проверяет:
   - `test_coach_service`: в возвращаемом dict метода `get_empathetic_response` ОБЯЗАНЫ быть ключи `"reply"`, `"validation"`, и если во входящем сообщении была усталость, то в `"reply"` должно присутствовать слово "устал" или "усталость".
   - `test_coach_api`: в ответе POST `/api/chat` обязаны быть ключи `"reply"` и `"gentle_question"`. Сделай схему `ChatRequest(message: str, session_id: Optional[str] = None)` так, чтобы при отсутствии session_id она автоматически создавалась или бралась дефолтная, а ответ всегда содержал `{"reply": ..., "validation": ..., "gentle_question": ..., "session_id": ...}`.
2. Не пытайся делать хрупкие правки через `edit_file`, если не можешь найти строку. Используй `write_file`, чтобы переписать модуль целиком в чистом виде!

План действий:
1. Обнови `coach.py` и `main.py` через `write_file`, гарантируя сохранение ключей `reply`, `validation`, `gentle_question`.
2. Запусти `run_test`. Все 9 тестов должны стать зелёными (OK).
3. Запушь изменения в GitHub (`clodecode2026-debug/ai-wife-coach`).
4. Дай краткий итоговый отчет."""

payload = {
    "message": task_msg,
    "session_id": "auditor_supervision_01",
    "project": "default"
}

try:
    r = client.post("https://light-agent.onrender.com/api/chat", json=payload)
    data = r.json()
    with open("agent_reply_round2.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("DONE. Status:", r.status_code)
except Exception as e:
    print("ERROR:", e)
