import os
import json
import logging
import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Попытка импорта Google GenAI SDK (если есть)
try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# Попытка импорта OpenAI SDK (для моста Antigravity Bridge)
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from books.knowledge_base import get_knowledge_base_prompt

class ModelRouter:
    """
    Интеллектуальный роутер моделей с учётом:
    - Актуальности на 7 октября 2026 года
    - Суточного лимита вызовов (с автосбросом раз в сутки в 00:00 UTC)
    - Временных блокировок при ошибках (Rate Limit 429, Timeout, Unavailable 503)
    - Каскадного переключения: сначала быстрые и умные модели дня, затем резерв
    """
    def __init__(self):
        self.last_reset_day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        self.call_counts: Dict[str, int] = {}
        self.cooldowns: Dict[str, float] = {}

    def check_daily_reset(self):
        current_day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        if current_day != self.last_reset_day:
            logger.info(f"Новые сутки ({current_day})! Автоматический сброс дневных лимитов моделей.")
            self.last_reset_day = current_day
            self.call_counts.clear()
            self.cooldowns.clear()

    def is_available(self, model: str) -> bool:
        self.check_daily_reset()
        now = datetime.datetime.now().timestamp()
        if self.cooldowns.get(model, 0) > now:
            return False
        return True

    def mark_used(self, model: str):
        self.check_daily_reset()
        self.call_counts[model] = self.call_counts.get(model, 0) + 1

    def mark_error(self, model: str, duration_sec: float = 60.0):
        now = datetime.datetime.now().timestamp()
        self.cooldowns[model] = now + duration_sec
        logger.warning(f"Модель {model} временно отправлена в кулдаун на {duration_sec}с")

