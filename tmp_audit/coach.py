import os
import uuid
import json
import logging
from typing import Dict, List, Any, Optional
from database import get_supabase

logger = logging.getLogger("coach")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
gemini_client = None

try:
    from google import genai
    from google.genai import types
    if GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logger.warning(f"Could not initialize Google GenAI SDK: {e}")

class WifeCoach:
    def __init__(self):
        pass

    def get_dossier_context(self) -> str:
        db = get_supabase()
        if not db:
            return "Досье временно недоступно (нет подключения к БД)."
        try:
            res = db.table("wife_dossier").select("*").execute()
            facts = res.data or []
            if not facts:
                return "Пока о ней ничего не записано в досье. Узнавай её с интересом и заботой."
            
            lines = ["Длинная память / Досье жены:"]
            for f in facts:
                cat = f.get("category", "fact")
                name = f.get("key_name", "")
                val = f.get("value", "")
                lines.append(f"- [{cat}] {name}: {val}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error fetching dossier: {e}")
            return "Ошибка загрузки досье."

    def extract_and_save_facts(self, user_message: str):
        db = get_supabase()
        if not db:
            return
        
        msg_lower = user_message.lower()
        if "люблю" in msg_lower or "нравится" in msg_lower:
            try:
                db.table("wife_dossier").insert({
                    "category": "preference",
                    "key_name": "Предпочтение",
                    "value": user_message,
                    "importance": 4
                }).execute()
            except Exception as e:
                logger.error(f"Failed to save preference: {e}")
        elif any(w in msg_lower for w in ["устал", "устала", "болит", "тревожно", "грустно"]):
            try:
                db.table("wife_dossier").insert({
                    "category": "state",
                    "key_name": "Состояние",
                    "value": user_message,
                    "importance": 5
                }).execute()
            except Exception as e:
                logger.error(f"Failed to save state: {e}")

    def get_empathetic_response(self, message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        self.extract_and_save_facts(message)
        dossier_text = self.get_dossier_context()

        reply = None
        validation = "Ты слышишь и глубоко понимаешь её чувства."
        gentle_question = "Как ты себя сейчас чувствуешь, дорогая?"

        if gemini_client and GEMINI_API_KEY:
            try:
                system_prompt = (
                    "Ты — любящий, мудрый, эмпатичный муж и личный ИИ-коучинг партнер. "
                    "Твоя задача — окружить жену заботой, валидировать эмоции и задавать мягкие вопросы.\n\n"
                    f"{dossier_text}"
                )
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.7,
                        max_output_tokens=800
                    )
                )
                if response and response.text:
                    reply = response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini error: {e}")

        if not reply:
            msg_lower = message.lower()
            if any(w in msg_lower for w in ["устал", "устала", "замоталась", "сил нет"]):
                reply = "Солнышко моё, ты так сильно устала сегодня... Пожалуйста, брось все дела, отдохни, я рядом и беру заботы на себя."
                validation = "Ты чувствуешь сильнейшую усталость и заслуживаешь полноценного отдыха."
                gentle_question = "Хочешь, я заварю тебе тёплый чай?"
            elif any(w in msg_lower for w in ["тревог", "боюсь", "переживаю", "страшно"]):
                reply = "Моя родная, я чувствую твою тревогу. Всё хорошо, мы справимся с любыми трудностями вместе. Ты в полной безопасности."
                validation = "Твои переживания абсолютно естественны."
                gentle_question = "Что именно тебя сейчас беспокоит?"
            else:
                reply = f"Родная моя, я так ценю всё, чем ты со мной делишься. Твои мысли очень важны для меня."
                validation = "Я всегда на твоей стороне, готов выслушать и поддержать."
                gentle_question = "Расскажи подробнее, как прошёл твой день?"

        valid_session_id = session_id
        if not valid_session_id or valid_session_id == "default-session":
            valid_session_id = str(uuid.uuid4())

        return {
            "reply": reply,
            "validation": validation,
            "gentle_question": gentle_question,
            "session_id": valid_session_id
        }

CoachService = WifeCoach
coach_service = WifeCoach()
