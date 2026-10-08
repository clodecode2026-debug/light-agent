import unittest
from fastapi.testclient import TestClient
from main import app
from coach import CoachService
from german import GermanTrainer
from library import LibraryService
from tasks import TaskTracker

class TestAiWifeCoach(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "project": "ai-wife-coach"})

    def test_coach_service(self):
        service = CoachService()
        res = service.get_empathetic_response("Я так устала за сегодня...")
        self.assertIn("reply", res)
        self.assertIn("validation", res)
        self.assertTrue("устал" in res["reply"].lower() or "усталость" in res["reply"].lower())

    def test_coach_api(self):
        response = self.client.post("/api/chat", json={"message": "Мне немного тревожно"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("reply", data)
        self.assertIn("gentle_question", data)

    def test_german_trainer(self):
        trainer = GermanTrainer()
        card = trainer.get_card("A1")
        self.assertIn("de", card)
        self.assertIn("ru", card)
        
        check = trainer.check_translation("A1", card["de"], card["ru"])
        self.assertTrue(check["correct"])

    def test_german_api(self):
        response = self.client.get("/api/german/card?level=A1")
        self.assertEqual(response.status_code, 200)
        card = response.json()
        self.assertIn("de", card)

        check_resp = self.client.post("/api/german/check", json={
            "level": "A1",
            "german_text": card["de"],
            "user_translation": card["ru"]
        })
        self.assertEqual(check_resp.status_code, 200)
        self.assertTrue(check_resp.json()["correct"])

    def test_library_service(self):
        lib = LibraryService()
        books = lib.list_books()
        self.assertGreater(len(books), 0)

        quotes = lib.search_quotes("границы")
        self.assertGreater(len(quotes), 0)

    def test_library_api(self):
        response = self.client.get("/api/books")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_task_tracker(self):
        tracker = TaskTracker()
        initial_count = len(tracker.get_tasks())
        
        new_task = tracker.add_task("Медитация 5 минут", "Релакс")
        self.assertEqual(new_task["title"], "Медитация 5 минут")
        self.assertEqual(len(tracker.get_tasks()), initial_count + 1)

        toggled = tracker.toggle_task(new_task["id"])
        self.assertTrue(toggled["success"])
        self.assertTrue(toggled["task"]["completed"])

        deleted = tracker.delete_task(new_task["id"])
        self.assertTrue(deleted["success"])

    def test_tasks_api(self):
        response = self.client.get("/api/tasks")
        self.assertEqual(response.status_code, 200)
        tasks = response.json()
        self.assertIsInstance(tasks, list)

        add_resp = self.client.post("/api/tasks", json={"title": "Выпить воды", "category": "Здоровье"})
        self.assertEqual(add_resp.status_code, 200)
        created = add_resp.json()
        
        toggle_resp = self.client.post(f"/api/tasks/{created['id']}/toggle")
        self.assertEqual(toggle_resp.status_code, 200)

        del_resp = self.client.delete(f"/api/tasks/{created['id']}")
        self.assertEqual(del_resp.status_code, 200)

if __name__ == "__main__":
    unittest.main()
