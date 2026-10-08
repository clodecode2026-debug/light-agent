"""
Модуль: Расширенная психологическая библиотека с книгами Ялома, Готтмана, Перель, Франкла, Джонсон и Берна.
"""

from books.psychology_books import get_psychology_books

def get_library_items():
    books = get_psychology_books()
    items = []
    for b in books:
        items.append({
            "id": b["id"],
            "title": b["title"],
            "author": b["author"],
            "category": b["category"],
            "year": b.get("year", 2000),
            "rating": b.get("rating", 4.8),
            "excerpt": b["excerpt"],
            "description": b["description"],
            "key_ideas": b["key_ideas"]
        })
    return items
