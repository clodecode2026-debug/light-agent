# -*- coding: utf-8 -*-
"""
builder_refine_course.py
Скрипт №2: Мастер улучшения и генерации контента (Builder & Refiner)
Выполняет:
1. Внедрение санитайзера речи (удаление **звёздочек**, эмодзи, разметки)
2. Настройку би-лингвальной озвучки (de-DE-SeraphinaMultilingualNeural для немецкого, ru-RU-SvetlanaNeural для коуча)
3. Создание Unit Guidebooks (справочников правил) для всех 36 юнитов курса
4. Обогащение базы уроков существительными с артиклями (der/die/das), глаголами и фразами
5. Полировку интерфейса Duolingo: добавление справочника юнита (📖 Теория), цветовых бейджей артиклей
"""

import os
import re
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSE_JSON = os.path.join(PROJECT_ROOT, "books", "german_180days_course.json")
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")
APP_JS = os.path.join(PROJECT_ROOT, "static", "app.js")
DUO_JS = os.path.join(PROJECT_ROOT, "static", "duolingo", "duolingo.js")

# Базовые словарные наборы с артиклями для обогащения юнитов (Goethe / Telc A1+/A2)
VOCAB_DATABASE_BY_UNIT = {
    1: [
        {"german": "der Name", "article": "der", "gender": "m", "russian": "имя / фамилия", "example": "Mein Name ist Alina."},
        {"german": "die Sprache", "article": "die", "gender": "f", "russian": "язык", "example": "Deutsch ist eine schöne Sprache."},
        {"german": "das Wort", "article": "das", "gender": "n", "russian": "слово", "example": "Dieses Wort ist neu für mich."},
        {"german": "der Satz", "article": "der", "gender": "m", "russian": "предложение", "example": "Der Satz ist sehr einfach."},
        {"german": "die Frage", "article": "die", "gender": "f", "russian": "вопрос", "example": "Ich habe eine kurze Frage."},
        {"german": "die Antwort", "article": "die", "gender": "f", "russian": "ответ", "example": "Die Antwort ist richtig."},
        {"german": "heißen", "type": "verb", "russian": "называться / зваться", "example": "Wie heißen Sie bitte?"},
        {"german": "wohnen", "type": "verb", "russian": "жить / проживать", "example": "Ich wohne jetzt in Deutschland."},
        {"german": "kommen", "type": "verb", "russian": "приходить / быть родом", "example": "Woher kommen Sie?"},
        {"german": "sprechen", "type": "verb", "russian": "говорить / разговаривать", "example": "Ich spreche ein bisschen Deutsch."},
        {"german": "lernen", "type": "verb", "russian": "учить / изучать", "example": "Heute lerne ich Deutsch."},
        {"german": "verstehen", "type": "verb", "russian": "понимать", "example": "Ich verstehe das sehr gut."}
    ],
    2: [
        {"german": "das Problem", "article": "das", "gender": "n", "russian": "проблема", "example": "Das ist kein Problem."},
        {"german": "die Zeit", "article": "die", "gender": "f", "russian": "время", "example": "Ich habe leider keine Zeit."},
        {"german": "die Lust", "article": "die", "gender": "f", "russian": "желание / охота", "example": "Ich habe keine Lust."},
        {"german": "der Hunger", "article": "der", "gender": "m", "russian": "голод", "example": "Ich habe keinen Hunger."},
        {"german": "der Durst", "article": "der", "gender": "m", "russian": "жажда", "example": "Ich habe keinen Durst."},
        {"german": "das Geld", "article": "das", "gender": "n", "russian": "деньги", "example": "Das kostet nicht viel Geld."},
        {"german": "wissen", "type": "verb", "russian": "знать (факты)", "example": "Ich weiß das nicht."},
        {"german": "kennen", "type": "verb", "russian": "знать (людей, места)", "example": "Ich kenne diese Stadt nicht."},
        {"german": "funktionieren", "type": "verb", "russian": "работать / функционировать", "example": "Das Internet funktioniert nicht."},
        {"german": "stimmen", "type": "verb", "russian": "соответствовать / быть верным", "example": "Das stimmt leider nicht."}
    ],
    3: [
        {"german": "der Kaffee", "article": "der", "gender": "m", "russian": "кофе", "example": "Ich trinke den Kaffee mit Milch."},
        {"german": "der Tee", "article": "der", "gender": "m", "russian": "чай", "example": "Möchtest du einen heißen Tee?"},
        {"german": "der Apfel", "article": "der", "gender": "m", "russian": "яблоко", "example": "Ich esse einen frischen Apfel."},
        {"german": "die Milch", "article": "die", "gender": "f", "russian": "молоко", "example": "Haben wir noch Milch im Kühlschrank?"},
        {"german": "das Brot", "article": "das", "gender": "n", "russian": "хлеб", "example": "Ich kaufe das frische Brot."},
        {"german": "das Wasser", "article": "das", "gender": "n", "russian": "вода", "example": "Ich trinke gerne stilles Wasser."},
        {"german": "der Supermarkt", "article": "der", "gender": "m", "russian": "супермаркет", "example": "Ich gehe in den Supermarkt."},
        {"german": "die Kasse", "article": "die", "gender": "f", "russian": "касса", "example": "Wo ist hier die Kasse, bitte?"},
        {"german": "der Kassenbon", "article": "der", "gender": "m", "russian": "чек", "example": "Brauchen Sie den Kassenbon?"},
        {"german": "kaufen", "type": "verb", "russian": "покупать", "example": "Was kaufen wir heute ein?"},
        {"german": "bezahlen", "type": "verb", "russian": "оплачивать", "example": "Kann ich mit Karte bezahlen?"}
    ],
    4: [
        {"german": "der Termin", "article": "der", "gender": "m", "russian": "запись / встреча / термин", "example": "Ich muss den Termin verschieben."},
        {"german": "die Hilfe", "article": "die", "gender": "f", "russian": "помощь", "example": "Brauchen Sie Hilfe?"},
        {"german": "der Arzt", "article": "der", "gender": "m", "russian": "врач (мужчина)", "example": "Ich muss zum Arzt gehen."},
        {"german": "die Ärztin", "article": "die", "gender": "f", "russian": "врач (женщина)", "example": "Die Ärztin untersucht die Patientin."},
        {"german": "die Arbeit", "article": "die", "gender": "f", "russian": "работа", "example": "Ich kann heute arbeiten."},
        {"german": "können", "type": "verb", "russian": "мочь / уметь (физически/навык)", "example": "Ich kann gut Deutsch verstehen."},
        {"german": "müssen", "type": "verb", "russian": "быть должным / обязанным", "example": "Ich muss heute früh aufstehen."},
        {"german": "wollen", "type": "verb", "russian": "хотеть (твёрдое намерение)", "example": "Wir wollen nach Berlin fahren."},
        {"german": "dürfen", "type": "verb", "russian": "иметь разрешение / позволено", "example": "Darf ich hier kurz warten?"},
        {"german": "möchten", "type": "verb", "russian": "хотелось бы (вежливо)", "example": "Ich möchte bitte einen Termin buchen."}
    ],
    5: [
        {"german": "der Wecker", "article": "der", "gender": "m", "russian": "будильник", "example": "Der Wecker klingelt um sieben Uhr."},
        {"german": "das Frühstück", "article": "das", "gender": "n", "russian": "завтрак", "example": "Das Frühstück ist fertig."},
        {"german": "der Zug", "article": "der", "gender": "m", "russian": "поезд", "example": "Der Zug kommt pünktlich an."},
        {"german": "die Haltestelle", "article": "die", "gender": "f", "russian": "остановка", "example": "Wir steigen an der nächsten Haltestelle aus."},
        {"german": "aufstehen", "type": "verb", "russian": "вставать (с постели)", "example": "Ich stehe jeden Tag um 8 Uhr auf."},
        {"german": "einkaufen", "type": "verb", "russian": "делать покупки", "example": "Am Samstag kaufe ich im Supermarkt ein."},
        {"german": "anrufen", "type": "verb", "russian": "звонить по телефону", "example": "Ich rufe meine Freundin an."},
        {"german": "mitbringen", "type": "verb", "russian": "приносить с собой", "example": "Bringst du bitte Brot mit?"},
        {"german": "einsteigen", "type": "verb", "russian": "садиться в транспорт", "example": "Wir steigen in den Bus ein."},
        {"german": "aussteigen", "type": "verb", "russian": "выходить из транспорта", "example": "Hier müssen wir aussteigen."}
    ],
    6: [
        {"german": "der Tag", "article": "der", "gender": "m", "russian": "день", "example": "Wie war dein Tag heute?"},
        {"german": "die Woche", "article": "die", "gender": "f", "russian": "неделя", "example": "Diese Woche war sehr produktiv."},
        {"german": "das Jahr", "article": "das", "gender": "n", "russian": "год", "example": "Ich lebe seit einem Jahr in Deutschland."},
        {"german": "die Schule", "article": "die", "gender": "f", "russian": "школа", "example": "Ich habe den Sprachkurs besucht."},
        {"german": "gemacht", "type": "participle", "russian": "сделал(а)", "example": "Ich habe alle Hausaufgaben gemacht."},
        {"german": "gesagt", "type": "participle", "russian": "сказал(а)", "example": "Was hat der Beamte gesagt?"},
        {"german": "gekauft", "type": "participle", "russian": "купил(а)", "example": "Ich habe frisches Obst gekauft."},
        {"german": "gegangen", "type": "participle", "russian": "пошёл / пошла (с sein)", "example": "Ich bin gestern spazieren gegangen."},
        {"german": "gefahren", "type": "participle", "russian": "поехал(а) (с sein)", "example": "Wir sind mit dem Zug gefahren."},
        {"german": "angekommen", "type": "participle", "russian": "прибыл(а) (с sein)", "example": "Der Bus ist pünktlich angekommen."}
    ],
    7: [
        {"german": "der Nachbar", "article": "der", "gender": "m", "russian": "сосед", "example": "Ich spreche mit dem Nachbarn."},
        {"german": "die Nachbarin", "article": "die", "gender": "f", "russian": "соседка", "example": "Ich helfe der Nachbarin."},
        {"german": "das Kind", "article": "das", "gender": "n", "russian": "ребёнок", "example": "Ich gebe dem Kind einen Apfel."},
        {"german": "die Eltern", "article": "die", "gender": "pl", "russian": "родители", "example": "Ich schreibe den Eltern eine Nachricht."},
        {"german": "helfen", "type": "verb", "russian": "помогать (+ Dativ)", "example": "Kannst du mir bitte helfen?"},
        {"german": "danken", "type": "verb", "russian": "благодарить (+ Dativ)", "example": "Ich danke dir von Herzen."},
        {"german": "gefallen", "type": "verb", "russian": "нравиться (+ Dativ)", "example": "Das Kleid gefällt mir sehr gut."},
        {"german": "gehören", "type": "verb", "russian": "принадлежать (+ Dativ)", "example": "Das Buch gehört mir."}
    ],
    8: [
        {"german": "der Freund", "article": "der", "gender": "m", "russian": "друг", "example": "Ich fahre mit dem Freund."},
        {"german": "die Freundin", "article": "die", "gender": "f", "russian": "подруга", "example": "Ich gehe zu der Freundin."},
        {"german": "die Stadt", "article": "die", "gender": "f", "russian": "город", "example": "Ich komme aus der Stadt."},
        {"german": "der Bahnhof", "article": "der", "gender": "m", "russian": "вокзал", "example": "Wir treffen uns am Bahnhof."},
        {"german": "die Post", "article": "die", "gender": "f", "russian": "почта", "example": "Ich gehe schnell zur Post."},
        {"german": "die Bank", "article": "die", "gender": "f", "russian": "банк", "example": "Ich habe ein Konto bei der Bank."}
    ],
    9: [
        {"german": "der Tisch", "article": "der", "gender": "m", "russian": "стол", "example": "Das Buch liegt auf dem Tisch."},
        {"german": "der Stuhl", "article": "der", "gender": "m", "russian": "стул", "example": "Ich setze mich auf den Stuhl."},
        {"german": "die Wand", "article": "die", "gender": "f", "russian": "стена", "example": "Das Bild hängt an der Wand."},
        {"german": "das Sofa", "article": "das", "gender": "n", "russian": "диван", "example": "Wir sitzen gemütlich auf dem Sofa."},
        {"german": "der Schrank", "article": "der", "gender": "m", "russian": "шкаф", "example": "Ich lege die Kleidung in den Schrank."}
    ],
    10: [
        {"german": "das Amt", "article": "das", "gender": "n", "russian": "ведомство / учреждение", "example": "Ich habe einen Termin beim Amt."},
        {"german": "die Anmeldung", "article": "die", "gender": "f", "russian": "регистрация / прописка", "example": "Hier ist meine Anmeldung."},
        {"german": "der Pass", "article": "der", "gender": "m", "russian": "паспорт", "example": "Haben Sie Ihren Pass dabei?"},
        {"german": "das Formular", "article": "das", "gender": "n", "russian": "формуляр / бланк", "example": "Füllen Sie bitte dieses Formular aus."},
        {"german": "die Unterschrift", "article": "die", "gender": "f", "russian": "подпись", "example": "Hier fehlt noch Ihre Unterschrift."},
        {"german": "die Bestätigung", "article": "die", "gender": "f", "russian": "подтверждение", "example": "Sie erhalten eine schriftliche Bestätigung."}
    ]
}

