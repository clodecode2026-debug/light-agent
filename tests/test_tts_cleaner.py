# -*- coding: utf-8 -*-
import re

def clean_speech_text(text: str) -> str:
    """Очищает текст от Markdown разметки, спецсимволов и эмодзи перед подачей в TTS."""
    if not text:
        return ""
    # Удаляем жирный и курсивный шрифт
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Удаляем оставшиеся звёздочки, решётки, тильды
    text = text.replace('*', '').replace('#', '').replace('~', '').replace('`', '')
    # Удаляем эмодзи
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2600-\u26ff\u2700-\u27bf]', '', text)
    # Нормализуем кавычки и тире
    text = text.replace('«', '"').replace('»', '"').replace('—', ' - ').replace('–', ' - ')
    # Убираем дубли пробелов
    text = re.sub(r'\s+', ' ', text).strip()
    return text

sample = '**Hallo, Alina!** Keine Panik, alles ist gut! 💡 Sag einfach: *«Heute geht es mir gut!»*'
cleaned = clean_speech_text(sample)
print("Original:", sample)
print("Cleaned:", cleaned)
assert "*" not in cleaned
assert "💡" not in cleaned
print("SUCCESS: Cleaner verified!")
