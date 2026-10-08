import httpx, json, sys

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

client = httpx.Client(verify=False, timeout=120.0)

task_msg = """[ФИНАЛЬНЫЙ ШАГ РАУНДА: ПУШ В GITHUB]

Отлично! Все 9 тестов пройдены успешно (OK).
Теперь сделай ровно одно действие: вызови инструмент `github_push` с сообщением коммита:
"Add Supabase persistence, wife dossier memory, Gemini 2.5 cascade, multi-chat and voice UI"
в репозиторий clodecode2026-debug/ai-wife-coach ветка main."""

payload = {
    "message": task_msg,
    "session_id": "auditor_supervision_01",
    "project": "default"
}

try:
    r = client.post("https://light-agent.onrender.com/api/chat", json=payload)
    data = r.json()
    with open("agent_reply_round3.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("DONE. Status:", r.status_code)
except Exception as e:
    print("ERROR:", e)