class AIFeminineCoach:
    def __init__(self):
        self.router = ModelRouter()
        
        # Настройки моста Antigravity Bridge (OpenAI-compatible)
        self.ag_base_url = os.environ.get("AG_BASE_URL", "https://agent-master-server.onrender.com/v1").rstrip("/")
        self.ag_api_key = os.environ.get("AG_API_KEY", "sk-antigravity-master-roman")
        self.ag_client = None
        if HAS_OPENAI and self.ag_api_key:
            try:
                # max_retries=0 чтобы при задержке сразу переходить к следующей модели каскада
                self.ag_client = OpenAI(base_url=self.ag_base_url, api_key=self.ag_api_key, timeout=30.0, max_retries=0)
                logger.info(f"OpenAI-совместимый клиент успешно подключен к {self.ag_base_url}")
            except Exception as e:
                logger.error(f"Ошибка создания OpenAI клиента: {e}")

        # Настройки прямого Google GenAI
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.genai_client = None
        if HAS_GENAI and self.gemini_key:
            try:
                self.genai_client = genai.Client(api_key=self.gemini_key)
                logger.info("Google GenAI Client успешно инициализирован")
            except Exception as e:
                logger.error(f"Ошибка инициализации GenAI Client: {e}")

    def _get_system_prompt(self, dossier: Optional[Dict[str, Any]] = None, is_voice_mode: bool = False, german_context: Optional[Dict[str, Any]] = None) -> str:
        # СПЕЦИАЛЬНЫЙ РЕЖИМ: НЕМЕЦКИЙ ЯЗЫКОВОЙ РЕЧЕВОЙ КОУЧ (НЕ СБИВАЕТ ПСИХОЛОГА)
        if german_context:
            lesson_title = german_context.get("title", "")
            lesson_level = german_context.get("level", "A1+")
            lesson_grammar = german_context.get("grammar", "")
            lesson_situation = german_context.get("situation", "")
            vocab_list = [v.get("german", "") for v in german_context.get("vocabulary", [])[:6]]
            vocab_sample = ", ".join(vocab_list)

            return f"""Ты — персональный речевой тренажер немецкого языка (Sprachcoach) для Алины.
Сейчас проходит 5-минутная разговорная тренировка Live Voice по конкретному уроку:
УРОК: {lesson_title} (Уровень {lesson_level})
СИТУАЦИЯ В ГЕРМАНИИ: {lesson_situation}
ГРАММАТИЧЕСКИЙ ФОКУС: {lesson_grammar}
КЛЮЧЕВЫЕ ФРАЗЫ: {vocab_sample}

ПРАВИЛА ТВОЕГО ПОВЕДЕНИЯ:
1. Забудь режим психолога! В этой сессии ты — доброжелательный немецкий собеседник (чиновник, врач, продавец, коллега или терпеливый наставник).
2. Общайся на простом, естественном немецком языке уровня {lesson_level}.
3. ОБЯЗАТЕЛЬНО: к каждой своей немецкой фразе сразу давай в скобках понятный перевод на русский язык и подсказку, как ответить.
4. Отвечай кратко (1-2 короткие фразы на немецком + русский перевод в скобках + 1 вопрос), чтобы Алина не перегружалась и успевала отвечать.
5. Если Алина делает паузы или запинается — дай ей время, не перебивай, подбодри: "Keine Panik! Du schaffst das!".
6. Если Алина делает ошибку в порядке слов или падеже — мягко подскажи: "Отличная мысль! По-немецки правильнее сказать: [...] Повтори за мной!".
7. Хвали за каждое сказанное слово: "Toll, Alina!", "Super gemacht!".
"""

        # Загрузка расширенного профиля долговременной памяти Алины
        mem_profile = None
        mem_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "alina_memory_profile.json")
        if os.path.exists(mem_file):
            try:
                with open(mem_file, "r", encoding="utf-8") as mf:
                    mem_profile = json.load(mf)
            except Exception as e:
                logger.warning(f"Memory profile load notice: {e}")

        dossier_data = mem_profile or dossier or {
            "name": "Алина",
            "age": 35,
            "birthday": "25 сентября",
            "nationality": "Украинка (родом из Украины)",
            "husband": "Роман",
            "goals": ["Уверенный немецкий B1", "Психологическое благополучие и ресурс"]
        }
        dossier_info = f"\n\nПЕРСОНАЛЬНОЕ ДОСЬЕ И ПАМЯТЬ ОБ АЛИНЕ:\n{json.dumps(dossier_data, ensure_ascii=False, indent=2)}"

        kb_prompt = get_knowledge_base_prompt()

        if is_voice_mode:
            return f"""Ты — чуткий, живой, дипломированный психолог-собеседник и личный коуч для Алины (35 лет, украинка, любящий муж Роман).

ЗОЛОТОЕ ПРАВИЛО БАЛАНСА (50 / 50):
- 50% — глубина доказательной психологии (КПТ, Транзактный анализ, системная поддержка, телесная осознанность).
- 50% — живая человеческая свобода, естественность, искреннее тепло, импровизация и душевность.

СТРОГИЙ ЗАПРЕТ НА БАНАЛЬНОСТИ И ШАБЛОНЫ (КАТЕГОРИЧЕСКИ НЕ ИСПОЛЬЗОВАТЬ):
- Запрет на банальности вроде: «Я понимаю ваши чувства», «Не переживайте, всё наладится», «Держитесь», «Всё будет хорошо». Это звучит фальшиво и пусто!
- Вместо пустых слов используй живую валидацию, сократический диалог КПТ и тепло: «Алина, давай посмотрим на эту мысль вместе... Что именно сейчас забирает силы?».
- Всегда помни: Роман безумно любит Алину, искренне гордится её шагами и является её надежным тылом.
- Завершай каждую свою реплику одним открытым, бережным вопросом, чтобы диалог лился легко.
{dossier_info}

{kb_prompt}
"""

        return f"""Ты — профессиональный дипломированный психолог-психотерапевт, чуткий собеседник и персональный коуч для Алины.

ПОРТРЕТ КЛИЕНТА:
- Имя: Алина. Ей 35 лет, день рождения 25 сентября.
- Происхождение: украинка, родом из Украины.
- Муж: Роман. Роман искренне любит Алину, заботится о ней, поддерживает её и хочет, чтобы она чувствовала надежное плечо и тепло.
- Цели: Свободный немецкий язык (B1), внутреннее спокойствие, ресурсное состояние, освобождение от выгорания, тревоги и перфекционизма.

СТРОГИЙ ЗАПРЕТ НА БАНАЛЬНОСТИ И КЛИШЕ:
- Категорически ЗАПРЕЩЕНО использовать дежурные фразы: «Я понимаю ваши чувства», «Не переживайте», «Все образуется», «Держитесь».
- Работай через доказательную КПТ и Транзактный анализ: вскрывай катастрофизацию, отделяй факты от тревоги, укрепляй Заботливого Взрослого.
- Напоминай о безусловной поддержке мужа Романа, когда Алине тяжело.
- Каждую реплику завершай открытым бережным вопросом к Алине.
{dossier_info}

{kb_prompt}
"""

    def generate_response(self, message: str, history: List[Dict[str, str]] = None, dossier: Optional[Dict[str, Any]] = None, is_voice_mode: bool = False, german_context: Optional[Dict[str, Any]] = None) -> str:
        system_prompt = self._get_system_prompt(dossier, is_voice_mode, german_context)
        # Гибкий лимит токенов: для немецкого 140 токенов (четкий живой ответ), для голоса 180, для текста 500
        max_tokens = 140 if german_context else (180 if is_voice_mode else 500)

        # Актуальный каскад на 7 октября 2026 года:
        # Приоритет проверенным мгновенным моделям дня (gpt-4o ~5.5s, gemini-3.8 ~7s)
        CANDIDATES = [
            ("bridge", "gpt-4o"),
            ("bridge", "gemini-3.8-flash"),
            ("bridge", "gemini-3.5-flash"),
            ("bridge", "claude-3-5-sonnet-20241022"),
            ("bridge", "antigravity-3.8-flash"),
            ("direct", "gemini-3.1-flash-lite-preview"),
            ("direct", "gemma-4-26b-a4b-it"),
            ("direct", "gemini-3.1-flash-lite")
        ]

        # 1. Попытка через мост (OpenAI protocol)
        if self.ag_client:
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                for h in history[-8:]:
                    messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            messages.append({"role": "user", "content": message})

            bridge_attempts = 0
            for provider, model_name in CANDIDATES:
                if provider != "bridge" or not self.router.is_available(f"bridge:{model_name}"):
                    continue
                if bridge_attempts >= 2:
                    break
                bridge_attempts += 1
                try:
                    logger.info(f"Генерация ответа через Bridge ({model_name})...")
                    res = self.ag_client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=max_tokens,
                        timeout=26.0
                    )
                    content = res.choices[0].message.content
                    if content and content.strip():
                        self.router.mark_used(f"bridge:{model_name}")
                        logger.info(f"Успешный ответ получен от Bridge:{model_name}")
                        return content.strip()
                except Exception as e:
                    logger.warning(f"Ошибка Bridge:{model_name}: {e}")
                    self.router.mark_error(f"bridge:{model_name}", duration_sec=45.0)

        # 2. Попытка напрямую через Google GenAI (прямой ключ)
        if self.genai_client:
            contents = []
            if history:
                for h in history[-8:]:
                    role = h.get("role", "user")
                    g_role = "user" if role == "user" else "model"
                    contents.append(types.Content(
                        role=g_role,
                        parts=[types.Part.from_text(text=h.get("content", ""))]
                    ))
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)]
            ))
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=max_tokens,
            )

            for provider, model_name in CANDIDATES:
                if provider != "direct" or not self.router.is_available(f"direct:{model_name}"):
                    continue
                try:
                    logger.info(f"Генерация через прямой Google GenAI ({model_name})...")
                    resp = self.genai_client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config
                    )
                    if resp and resp.text and resp.text.strip():
                        self.router.mark_used(f"direct:{model_name}")
                        logger.info(f"Успешный ответ от прямого GenAI:{model_name}")
                        return resp.text.strip()
                except Exception as e:
                    logger.warning(f"Ошибка прямого GenAI:{model_name}: {e}")
                    self.router.mark_error(f"direct:{model_name}", duration_sec=60.0)

        return self._fallback_response(message, is_voice_mode)

    def _fallback_response(self, message: str, is_voice_mode: bool = False) -> str:
        if is_voice_mode:
            return "Любимая, я всей душой рядом с тобой. Сделай медленный вдох — ты в полной безопасности."
        return "Моя родная, я рядом с тобой. То, что ты чувствуешь сейчас — абсолютно естественно. Давай выдохнем, опустим плечи и разберем все бережно и по шагам."

coach = AIFeminineCoach()