# Справочники правил для юнитов (Guidebooks)
UNIT_GUIDEBOOKS = {
    1: {
        "title": "Справочник: Основы немецкого порядка слов",
        "grammar_summary": "В немецком языке глагол — это король предложения! В обычном повествовательном предложении спрягаемый глагол ВСЕГДА стоит на 2-м месте. На 1-м месте может стоять подлежащее (Ich) или обстоятельство времени (Heute): 'Heute lerne ich Deutsch' (не 'Heute ich lerne'!).",
        "tips": "Если начинаете предложение со времени (Heute, Morgen, Jetzt) — сразу после него ставьте глагол, а местоимение 'ich' уходит на 3-е место.",
        "key_phrases": [
            "Heute lerne ich Deutsch. (Сегодня я учу немецкий)",
            "Wie heißen Sie? (Как вас зовут?)",
            "Ich heiße Alina. (Меня зовут Алина)",
            "Freut mich sehr! (Очень приятно!)"
        ]
    },
    2: {
        "title": "Справочник: Отрицание nicht против kein",
        "grammar_summary": "1) 'kein' используется ТОЛЬКО для отрицания существительных, которые употребляются с неопределенным артиклем (ein/eine) или вообще без артикля (вещества, абстракции): Ich habe KEINE Zeit, das ist KEIN Problem.\n2) 'nicht' используется для всего остального: отрицает глаголы (ich weiß NICHT), прилагательные (das ist NICHT teuer) и имена/конкретные вещи с определенным артиклем.",
        "tips": "Запомните формулу: Если перед словом по смыслу можно поставить 'никакой/никакая' — используйте kein/keine!",
        "key_phrases": [
            "Das ist kein Problem! (Это вообще не проблема!)",
            "Ich habe keine Zeit. (У меня нет времени)",
            "Ich weiß das nicht. (Я этого не знаю)",
            "Das stimmt nicht. (Это неверно)"
        ]
    },
    3: {
        "title": "Справочник: Винительный падеж (Akkusativ)",
        "grammar_summary": "Akkusativ отвечает на вопрос 'Кого? Что?' (Wen? Was?). Главный секрет Akkusativ: меняется ТОЛЬКО мужской род (der -> den, ein -> einen). Женский (die / eine) и средний (das / ein) род остаются совершенно без изменений!",
        "tips": "В кафе или магазине при заказе всегда мужской род превращается в -en: Ich möchte EINEN Kaffee (der Kaffee), einen Tee, einen Apfel.",
        "key_phrases": [
            "Ich möchte bitte einen Kaffee. (Я хотела бы кофе, пожалуйста)",
            "Was kostet das zusammen? (Сколько это стоит вместе?)",
            "Kann ich mit Karte bezahlen? (Могу я оплатить картой?)",
            "Einen schönen Tag noch! (Хорошего вам дня!)"
        ]
    },
    4: {
        "title": "Справочник: Модальные глаголы (Können, Müssen, Wollen)",
        "grammar_summary": "Модальный глагол занимает 2-е место в предложении и спрягается, а смысловой смысловой глагол уходит в самом конце предложения в начальной форме (инфинитиве)! Пример: 'Ich MUSS heute zum Arzt GEHEN'. Формы ich и er/sie/es совпадают: ich kann = er kann, ich muss = er muss.",
        "tips": "Глагол-смысл всегда запирает предложение как замок в самом конце!",
        "key_phrases": [
            "Ich kann gut Deutsch sprechen. (Я могу хорошо говорить по-немецки)",
            "Ich muss einen Termin machen. (Я должна сделать запись/термин)",
            "Ich möchte bitte etwas fragen. (Я хотела бы кое-что спросить)"
        ]
    },
    5: {
        "title": "Справочник: Отделяемые приставки (Trennbare Verben)",
        "grammar_summary": "Приставки ab-, an-, auf-, aus-, ein-, mit-, vor-, zu- отрываются от глагола в настоящем времени и улетают в самый конец предложения! Пример: aufstehen -> 'Ich stehe um 8 Uhr AUF'. einkaufen -> 'Ich kaufe im Supermarkt EIN'.",
        "tips": "Не забывайте приставку в хвосте предложения — без неё смысл слова полностью меняется!",
        "key_phrases": [
            "Ich stehe morgens früh auf. (Я встаю утром рано)",
            "Ich kaufe am Samstag ein. (Я закупаюсь в субботу)",
            "Ich rufe dich später an. (Я перезвоню тебе позже)"
        ]
    },
    6: {
        "title": "Справочник: Разговорное прошедшее время Perfekt",
        "grammar_summary": "В живой речи немцы говорят о прошлом в Perfekt: вспомогательный глагол haben или sein на 2-м месте + причастие (Partizip II с приставкой ge-) в самом конце предложения! Большинство глаголов берут haben (ich habe gemacht). Глаголы движения и смены состояния берут sein (ich bin gefahren, ich bin aufgestanden).",
        "tips": "Запоминайте глаголы движения сразу в паре с 'sein': fahren -> ist gefahren, gehen -> ist gegangen, kommen -> ist gekommen.",
        "key_phrases": [
            "Ich habe Deutsch gelernt. (Я учила немецкий)",
            "Wir haben Kaffee getrunken. (Мы выпили кофе)",
            "Ich bin nach Hause gegangen. (Я пошла домой)"
        ]
    },
    7: {
        "title": "Справочник: Дательный падеж (Dativ)",
        "grammar_summary": "Dativ отвечает на вопрос 'Кому? Чему? Где?' (Wem? Wo?). Артикли меняются так: der -> dem, das -> dem, die -> der, die (мн.ч.) -> den (+ n к существительному). Пример: Ich helfe DEM Mann, DER Frau, DEM Kind.",
        "tips": "Глаголы helfen (помогать), danken (благодарить), gefallen (нравиться), gehören (принадлежать) ВСЕГДА требуют Dativ!",
        "key_phrases": [
            "Kannst du mir helfen? (Можешь мне помочь?)",
            "Das Kleid gefällt mir sehr gut. (Это платье мне очень нравится)",
            "Ich danke dir herzlich. (Я от всего сердца благодарю тебя)"
        ]
    },
    8: {
        "title": "Справочник: Предлоги Dativ (mit, nach, von, zu, bei, seit, aus)",
        "grammar_summary": "Золотая семерка предлогов, после которых ВСЕГДА стоит Dativ без исключений: mit (с), nach (после, в страны/города), von (от, из), zu (к), bei (у, при), seit (с тех пор как / на протяжении), aus (из).",
        "tips": "Слитно: zu + dem = zum, zu + der = zur, bei + dem = beim, von + dem = vom.",
        "key_phrases": [
            "Ich fahre mit dem Bus. (Я еду на автобусе)",
            "Ich gehe zur Post / zum Arzt. (Я иду на почту / к врачу)",
            "Ich wohne seit einem Jahr hier. (Я живу здесь уже год)"
        ]
    },
    9: {
        "title": "Справочник: Предлоги двойного управления (Wechselpräpositionen)",
        "grammar_summary": "9 предлогов (an, auf, hinter, in, neben, über, unter, vor, zwischen): 1) Вопрос 'Где?' (Wo?) -> DATIV (покой). 'Das Buch liegt auf DEM Tisch'. 2) Вопрос 'Куда?' (Wohin?) -> AKKUSATIV (действие/направление). 'Ich lege das Buch auf DEN Tisch'.",
        "tips": "Правило 'Покой = Датив, Движение = Аккузатив'.",
        "key_phrases": [
            "Ich bin im Supermarkt (in dem - Wo? Dativ). (Я в супермаркете)",
            "Ich gehe in den Supermarkt (Wohin? Akkusativ). (Я иду в супермаркет)"
        ]
    },
    10: {
        "title": "Справочник: Ведомства Германии и регистрация (Bürgeramt)",
        "grammar_summary": "Для официальных походов в ведомства используйте вежливую форму Sie, формулы 'Ich habe einen Termin um...' и 'Ich möchte bitte...'. Ключевые документы: der Personalausweis / der Reisepass (паспорт), die Wohnungsgeberbestätigung (подтверждение от арендодателя), das Formular (анкета).",
        "tips": "Всегда приходите на термин за 10 минут и держите номер талона (Wartenummer) перед глазами на табло.",
        "key_phrases": [
            "Guten Tag, ich habe einen Termin um 10 Uhr. (Добрый день, у меня термин на 10 часов)",
            "Hier sind meine Unterlagen und mein Pass. (Вот мои документы и мой паспорт)",
            "Ich möchte meinen Wohnsitz anmelden. (Я хотела бы зарегистрировать место жительства)"
        ]
    }
}

