import uuid

class LibraryService:
    def __init__(self):
        self.books = [
            {"id": 1, "title": "Пять языков любви", "author": "Гэри Чепмен", "category": "Отношения", "excerpt": "Любовь требует времени и усердия. Личные границы и доверие."},
            {"id": 2, "title": "Ненасильственное общение", "author": "Маршал Розенберг", "category": "Психология", "excerpt": "Общение из сочувствия, эмоций и потребностей. Границы личности."}
        ]

    def list_books(self):
        return self.books

    def search_quotes(self, query: str):
        q = query.lower()
        return [b for b in self.books if q in b["excerpt"].lower() or q in b["category"].lower() or q in b["title"].lower()]
