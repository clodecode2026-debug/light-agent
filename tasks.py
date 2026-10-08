from typing import List, Dict, Any
import datetime

class TaskTracker:
    def __init__(self):
        # Дефолтные заботливые задачи для гармонии и отдыха
        self.tasks = [
            {"id": 1, "title": "Выпить стакан теплой воды с лимоном", "category": "Здоровье", "completed": False},
            {"id": 2, "title": "Сделать 5 глубоких вдохов и выдохов у окна", "category": "Релакс", "completed": False},
            {"id": 3, "title": "Почитать любимую книгу 15 минут", "category": "Развитие", "completed": False},
            {"id": 4, "title": "Пять минут попрактиковать немецкий язык", "category": "Немецкий", "completed": False},
            {"id": 5, "title": "Сказать себе одно доброе комплимент", "category": "Любовь к себе", "completed": False}
        ]
        self.counter = 6

    def get_tasks(self) -> List[Dict[str, Any]]:
        """Возвращает список всех задач"""
        return self.tasks

    def add_task(self, title: str, category: str = "Забота") -> Dict[str, Any]:
        """Добавляет новую задачу"""
        task = {
            "id": self.counter,
            "title": title,
            "category": category,
            "completed": False
        }
        self.counter += 1
        self.tasks.append(task)
        return task

    def toggle_task(self, task_id: int) -> Dict[str, Any]:
        """Переключает статус задачи (выполнено / не выполнено)"""
        for task in self.tasks:
            if task["id"] == task_id:
                task["completed"] = not task["completed"]
                return {"success": True, "task": task}
        return {"success": False, "error": "Задача не найдена"}

    def delete_task(self, task_id: int) -> Dict[str, Any]:
        """Удаляет задачу"""
        for i, task in enumerate(self.tasks):
            if task["id"] == task_id:
                removed = self.tasks.pop(i)
                return {"success": True, "removed": removed}
        return {"success": False, "error": "Задача не найдена"}
