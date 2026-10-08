import uuid
from typing import List, Dict, Any

class TaskTracker:
    def __init__(self):
        self.tasks = [
            {"id": "1", "title": "Сказать комплимент", "category": "Забота", "completed": False},
            {"id": "2", "title": "Подарить цветы", "category": "Романтика", "completed": True}
        ]

    def get_tasks(self) -> List[Dict]:
        return self.tasks

    def add_task(self, title: str, category: str = "Забота") -> Dict:
        new_task = {"id": str(uuid.uuid4()), "title": title, "category": category, "completed": False}
        self.tasks.append(new_task)
        return new_task

    def toggle_task(self, task_id: str) -> Dict[str, Any]:
        for t in self.tasks:
            if t["id"] == task_id:
                t["completed"] = not t["completed"]
                return {"success": True, "task": t}
        return {"success": False}

    def delete_task(self, task_id: str) -> Dict[str, Any]:
        for i, t in enumerate(self.tasks):
            if t["id"] == task_id:
                self.tasks.pop(i)
                return {"success": True}
        return {"success": False}
