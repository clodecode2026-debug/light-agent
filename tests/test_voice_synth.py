# -*- coding: utf-8 -*-
import asyncio
import edge_tts

async def test_voices():
    sample = "Hallo Alina! Keine Panik. Wie geht es dir heute? Привет, Алина! Как твои дела сегодня?"
    
    # 1. Проверяем de-DE-SeraphinaMultilingualNeural
    try:
        comm = edge_tts.Communicate(sample, "de-DE-SeraphinaMultilingualNeural")
        data = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        print(f"SeraphinaMultilingual audio bytes: {len(data)}")
    except Exception as e:
        print(f"Seraphina error: {e}")

    # 2. Проверяем de-DE-KatjaNeural
    try:
        comm = edge_tts.Communicate("Hallo Alina! Keine Panik. Wie geht es dir heute?", "de-DE-KatjaNeural")
        data = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        print(f"Katja (German) audio bytes: {len(data)}")
    except Exception as e:
        print(f"Katja error: {e}")

if __name__ == "__main__":
    asyncio.run(test_voices())
