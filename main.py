"""Точка входа: python app/main.py или gunicorn app.main:app"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        timeout_keep_alive=75,  # Render проксирует, нужен запас
    )