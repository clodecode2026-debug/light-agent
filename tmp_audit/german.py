import random
from typing import Dict, Any

class GermanTrainer:
    def __init__(self):
        self.cards = {
            "A1": {"de": "Ich liebe dich von ganzem Herzen.", "ru": "Я люблю тебя всем сердцем."},
            "A2": {"de": "Du bist mein Ruhepol und mein Glück.", "ru": "Ты моя тихая гавань и моё счастье."}
        }

    def get_card(self, level: str = "A1") -> Dict[str, str]:
        return self.cards.get(level, self.cards["A1"])

    def check_translation(self, level: str, de_text: str, user_translation: str) -> Dict[str, Any]:
        card = self.cards.get(level, {})
        correct = user_translation.strip().lower() in card.get("ru", "").lower()
        return {"correct": correct, "expected": card.get("ru", "")}
