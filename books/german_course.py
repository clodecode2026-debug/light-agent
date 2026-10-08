import os
import json
import logging

logger = logging.getLogger(__name__)

# Попытка загрузить полный 180-дневный курс (A1+ -> A2 -> B1)
COURSE_JSON_PATH = os.path.join(os.path.dirname(__file__), "german_180days_course.json")

def load_german_course_from_file():
    if os.path.exists(COURSE_JSON_PATH):
        try:
            with open(COURSE_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Нормализация полей для совместимости
                if "levels" not in data:
                    data["levels"] = ["A1+", "A2", "B1"]
                if "study_plan" not in data and "stages" in data:
                    data["study_plan"] = [
                        {
                            "stage": s["stage"],
                            "duration": s.get("days", "30-90 дней"),
                            "goal": s.get("goal", ""),
                            "modules_count": s.get("units", "")
                        }
                        for s in data["stages"]
                    ]
                logger.info(f"Успешно загружен 180-дневный курс немецкого языка: {len(data.get('lessons', []))} уроков.")
                return data
        except Exception as e:
            logger.error(f"Ошибка загрузки german_180days_course.json: {e}")
    return None

GERMAN_COURSE_DATA = load_german_course_from_file()

if not GERMAN_COURSE_DATA:
    GERMAN_COURSE_DATA = {
        "title": "Курс немецкого языка для Алины",
        "duration_days": 180,
        "daily_minutes": 30,
        "total_units": 36,
        "levels": ["A1+", "A2", "B1"],
        "study_plan": [
            {
                "stage": "A1+ Уверенный старт (Трамплин)",
                "duration": "Дни 1-30",
                "goal": "Активация базы, снятие каши в грамматике, порядок слов, nicht/kein, Akkusativ, модальные глаголы.",
                "modules_count": "Юниты 1-6"
            },
            {
                "stage": "A2 Жизнь в Германии и ведомства",
                "duration": "Дни 31-90",
                "goal": "Bürgeramt, Jobcenter, врачи, аптека, аренда квартиры, Dativ, Wechselpräpositionen, все формы Perfekt.",
                "modules_count": "Юниты 7-18"
            },
            {
                "stage": "B1 Профессиональный немецкий и свобода",
                "duration": "Дни 91-180",
                "goal": "Работа, резюме Lebenslauf, собеседование Vorstellungsgespräch, союзы weil/dass/obwohl, Konjunktiv II, свободная речь.",
                "modules_count": "Юниты 19-36"
            }
        ],
        "lessons": [
        # ==========================================
        # УРОВЕНЬ A1 (5 УРОКОВ)
        # ==========================================
        {
            "id": "a1_1",
            "level": "A1",
            "title": "Урок 1: Первые шаги — Знакомство и вежливость (Begrüßung & Kennenlernen)",
            "grammar": "Личные местоимения (ich, du, er/sie, wir, ihr, sie/Sie) и спряжение глаголов sein (быть) и heißen (зваться) в Präsens.",
            "rule_explanation": "Глагол в немецком повествовательном предложении ВСЕГДА стоит на 2-м месте: 'Ich heiße Alina' или 'Heute bin ich glücklich'.",
            "vocabulary": [
                {"german": "Guten Tag! Wie heißen Sie?", "russian": "Добрый день! Как вас зовут? (вежливо)", "transcription": "[гу́тэн та́г! ви́ ха́йсэн зи́?]", "example": "Guten Tag! Wie heißen Sie? — Ich heiße Alina.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Ich heiße Alina und ich lerne Deutsch.", "russian": "Меня зовут Алина, и я учу немецкий.", "transcription": "[их ха́йсэ али́на унт их лэ́рнэ дойч]", "example": "Ich heiße Alina und ich lerne Deutsch jeden Tag.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Freut mich sehr, Sie kennenzulernen.", "russian": "Очень приятно познакомиться с вами.", "transcription": "[фройт михь зэ́йр, зи́ кэ́нэнцулэрнэн]", "example": "Guten Tag, Frau Müller! Freut mich sehr, Sie kennenzulernen.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Wie geht es dir heute?", "russian": "Как у тебя сегодня дела?", "transcription": "[ви́ гэйт эс ди́р хо́йтэ?]", "example": "Hallo! Wie geht es dir heute? — Mir geht es sehr gut!", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Mir geht es super, danke! Und dir?", "russian": "У меня всё супер, спасибо! А у тебя?", "transcription": "[ми́р гэйт эс зу́пэр, да́нкэ! унт ди́р?]", "example": "Danke der Nachfrage, mir geht es super!", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Auf Wiedersehen! Bis bald!", "russian": "До свидания! До скорого!", "transcription": "[а́уф ви́дэрзэен! бис ба́льт!]", "example": "Tschüss! Auf Wiedersehen und bis bald!", "voice_hint": "de-DE-ConradNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Вы встретили новую знакомую в языковой школе. Поздоровайтесь и представьтесь.",
                "example": "Hallo! Ich heiße Alina. Wie heißt du?",
                "tips": "Для дружеского общения используйте 'du', для официального — 'Sie'."
            }
        },
        {
            "id": "a1_2",
            "level": "A1",
            "title": "Урок 2: В магазине и кафе (Einkaufen & Im Café)",
            "grammar": "Артикли (der, die, das), винительный падеж Akkusativ (den, die, das) и вежливая форма заказа 'Ich möchte...'.",
            "rule_explanation": "В Akkusativ изменяется только мужской род: der Kaffee -> Ich möchte den Kaffee. Женский (die) и средний (das) остаются без изменений.",
            "vocabulary": [
                {"german": "Ich möchte bitte einen Kaffee und ein Croissant.", "russian": "Я хотела бы кофе и круассан, пожалуйста.", "transcription": "[их мё́хьтэ би́тэ а́йнэн ка́фэ унт айн круасса́н]", "example": "Guten Morgen, ich möchte bitte einen Kaffee.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Was kostet das zusammen?", "russian": "Сколько это стоит вместе?", "transcription": "[вас ко́стэт дас цуза́мэн?]", "example": "Entschuldigung, was kostet das zusammen?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Das macht zusammen vier Euro fünfzig.", "russian": "С вас четыре евро пятьдесят.", "transcription": "[дас ма́хт цуза́мэн фи́р о́йро фю́нфцихь]", "example": "Das macht zusammen vier Euro fünfzig, bitte.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Kann ich mit Karte bezahlen?", "russian": "Могу ли я оплатить картой?", "transcription": "[кан их мит ка́ртэ бэца́лэн?]", "example": "Kann ich hier kontaktlos mit Karte bezahlen?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ja, natürlich. Vielen Dank!", "russian": "Да, конечно. Большое спасибо!", "transcription": "[йа, натю́рлихь. фи́лэн данк!]", "example": "Ja, natürlich geht das. Vielen Dank!", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Einen schönen Tag noch!", "russian": "Хорошего вам дня!", "transcription": "[а́йнэн шё́нэн та́г нох!]", "example": "Danke gleichfalls! Einen schönen Tag noch!", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Закажите в немецком кафе зелёный чай и спросите, принимают ли они карту.",
                "example": "Ich möchte bitte einen grünen Tee. Kann ich mit Karte bezahlen?",
                "tips": "Фраза 'Ich möchte bitte...' — идеальный универсальный ключ к вежливому заказу."
            }
        },
        {
            "id": "a1_3",
            "level": "A1",
            "title": "Урок 3: Семья, дом и чувства (Familie, Zuhause & Gefühle)",
            "grammar": "Притяжательные местоимения (mein/meine, dein/deine) и модальный глагол können (мочь, уметь).",
            "rule_explanation": "Если существительное женского рода или во множественном числе, добавляется окончание -e: mein Mann (мужской), но meine Familie, meine Gefühle (женский).",
            "vocabulary": [
                {"german": "Das ist mein Mann Roman, wir halten immer zusammen.", "russian": "Это мой муж Роман, мы всегда держимся вместе.", "transcription": "[дас ист майн ман ро́ман, ви́р ха́льтэн и́мэр цуза́мэн]", "example": "Das ist mein Mann Roman, er unterstützt mich immer.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich bin heute ein bisschen müde.", "russian": "Я сегодня немного устала.", "transcription": "[их бин хо́йтэ айн би́схен мю́дэ]", "example": "Nach der Arbeit bin ich heute ein bisschen müde.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Du brauchst etwas Ruhe und Entspannung.", "russian": "Тебе нужен отдых и расслабление.", "transcription": "[ду бра́ухст э́твас ру́э унт энтшпа́нунг]", "example": "Komm her, du brauchst etwas Ruhe und Entspannung.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Ich liebe gemütliche Abende zu Hause.", "russian": "Я обожаю уютные вечера дома.", "transcription": "[их ли́бэ гэмю́тлихьэ а́бэндэ цу ха́узэ]", "example": "Mit einer Tasse Tee liebe ich gemütliche Abende zu Hause.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Alles wird gut, mach dir keine Sorgen.", "russian": "Всё будет хорошо, не переживай.", "transcription": "[а́лэс вирт гут, мах ди́р ка́йнэ зо́ргэн]", "example": "Atme tief durch, alles wird gut, mach dir keine Sorgen.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Ich fühle mich wohl und geborgen.", "russian": "Я чувствую себя спокойно и защищенно.", "transcription": "[их фю́лэ михь во́ль унт гэбо́ргэн]", "example": "Hier fühle ich mich vollkommen wohl und geborgen.", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Поделитесь с близким человеком, что вам нужен теплый чай и спокойный вечер.",
                "example": "Ich bin heute müde. Lass uns einen Tee trinken und uns ausruhen.",
                "tips": "'sich ausruhen' — отдыхать, переводить дыхание."
            }
        },
        {
            "id": "a1_4",
            "level": "A1",
            "title": "Урок 4: Ориентация в городе и транспорт (In der Stadt & Unterwegs)",
            "grammar": "Вопросительные слова (Wo? Wohin? Wie komme ich zu...?) и предлог nach/zu.",
            "rule_explanation": "Вопрос 'Wo ist...?' (где находится?) требует Dativ. Для направления движения к объекту используется предлог 'zu' + Dativ: zum Bahnhof, zur Apotheke.",
            "vocabulary": [
                {"german": "Entschuldigung, wo ist die nächste Apotheke?", "russian": "Извините, где ближайшая аптека?", "transcription": "[энтшу́льдигунг, во́ ист ди́ нэ́хьстэ апотэ́кэ?]", "example": "Entschuldigung, wo ist hier die nächste Apotheke bitte?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Gehen Sie geradeaus und dann nach rechts.", "russian": "Идите прямо, а затем направо.", "transcription": "[гэ́ен зи́ гэра́дэа́ус унт дан нах рє́хьтс]", "example": "Gehen Sie zweihundert Meter geradeaus und dann nach rechts.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Wo kann ich eine Fahrkarte kaufen?", "russian": "Где я могу купить билет на транспорт?", "transcription": "[во́ кан их а́йнэ фа́ркартэ ка́уфэн?]", "example": "Am Automaten können Sie eine Fahrkarte kaufen.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Fährt dieser Bus zum Hauptbahnhof?", "russian": "Этот автобус едет к главному вокзалу?", "transcription": "[фэ́рт ди́зэр бус цум ха́уптбанхоф?]", "example": "Entschuldigung, fährt dieser Bus direkt zum Hauptbahnhof?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Vielen Dank für Ihre Hilfe!", "russian": "Большое спасибо за вашу помощь!", "transcription": "[фи́лэн данк фюр и́рэ хи́льфэ!]", "example": "Sie haben mir sehr geholfen, vielen Dank für Ihre Hilfe!", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Спросите прохожего на улице, как пройти к вокзалу или аптеке.",
                "example": "Entschuldigung, wie komme ich zum Bahnhof bitte?",
                "tips": "Всегда начинайте вопрос со слова 'Entschuldigung' (Извините)."
            }
        },
        {
            "id": "a1_5",
            "level": "A1",
            "title": "Урок 5: Время, дни недели и распорядок (Uhrzeit & Tagesablauf)",
            "grammar": "Обозначение времени (Um wie viel Uhr? Um 8 Uhr) и отделяемые приставки (aufstehen -> ich stehe auf).",
            "rule_explanation": "В немецком отделяемые приставки (auf-, an-, ein-, aus-) уходят в САМЫЙ КОНЕЦ предложения в Präsens: 'Ich stehe um 7 Uhr auf'.",
            "vocabulary": [
                {"german": "Wie spät ist es jetzt?", "russian": "Сколько сейчас времени?", "transcription": "[ви́ шпэ́йт ист эс йетцт?]", "example": "Entschuldigung, wie spät ist es jetzt? — Es ist zehn Uhr.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich stehe morgens um sieben Uhr auf.", "russian": "Я встаю по утрам в семь часов.", "transcription": "[их штэ́е мо́ргэнс ум зи́бэн у́р а́уф]", "example": "Unter der Woche stehe ich morgens um sieben Uhr auf.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Am Wochenende schlafe ich gerne länger.", "russian": "На выходных я с удовольствием сплю дольше.", "transcription": "[ам во́хэнэндэ шла́фэ их гэ́рнэ лэ́нгэр]", "example": "Am Wochenende schlafe ich gerne länger und entspanne mich.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Haben Sie am Montag Zeit für ein Treffen?", "russian": "У вас есть время для встречи в понедельник?", "transcription": "[ха́бэн зи́ ам мо́нтак цайт фюр айн трэ́фэн?]", "example": "Haben Sie am Montag um vierzehn Uhr Zeit für ein Treffen?", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Ich wünsche dir einen wunderschönen Tag!", "russian": "Я желаю тебе прекрасного дня!", "transcription": "[их вю́ншэ ди́р а́йнэн ву́ндэршёнэн та́к!]", "example": "Pass auf dich auf und ich wünsche dir einen wunderschönen Tag!", "voice_hint": "de-DE-ConradNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Договоритесь с подругой о встрече за кофе в субботу.",
                "example": "Hast du am Samstag um 15 Uhr Zeit für einen Kaffee?",
                "tips": "С днями недели используется предлог 'am' (am Samstag, am Montag)."
            }
        },

        # ==========================================
        # УРОВЕНЬ A2 (5 УРОКОВ)
        # ==========================================
        {
            "id": "a2_1",
            "level": "A2",
            "title": "Урок 6: Официальные визиты: Bürgeramt & Jobcenter",
            "grammar": "Модальные глаголы müssen (должен), dürfen (иметь право/разрешение) и прошедшее время Perfekt со слабыми глаголами.",
            "rule_explanation": "В Perfekt вспомогательный глагол (haben/sein) стоит на 2-м месте, а форма Partizip II (ge...t) — строго в самом конце предложения: 'Ich habe Unterlagen geschickt'.",
            "vocabulary": [
                {"german": "Ich habe einen Termin um zehn Uhr.", "russian": "У меня запись (термин) на десять часов.", "transcription": "[их ха́бэ а́йнэн тэрми́н ум цэ́йн у́р]", "example": "Guten Tag, ich habe einen Termin um zehn Uhr bei Frau Schmidt.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Hier sind meine Unterlagen und mein Pass.", "russian": "Вот мои документы и мой паспорт.", "transcription": "[хи́р зинт ма́йнэ у́нтэрлагэн унт майн пас]", "example": "Hier sind meine Unterlagen, mein Pass und das Anmeldeformular.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Füllen Sie bitte dieses Formular aus.", "russian": "Заполните, пожалуйста, этот бланк.", "transcription": "[фю́лэн зи́ би́тэ ди́зэс формуля́р а́ус]", "example": "Nehmen Sie Platz und füllen Sie bitte dieses Formular aus.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Ich habe die Bestätigung per E-Mail geschickt.", "russian": "Я отправила подтверждение по электронной почте.", "transcription": "[их ха́бэ ди́ бэштэ́тигунг пэр и́мэйл гэши́кт]", "example": "Gestern habe ich die Bestätigung per E-Mail geschickt.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Wann bekomme ich den schriftlichen Bescheid?", "russian": "Когда я получу письменное официальное решение?", "transcription": "[ван бэко́мэ их дэн шри́фтлихьэн бэша́йт?]", "example": "Wann bekomme ich den schriftlichen Bescheid per Post?", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Вы пришли в ведомство по термину. Сообщите сотруднику о записи и передайте документы.",
                "example": "Guten Tag! Ich habe einen Termin um 10 Uhr. Hier sind meine Dokumente.",
                "tips": "Слово 'der Termin' в Германии — ключ к любому официальному учреждению."
            }
        },
        {
            "id": "a2_2",
            "level": "A2",
            "title": "Урок 7: Здоровье и визит к врачу (Beim Arzt & Wohlbefinden)",
            "grammar": "Дательный падеж Dativ с предлогами (mit, nach, bei, seit, von, zu) и выражение симптомов: 'Mir tut ... weh'.",
            "rule_explanation": "Конструкция боли: 'Mir tut der Kopf weh' (болит голова, ед.ч.) или 'Mir tun die Augen weh' (болят глаза, мн.ч.). Предлог 'seit' (с тех пор как) всегда требует Dativ: 'seit gestern'.",
            "vocabulary": [
                {"german": "Mir tut seit gestern der Rücken weh.", "russian": "У меня со вчерашнего дня болит спина.", "transcription": "[ми́р тут зайт гэ́стэрн дэр рю́кэн вэй]", "example": "Mir tut seit gestern der Rücken weh, besonders beim Sitzen.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich brauche ein Rezept für diese Medikamente.", "russian": "Мне нужен рецепт на эти лекарства.", "transcription": "[их бра́ухэ айн рэцэ́пт фюр ди́зэ медикаме́нтэ]", "example": "Herr Doktor, ich brauche ein neues Rezept für diese Medikamente.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ruhen Sie sich aus und trinken Sie viel Tee.", "russian": "Отдохните и пейте много чая.", "transcription": "[ру́эн зи́ зих а́ус унт три́нкэн зи́ фи́ль тэй]", "example": "Sie haben eine Erkältung. Ruhen Sie sich aus und trinken Sie viel Tee.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Ich fühle mich heute schon viel besser.", "russian": "Сегодня я чувствую себя уже намного лучше.", "transcription": "[их фю́лэ михь хо́йтэ шон филь бэ́сэр]", "example": "Dank der Ruhe fühle mich heute schon viel besser.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Gute Besserung! Passen Sie auf sich auf!", "russian": "Скорейшего выздоровления! Берегите себя!", "transcription": "[гу́тэ бэ́сэрунг! па́сэн зи́ а́уф зих а́уф!]", "example": "Gute Besserung, liebe Alina! Passen Sie gut auf sich auf!", "voice_hint": "de-DE-ConradNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Объясните доктору, что у вас болит голова и вы плохо спали.",
                "example": "Guten Tag, Herr Doktor. Mir tut der Kopf weh und ich habe schlecht geschlafen.",
                "tips": "Используйте 'Gute Besserung' для искреннего пожелания выздоровления."
            }
        },
        {
            "id": "a2_3",
            "level": "A2",
            "title": "Урок 8: Аренда жилья и обустройство (Wohnungssuche & Mietvertrag)",
            "grammar": "Предлоги двойного управления (Wechselpräpositionen: in, an, auf, unter, über, vor, hinter, neben, zwischen). Где? — Dativ, Куда? — Akkusativ.",
            "rule_explanation": "Вопрос 'Wo?' (состояние покоя) требует Dativ: 'Das Bild hängt an der Wand'. Вопрос 'Wohin?' (направление) требует Akkusativ: 'Ich hänge das Bild an die Wand'.",
            "vocabulary": [
                {"german": "Ich suche eine helle Zweizimmerwohnung.", "russian": "Я ищу светлую двухкомнатную квартиру.", "transcription": "[их зу́хэ а́йнэ хэ́лэ цва́йцимэрвонунг]", "example": "Mein Mann Roman und ich suchen eine ruhige Zweizimmerwohnung.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Wie hoch ist die Warmmiete inklusive Nebenkosten?", "russian": "Какова общая арендная плата включая коммуналку?", "transcription": "[ви́ хо́х ист ди́ ва́рммитэ инклюзи́вэ нэ́бэнкостэн?]", "example": "Können Sie mir sagen, wie hoch die Warmmiete inklusive Nebenkosten ist?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Die Wohnung liegt in einer sehr ruhigen Gegend.", "russian": "Квартира расположена в очень спокойном районе.", "transcription": "[ди́ во́нунг ли́кт ин а́йнэр зэ́йр ру́игэн гэ́гэнт]", "example": "Die Wohnung liegt in einer sehr ruhigen Gegend mit viel Grün.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Wann ist der nächste Besichtigungstermin?", "russian": "Когда ближайший просмотр квартиры?", "transcription": "[ван ист дэр нэ́хьстэ бэзи́хьтигунгстэрмин?]", "example": "Ich habe großes Interesse. Wann ist der nächste Besichtigungstermin?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Die Kaution beträgt drei Monatskaltmieten.", "russian": "Залог составляет три базовые месячные арендные платы.", "transcription": "[ди́ кауцьо́н бэтре́кт драй мо́натскальтмитэн]", "example": "Vor dem Einzug: Die Kaution beträgt drei Monatskaltmieten.", "voice_hint": "de-DE-ConradNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Спросите арендодателя о стоимости квартиры с коммунальными услугами и дате просмотра.",
                "example": "Guten Tag! Wie hoch ist die Warmmiete und wann kann ich die Wohnung besichtigen?",
                "tips": "Warmmiete = базовая аренда (Kaltmiete) + коммунальные расходы (Nebenkosten)."
            }
        },
        {
            "id": "a2_4",
            "level": "A2",
            "title": "Урок 9: Работа, резюме и коллеги (Arbeit, Lebenslauf & Kollegen)",
            "grammar": "Модальный глагол sollen (следует), прошедшее время Präteritum глаголов war/hatte и составные существительные.",
            "rule_explanation": "В устной речи формы 'ich war' (я была) и 'ich hatte' (у меня было) используются чаще, чем формы Perfekt с sein/haben.",
            "vocabulary": [
                {"german": "Ich habe meinen Lebenslauf vorbereitet.", "russian": "Я подготовила своё резюме (Lebenslauf).", "transcription": "[их ха́бэ ма́йнэн ле́бэнслауф фо́рбэрайтет]", "example": "Ich habe meinen Lebenslauf und meine Zeugnisse vorbereitet.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich habe viele Jahre Erfahrung in diesem Bereich.", "russian": "У меня многолетний опыт в этой сфере.", "transcription": "[их ха́бэ фи́лэ я́рэ эрфа́рунг ин ди́зэм бэра́йхь]", "example": "Ich lerne schnell und habe viele Jahre Erfahrung in diesem Bereich.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Meine Kollegen sind sehr hilfsbereit und freundlich.", "russian": "Мои коллеги очень отзывчивые и дружелюбные.", "transcription": "[ма́йнэ колэ́гэн зинт зэ́йр хи́льфсбрайт унт фро́йнтлихь]", "example": "Ich fühle mich wohl im Team, meine Kollegen sind sehr hilfsbereit.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Wir haben heute eine wichtige Teambesprechung.", "russian": "У нас сегодня важное командное совещание.", "transcription": "[ви́р ха́бэн хо́йтэ а́йнэ ви́хьтигэ ти́мбэшпрэхунг]", "example": "Um vierzehn Uhr haben wir eine wichtige Teambesprechung.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Ich freue mich auf die Zusammenarbeit.", "russian": "Я с нетерпением жду совместной работы.", "transcription": "[их фро́йэ михь а́уф ди́ цуза́мэнарбайт]", "example": "Vielen Dank für das Gespräch, ich freue mich auf die Zusammenarbeit.", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Расскажите на собеседовании или коллеге о вашем опыте и готовности учиться новому.",
                "example": "Guten Tag! Ich habe viel Erfahrung und lerne jeden Tag Neues.",
                "tips": "Немцы ценят пунктуальность, структурированность и открытое желание учиться."
            }
        },
        {
            "id": "a2_5",
            "level": "A2",
            "title": "Урок 10: Покупки одежды, размеры и возврат (Kleidung & Umtausch)",
            "grammar": "Степени сравнения прилагательных (gut - besser - am besten, groß - größer - am größten) и глагол gefallen (нравиться).",
            "rule_explanation": "Глагол 'gefallen' согласуется с тем, что нравится, а человек стоит в Dativ: 'Das Kleid gefällt mir' (Платье нравится мне).",
            "vocabulary": [
                {"german": "Welche Größe haben Sie bitte?", "russian": "Какой у вас размер, пожалуйста?", "transcription": "[вэ́льхэ грё́сэ ха́бэн зи́ би́тэ?]", "example": "Welche Größe haben Sie? — Ich trage Größe achtunddreißig.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Dieses Kleid gefällt mir sehr gut.", "russian": "Это платье мне очень нравится.", "transcription": "[ди́зэс клайт гэфэ́льт ми́р зэ́йр гут]", "example": "Die Farbe ist wunderschön, dieses Kleid gefällt mir sehr gut.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Kann ich das anprobieren? Wo sind die Umkleidekabinen?", "russian": "Могу ли я это примерить? Где примерочные кабинки?", "transcription": "[кан их дас а́нпробирен? во́ зинт ди́ у́мклайдэкабинэн?]", "example": "Entschuldigung, kann ich das anprobieren? Wo ist die Umkleidekabine?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Haben Sie diese Bluse eine Nummer kleiner?", "russian": "У вас есть эта блузка на один размер меньше?", "transcription": "[ха́бэн зи́ ди́зэ блу́зэ а́йнэ ну́мэр кла́йнэр?]", "example": "Sie ist etwas weit. Haben Sie diese Bluse eine Nummer kleiner?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich möchte diesen Artikel bitte umtauschen.", "russian": "Я хотела бы обменять этот товар, пожалуйста.", "transcription": "[их мё́хьтэ ди́зэн арти́кэль би́тэ у́мтаушэн]", "example": "Hier ist der Kassenbon, ich möchte diesen Artikel bitte umtauschen.", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Спросите продавца, где находится примерочная, и попросите вещь другого размера.",
                "example": "Entschuldigung, wo ist die Umkleidekabine? Haben Sie das eine Nummer größer?",
                "tips": "Сохраняйте чек (der Kassenbon) для возможности обмена или возврата."
            }
        },

        # ==========================================
        # УРОВЕНЬ B1 (5 УРОКОВ)
        # ==========================================
        {
            "id": "b1_1",
            "level": "B1",
            "title": "Урок 11: Сложные предложения: Причины и уступки (weil, dass, obwohl)",
            "grammar": "Придаточные предложения (Nebensätze) с подчинительными союзами weil (потому что), obwohl (хотя), dass (что).",
            "rule_explanation": "В придаточном предложении спрягаемый глагол ВСЕГДА уходит на САМОЕ ПОСЛЕДНЕЕ место: 'Ich lerne Deutsch, weil ich in Deutschland leben und mich wohlfühlen WILL'.",
            "vocabulary": [
                {"german": "Ich lerne Deutsch, weil ich mich voll integrieren möchte.", "russian": "Я учу немецкий, потому что хочу полноценно интегрироваться.", "transcription": "[их лэ́рнэ дойч, вайл их михь фоль интэгри́рэн мё́хьтэ]", "example": "Ich lerne Deutsch, weil ich mich voll integrieren und frei sprechen möchte.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Obwohl es manchmal anstrengend ist, gebe ich niemals auf.", "russian": "Хотя иногда бывает утомительно, я никогда не сдаюсь.", "transcription": "[обво́ль эс ма́нхмаль а́нштрэнгант ист, гэ́йбэ их ни́мальс а́уф]", "example": "Obwohl es manchmal anstrengend ist, glaube ich fest an meinen Erfolg.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich glaube fest daran, dass Träume wahr werden können.", "russian": "Я твердо верю в то, что мечты могут сбываться.", "transcription": "[их гла́убэ фэст дара́н, дас трой́мэ вар вэ́рдэн кё́нэн]", "example": "Mit Geduld und Liebe glaube ich fest daran, dass Träume wahr werden.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Es ist wichtig, dass wir ehrlich über unsere Gefühle sprechen.", "russian": "Важно, чтобы мы искренне говорили о наших чувствах.", "transcription": "[эс ист ви́хьтих, дас ви́р э́йрлихь ю́бэр у́нзэрэ гэфю́лэ шпрэ́хэн]", "example": "In einer Partnerschaft ist es wichtig, dass wir ehrlich über Gefühle sprechen.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Da ich gut vorbereitet bin, fühle ich mich sicher.", "russian": "Поскольку я хорошо подготовилась, я чувствую себя уверенно.", "transcription": "[да их гут фо́рбэрайтет бин, фю́лэ их михь зи́хэр]", "example": "Da ich gut vorbereitet bin, habe ich keine Angst vor der Prüfung.", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Объясните собеседнику, почему вы продолжаете учиться, несмотря на усталость после рабочего дня.",
                "example": "Ich lerne jeden Tag Deutsch, obwohl ich oft müde bin, weil ich frei sprechen möchte.",
                "tips": "Следите за глаголом в самом конце придаточной части предложения!"
            }
        },
        {
            "id": "b1_2",
            "level": "B1",
            "title": "Урок 12: Психологическая рефлексия и личностный рост (Psychologie & Reflexion)",
            "grammar": "Конструкции um... zu + Infinitiv (для того чтобы) и сослагательное наклонение Konjunktiv II (wäre, hätte, würde).",
            "rule_explanation": "Konjunktiv II выражает вежливость, мечты и бережные размышления: 'Ich würde gerne...' (я бы хотела...), 'Wenn ich mehr Zeit hätte...' (если бы у меня было больше времени...).",
            "vocabulary": [
                {"german": "Ich brauche Zeit für mich, um neue Energie zu tanken.", "russian": "Мне нужно время для себя, чтобы восстановить силы (заправиться энергией).", "transcription": "[их бра́ухэ цайт фюр михь, ум но́йэ энэрги́ цу та́нкэн]", "example": "Nach einer harten Woche brauche ich Zeit für mich, um Energie zu tanken.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Wenn ich gestresst bin, hilft mir ein tiefer, bewusster Atemzug.", "russian": "Когда я в стрессе, мне помогает глубокий, осознанный вдох.", "transcription": "[вэн их гэштрэ́ст бин, хильфт ми́р айн ти́фэр бэву́стэр а́тэмцук]", "example": "Wenn ich gestresst bin, hilft mir ein tiefer Atemzug und Ruhe.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Jeder neue Tag ist eine Chance, glücklich zu sein.", "russian": "Каждый новый день — это шанс быть счастливой.", "transcription": "[е́дэр но́йэ так ист а́йнэ ша́нсэ, глю́клихь цу зайн]", "example": "Vergiss das Gestern, jeder neue Tag ist eine Chance, glücklich zu sein.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich bin stolz auf meinen persönlichen Fortschritt im Leben.", "russian": "Я горжусь своим личным прогрессом в жизни.", "transcription": "[их бин штольц а́уф ма́йнэн пэрзё́нлихьэн фо́ртшрит им ле́бэн]", "example": "Schritt für Schritt: Ich bin stolz auf meinen persönlichen Fortschritt.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Es ist in Ordnung, Pausen zu machen und nicht perfekt zu sein.", "russian": "Это абсолютно нормально — делать паузы и не быть идеальной.", "transcription": "[эс ист ин о́рднунг, па́узэн цу ма́хэн унт нихьт пэрфэ́кт цу зайн]", "example": "Erlaube dir Schwäche: Es ist in Ordnung, Pausen zu machen.", "voice_hint": "de-DE-ConradNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Сформулируйте на немецком языке вашу главную цель в жизни и то, что дает вам внутреннее спокойствие.",
                "example": "Mein Ziel ist innere Ruhe. Ich nehme mir bewusst Zeit, um neue Kraft zu tanken.",
                "tips": "'stolz auf (+Akk) sein' — гордиться чем-то."
            }
        },
        {
            "id": "b1_3",
            "level": "B1",
            "title": "Урок 13: Дискуссия, аргументы и выражение мнения (Meinung äußern)",
            "grammar": "Вводные конструкции выражения мнения: Meiner Meinung nach, Ich bin der Ansicht, dass..., Einerseits... andererseits.",
            "rule_explanation": "Конструкция 'Meiner Meinung nach' требует инверсии: глагол стоит сразу после неё: 'Meiner Meinung nach IST das wichtig'.",
            "vocabulary": [
                {"german": "Meiner Meinung nach sollten wir einen Kompromiss finden.", "russian": "По моему мнению, нам следует найти компромисс.", "transcription": "[ма́йнэр ма́йнунг нах зо́льтэн ви́р а́йнэн компроми́с фи́ндэн]", "example": "Meiner Meinung nach sollten wir offen darüber sprechen und einen Kompromiss finden.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich bin fest davon überzeugt, dass wir das gemeinsam schaffen.", "russian": "Я твердо убеждена, что мы справимся с этим вместе.", "transcription": "[их бин фэст дафо́н юбэрцо́йкт, дас ви́р дас гэма́йнзам ша́фэн]", "example": "Zusammen mit Roman bin ich überzeugt, dass wir das gemeinsam schaffen.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Einerseits verstehe ich dich, andererseits habe ich Bedenken.", "russian": "С одной стороны, я тебя понимаю, с другой — у меня есть сомнения.", "transcription": "[а́йнэрзайтс фэрштэ́е их дихь, а́ндэрэрзайтс ха́бэ их бэдэ́нкэн]", "example": "Einerseits verstehe ich deine Sicht, andererseits müssen wir vorsichtig sein.", "voice_hint": "de-DE-ConradNeural"},
                {"german": "Darf ich dazu etwas hinzufügen?", "russian": "Могу ли я добавить к этому кое-что?", "transcription": "[дарф их дацу́ э́твас хи́нцуфюгэн?]", "example": "Das ist ein guter Punkt, darf ich dazu kurz etwas hinzufügen?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Da stimme ich dir vollkommen zu.", "russian": "Здесь я с тобой полностью согласна.", "transcription": "[да шти́мэ их ди́р фолько́мэн цу]", "example": "Genau so sehe ich das auch, da stimme ich dir vollkommen zu.", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Выскажите свое мнение в беседе и мягко согласитесь или не согласитесь с аргументом.",
                "example": "Meiner Meinung nach ist das ein guter Schritt, aber wir brauchen mehr Zeit.",
                "tips": "Используйте 'Einerseits... andererseits' для взвешенной аргументации."
            }
        },
        {
            "id": "b1_4",
            "level": "B1",
            "title": "Урок 14: Успешное собеседование и профессиональные навыки (Vorstellungsgespräch)",
            "grammar": "Страдательный залог Passiv в настоящем времени (werden + Partizip II) и косвенные вопросы.",
            "rule_explanation": "В Passiv Präsens: объект + wird/werden + Partizip II: 'Die Dokumente werden geprüft' (Документы проверяются).",
            "vocabulary": [
                {"german": "Ich freue mich sehr über die Einladung zum Vorstellungsgespräch.", "russian": "Я очень рада приглашению на собеседование.", "transcription": "[их фро́йэ михь зэ́йр ю́бэр ди́ а́йнладунг цум фо́рштэлунгсгэшпрэхь]", "example": "Guten Tag! Ich freue mich sehr über die Einladung zum Vorstellungsgespräch.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Zu meinen Stärken gehören Zuverlässigkeit und Teamgeist.", "russian": "К моим сильным сторонам относятся надежность и командный дух.", "transcription": "[цу ма́йнэн штэ́ркэн гэхё́рэн цу́фэрлесихькайт унт ти́мгайст]", "example": "Zu meinen größten Stärken gehören Zuverlässigkeit, Empathie und Teamgeist.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Könnten Sie mir bitte die Aufgaben genauer beschreiben?", "russian": "Не могли бы вы подробнее описать задачи?", "transcription": "[кё́нтэн зи́ ми́р би́тэ ди́ а́уфгабэн гэна́уэр бэшра́йбэн?]", "example": "Das klingt spannend. Könnten Sie mir bitte die Aufgaben genauer beschreiben?", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich bin bereit, mich schnell in neue Bereiche einzuarbeiten.", "russian": "Я готова быстро осваивать новые сферы и вникать в работу.", "transcription": "[их бин бэра́йт, михь шнэль ин но́йэ бэра́йхэ а́йнцуарбайтэн]", "example": "Ich habe hohe Motivation und bin bereit, mich schnell einzuarbeiten.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Vielen Dank für das angenehme und informative Gespräch.", "russian": "Большое спасибо за приятную и содержательную беседу.", "transcription": "[фи́лэн данк фюр дас а́нгэнэймэ унт информати́вэ гэшпрэ́хь]", "example": "Ich habe einen sehr guten Eindruck, vielen Dank für das angenehme Gespräch.", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Ответьте на собеседовании о ваших сильных сторонах и поблагодарите за беседу.",
                "example": "Meine Stärken sind Zuverlässigkeit und Engagement. Ich freue mich auf die Chance.",
                "tips": "Уверенная улыбка и четкие формулировки производят отличное впечатление."
            }
        },
        {
            "id": "b1_5",
            "level": "B1",
            "title": "Урок 15: Уверенная жизнь в Германии, будущее и мечты (Zukunft & Selbstvertrauen)",
            "grammar": "Будущее время Futur I (werden + Infinitiv) и придаточные времени (wenn, als, während, seitdem).",
            "rule_explanation": "Futur I образуется с помощью вспомогательного глагола 'werden' на 2-м месте и инфинитива смыслового глагола в самом конце: 'Ich werde mein Ziel erreichen'.",
            "vocabulary": [
                {"german": "Ich werde mein Ziel mit Geduld und Zuversicht erreichen.", "russian": "Я достигну своей цели с терпением и уверенностью.", "transcription": "[их вэ́рдэ майн циль мит гэду́льт унт цу́фэрзихьт эрра́йхэн]", "example": "Schritt für Schritt werde ich mein Ziel mit Geduld und Zuversicht erreichen.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Deutschland ist zu einem vertrauten Ort für mich geworden.", "russian": "Германия стала для меня знакомым и привычным местом.", "transcription": "[до́йчлант ист цу а́йнэм фэртра́утэн орт фюр михь гэво́рдэн]", "example": "Mit jedem Tag fühle ich mich sicherer, Deutschland ist vertraut geworden.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Gemeinsam mit meinem Mann schauen wir voller Hoffnung nach vorne.", "russian": "Вместе с моим мужем мы с надеждой смотрим вперед.", "transcription": "[гэма́йнзам мит ма́йнэм ман ша́уэн ви́р фо́лэр хо́фнунг нах фо́рнэ]", "example": "Wir sind ein starkes Team und schauen voller Hoffnung nach vorne.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich vertraue auf meine Fähigkeiten und meine innere Stärke.", "russian": "Я доверяю своим способностям и своей внутренней силе.", "transcription": "[их фэртра́уэ а́уф ма́йнэ фэ́ихькайтэн унт ма́йнэ и́нэрэ штэ́ркэ]", "example": "Was auch immer kommt: Ich vertraue auf meine Fähigkeiten und innere Stärke.", "voice_hint": "de-DE-KatjaNeural"},
                {"german": "Ich bin dankbar für jeden Tag des Lernens und des Wachsens.", "russian": "Я благодарна за каждый день учебы и личностного роста.", "transcription": "[их бин да́нкбар фюр е́дэн так дэс лэ́рнэнс унт дэс ва́хсэнс]", "example": "Das Leben ist eine Reise, und ich bin dankbar für jeden Tag des Wachsens.", "voice_hint": "de-DE-KatjaNeural"}
            ],
            "dialogue_simulator": {
                "situation": "Подведите итог своего прогресса в немецком языке и поделитесь планами на будущее.",
                "example": "Ich habe schon so viel gelernt und ich werde weiterhin mit Freude mein Deutsch verbessern.",
                "tips": "Похвалите себя за каждый пройденный урок — это главный закон коучинга!"
            }
        }
    ]
}


def get_german_course():
    return GERMAN_COURSE_DATA
