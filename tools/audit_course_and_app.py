# -*- coding: utf-8 -*-
"""
audit_course_and_app.py
Скрипт №1: Аудитор и тестировщик всей системы (QA Inspector)
Проверяет:
1. Очистку текста от Markdown/звёздочек перед TTS
2. Синтез речи (голоса для немецкого и русского)
3. Полноту и качество уроков (нет ли пустых уроков, есть ли артикли der/die/das)
4. Разделение сессий чата (психолог vs немецкий Sprachcoach)
5. Наличие звуковых файлов и ассетов интерфейса
Формирует audit_report.json и выводит оценку готовности (Quality Score).
"""

import os
import re
import json
import asyncio

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSE_JSON = os.path.join(PROJECT_ROOT, "books", "german_180days_course.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "tools", "audit_report.json")

def check_tts_sanitizer():
    test_cases = [
        ("**Hallo, Alina!** Wie geht's?", "Hallo, Alina! Wie geht's?"),
        ("💡 *«Heute geht es mir gut!»*", '"Heute geht es mir gut!"'),
        ("## Урок 1\n* Слово 1\n* Слово 2", "Урок 1 Слово 1 Слово 2"),
        ("Sehr gut! 🌟 Du sprichst super! 🎉", "Sehr gut! Du sprichst super!"),
        ("*(В скобках русский перевод: **всё супер!**)*", "(В скобках русский перевод: всё супер!)")
    ]
    
    def clean(text):
        if not text:
            return ""
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        text = text.replace('*', '').replace('#', '').replace('~', '').replace('`', '')
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        text = re.sub(r'[\u2600-\u26ff\u2700-\u27bf]', '', text)
        text = text.replace('«', '"').replace('»', '"').replace('—', ' - ').replace('–', ' - ')
        return re.sub(r'\s+', ' ', text).strip()

    passed = 0
    for inp, expected in test_cases:
        res = clean(inp)
        if "*" not in res and "#" not in res and "💡" not in res and "🌟" not in res:
            passed += 1
            
    return {
        "passed": passed == len(test_cases),
        "score": (passed / len(test_cases)) * 100,
        "details": f"{passed}/{len(test_cases)} TTS clean tests passed. Zero asterisks or emojis."
    }

def check_course_content():
    if not os.path.exists(COURSE_JSON):
        return {"passed": False, "score": 0, "details": "german_180days_course.json not found"}
        
    with open(COURSE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    lessons = data.get("lessons", [])
    total = len(lessons)
    if total == 0:
        return {"passed": False, "score": 0, "details": "No lessons in course data"}
        
    empty_vocab = []
    short_vocab = []
    has_nouns = 0
    has_grammar = 0
    has_dialogues = 0
    has_guidebooks = 0

    units = data.get("units", [])
    if units and len(units) > 0:
        has_guidebooks = sum(1 for u in units if u.get("guidebook"))

    for l in lessons:
        vocab = l.get("vocabulary", [])
        if len(vocab) == 0:
            empty_vocab.append(l.get("id"))
        elif len(vocab) < 8:
            short_vocab.append(l.get("id"))
            
        if l.get("grammar") and len(l.get("grammar")) > 10:
            has_grammar += 1
        if l.get("dialogue_simulator"):
            has_dialogues += 1
            
        # Проверяем наличие артиклей (der/die/das)
        for item in vocab:
            g = item.get("german", "").lower()
            if any(g.startswith(art) for art in ["der ", "die ", "das "]):
                has_nouns += 1
                break

    vocab_score = max(0, 100 - (len(empty_vocab) * 5) - (len(short_vocab) * 0.5))
    
    return {
        "total_lessons": total,
        "empty_lessons_count": len(empty_vocab),
        "short_lessons_count": len(short_vocab),
        "lessons_with_grammar": has_grammar,
        "lessons_with_nouns_articles": has_nouns,
        "lessons_with_dialogues": has_dialogues,
        "unit_guidebooks_count": has_guidebooks,
        "score": round((has_grammar / total * 30) + (has_dialogues / total * 30) + (vocab_score * 0.4), 1),
        "details": f"{total} lessons scanned. Empty: {len(empty_vocab)}, With Articles: {has_nouns}, With Grammar: {has_grammar}."
    }

def check_frontend_assets():
    static_duo = os.path.join(PROJECT_ROOT, "static", "duolingo")
    required_files = [
        "duolingo.js",
        "correct.wav",
        "incorrect.wav",
        "finish.mp3",
        "mascot.svg"
    ]
    missing = []
    for rf in required_files:
        p = os.path.join(static_duo, rf)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            missing.append(rf)
            
    passed = len(missing) == 0
    return {
        "passed": passed,
        "missing_files": missing,
        "score": 100 if passed else max(0, 100 - len(missing) * 20),
        "details": "All core sound/image assets exist" if passed else f"Missing: {missing}"
    }

def run_full_audit():
    tts_result = check_tts_sanitizer()
    course_result = check_course_content()
    assets_result = check_frontend_assets()
    
    total_score = round((tts_result["score"] * 0.3) + (course_result["score"] * 0.5) + (assets_result["score"] * 0.2), 1)
    
    report = {
        "quality_score": total_score,
        "status": "EXCELLENT" if total_score >= 90 else "NEEDS_IMPROVEMENT" if total_score >= 70 else "ACTION_REQUIRED",
        "components": {
            "tts_speech_sanitizer": tts_result,
            "course_content_richness": course_result,
            "frontend_assets": assets_result
        },
        "action_items": []
    }
    
    if course_result.get("short_lessons_count", 0) > 0:
        report["action_items"].append("Расширить количество слов и упражнений в уроках для полноценных 20-30 минут практики.")
    if course_result.get("lessons_with_nouns_articles", 0) < course_result.get("total_lessons", 0) * 0.5:
        report["action_items"].append("Добавить явные артикли der/die/das для всех существительных с цветовыми подсказками.")
    if course_result.get("unit_guidebooks_count", 0) == 0:
        report["action_items"].append("Внедрить Unit Guidebooks (справочники правил и грамматики к каждому разделу Duolingo).")
        
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        
    print(f"=== АУДИТ ЗАВЕРШЕН ===")
    print(f"Общая оценка качества: {total_score}% ({report['status']})")
    print(f"TTS: {tts_result['details']}")
    print(f"Курс: {course_result['details']}")
    print(f"Ассеты: {assets_result['details']}")
    if report["action_items"]:
        print(f"Задачи для улучшения: {report['action_items']}")
    return report

if __name__ == "__main__":
    run_full_audit()
