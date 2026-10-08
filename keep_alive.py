import time
import httpx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PING_URL = "https://ai-wife-coach.onrender.com/health"
INTERVAL_SECONDS = 300  # Каждые 5 минут (300 секунд)

def ping_server():
    logging.info(f"Сейф-пинг отправляется на {PING_URL}...")
    try:
        response = httpx.get(PING_URL, timeout=15.0)
        if response.status_code == 200:
            logging.info(f"Сервер успешно откликнулся! Код: {response.status_code}, Ответ: {response.json()}")
        else:
            logging.warning(f"Сервер ответил с кодом: {response.status_code}")
    except Exception as e:
        logging.error(f"Не удалось достучаться до сервера: {e}")

if __name__ == "__main__":
    logging.info("Anti-sleep скрипт для ai-wife-coach запущен.")
    while True:
        ping_server()
        time.sleep(INTERVAL_SECONDS)
