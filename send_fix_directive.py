import httpx, json, sys

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

client = httpx.Client(verify=False, timeout=120.0)

task_msg = """[КРИТИЧЕСКИЙ АУДИТ И ДИРЕКТИВА: ИСПРАВЛЕНИЕ СБОРКИ НА RENDER]

Я провёл анализ логов и контейнера на Render. Деплой упал с ошибкой `update_failed`. 
Вот точная причина падения:
1. В `database.py` импорт `from supabase import create_client, Client` находится на верхнем уровне файла без `try...except`.
2. В `requirements.txt` библиотеки `supabase` НЕ БЫЛО! При чистой установке на сервере Render контейнер не запускался с ошибкой: `ModuleNotFoundError: No module named 'supabase'`.
3. Локально у тебя тесты проходили только потому, что supabase был установлен в системном окружении машины.

ТВОЯ ЗАДАЧА СЕЙЧАС:
1. Обнови `requirements.txt`: добавь строчку `supabase>=2.10.0`.
2. В `database.py` сделай безопасную инициализацию:
```python
import os

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Supabase init error: {e}")

def get_supabase():
    return supabase
```
3. Запусти `run_test`, убедись что все тесты зелёные.
4. Вызови `github_push(message="Fix requirements.txt and safe supabase import in database.py")`.

Сделай это прямо сейчас и отчитайся."""

payload = {
    "message": task_msg,
    "session_id": "auditor_supervision_01",
    "project": "default"
}

try:
    r = client.post("https://light-agent.onrender.com/api/chat", json=payload)
    data = r.json()
    with open("agent_reply_round4.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("DONE. Status:", r.status_code)
except Exception as e:
    print("ERROR:", e)