def enrich_course_data():
    if not os.path.exists(COURSE_JSON):
        print(f"Error: {COURSE_JSON} not found!")
        return False
        
    with open(COURSE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    lessons = data.get("lessons", [])
    print(f"Enriching {len(lessons)} lessons...")
    
    # 1. Добавляем Unit Guidebooks
    units_list = []
    for u_id in range(1, 37):
        gb = UNIT_GUIDEBOOKS.get(u_id)
        if not gb:
            # Универсальный справочник для продвинутых юнитов
            gb = {
                "title": f"Справочник темы: Юнит {u_id}",
                "grammar_summary": "Практическое применение грамматики и речевых оборотов в реальных ситуациях в Германии (работа, ведомства, интеграция, быт).",
                "tips": "Слушайте интонацию носителей языка и повторяйте вслух полные конструкции с артиклями.",
                "key_phrases": [
                    "Könnten Sie das bitte wiederholen? (Не могли бы вы повторить?)",
                    "Ich hätte gern eine Auskunft. (Я хотела бы получить справку)",
                    "Vielen Dank für Ihre Unterstützung! (Большое спасибо за вашу поддержку!)"
                ]
            }
        units_list.append({
            "id": u_id,
            "title": f"Раздел {u_id}",
            "guidebook": gb
        })
    data["units"] = units_list
    
    # 2. Обогащаем словарь уроков
    for lesson in lessons:
        u_id = lesson.get("unit_id", 1)
        existing_vocab = lesson.get("vocabulary", [])
        
        # Если в уроке мало слов или нет существительных с артиклями, добавляем из нашей базы
        unit_vocab = VOCAB_DATABASE_BY_UNIT.get(u_id, VOCAB_DATABASE_BY_UNIT.get(1))
        
        # Дополняем словами с артиклями
        for word in unit_vocab:
            if not any(v.get("german") == word.get("german") for v in existing_vocab):
                existing_vocab.append({
                    "german": word.get("german"),
                    "article": word.get("article", ""),
                    "gender": word.get("gender", ""),
                    "russian": word.get("russian"),
                    "example": word.get("example"),
                    "example_translation": word.get("russian"),
                    "voice_hint": "de-DE-KatjaNeural"
                })
                
        lesson["vocabulary"] = existing_vocab
        # Добавляем ссылку на справочник юнита
        lesson["guidebook"] = UNIT_GUIDEBOOKS.get(u_id, UNIT_GUIDEBOOKS.get(1))
        
    with open(COURSE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully enriched {len(lessons)} lessons and 36 unit guidebooks!")
    return True

if __name__ == "__main__":
    enrich_course_data()
