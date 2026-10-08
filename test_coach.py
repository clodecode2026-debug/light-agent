import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data

def test_german_endpoint():
    response = client.get("/api/german?level=A1")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

def test_library_endpoint():
    response = client.get("/api/library")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

def test_books_and_german_course_endpoints():
    res_books = client.get("/api/books")
    assert res_books.status_code == 200
    assert isinstance(res_books.json(), list)

    res_course = client.get("/api/german/course")
    assert res_course.status_code == 200
    assert isinstance(res_course.json(), dict)
    assert "lessons" in res_course.json()
