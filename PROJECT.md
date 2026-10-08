# Паспорт проекта: ai-wife-coach

**Цель:** Реализация 2 режимов (текстовый + Google Live Voice модальное окно), облачного хранилища S3 Storj и коротких ответов ИИ в голосовом режиме

**Статус:** Код проверен через validate_code, пройдены юнит-тесты pytest, готовим деплой и синхронизацию с GitHub
**Обновлено:** 2026-10-06 22:13:14 UTC

## Стек технологий
`FastAPI`, `Gemini/LLM`, `Supabase`, `Storj S3`, `Tailwind CSS`, `Python`, `pytest`, `edge-tts`, `Render`, `Uvicorn`, `Google GenAI`, `Edge-TTS`, `Pytest`, `Google GenAI SDK`, `Storj S3 (boto3)`

## Ключевые файлы и модули
- **`main.py`**: эндпоинты чата, TTS, S3 voice save, немецкого, библиотеки
- **`models.py`**: схемы и базы данных
- **`static/`**: веб-интерфейс
- **`coach.py`**: добавлен параметр max_output_tokens=120 для is_voice_mode
- **`german.py`**: 30 фраз A1-B1
- **`library.py`**: 10 цитат классиков
- **`tasks.py`**: задачи
- **`test_coach.py`**: юнит-тесты.
- **`index.html`**: Файл .html
- **`style.css`**: Файл .css
- **`app.js`**: Файл .js
- **`requirements.txt`**: Полный набор зависимостей
- **`render.yaml`**: обновлен startCommand
- **`keep_alive.py`**: Файл .py
- **`voice.py`**: эндпоинт /api/voice/tts через edge-tts
- **`static/app.js`**: функция toggleLiveVoiceMode() и непрерывный голосовой диалог
- **`tts_helper.js`**: Файл .js
- **`static/tts_helper.js`**: клиентский плеер аудио стриминга
- **`database.py`**: Supabase интеграция
- **`static/index.html & app.js`**: UI с кнопкой живого голоса
- **`static/index.html`**: добавлено модальное окно google-live-modal
- **`storage.py`**: модуль boto3 для S3 Storj
- **`static/index.html и static/app.js`**: интерфейс чата и модальное окно Google Live
- **`psychology_books.py`**: Файл .py
- **`german_course.py`**: Файл .py
- **`extra_routes.py`**: Файл .py

## Принятые решения
- AI коуч-психолог с мягкой поддержкой
- интеграция LLM
- модуль изучения немецкого
- библиотека книг
- трекер задач
- уютный адаптивный веб-интерфейс
- Эмпатичный ИИ-коуч с мягкой валидацией
- модуль немецкого A1-B2
- трекер заботы
- FastAPI
- Tailwind CSS
- Интеграция edge-tts для озвучивания ответов коуча (ru-RU-SvetlanaNeural)
- добавлены эндпоинты /api/voice/tts и фронтенд-кнопки озвучки в реальном времени.
- Добавлен модуль голосового синтеза edge-tts (/api/voice/tts) с русской озвучкой SvetlanaNeural
- интерфейс чата обогащен кнопками озвучивания и голосовым вводом.
- Добавлен FastAPI эндпоинт /api/voice/tts через edge-tts с голосом ru-RU-SvetlanaNeural
- фронтенд воспроизводит аудиоответы через этот эндпоинт с бэкапом в Web Speech API
- зависимости edge-tts>=6.1.12 прописаны в requirements.txt
- интегрирован эндпоинт POST /api/voice/tts с edge-tts (ru-RU-SvetlanaNeural)
- фронтенд оздоравливает ответы коуча через потоковое воспроизведение audio/mpeg
- проведены тесты и валидация кода
- интеграция edge-tts через /api/voice/tts с голосом ru-RU-SvetlanaNeural
- обновление frontend app.js для воспроизведения аудио стриминга
- эндпоинт POST /api/voice/tts с потоковым audio/mpeg
- фронтенд app.js интегрирован с /api/voice/tts
- edge-tts интегрирован в FastAPI через /api/voice/tts с голосом ru-RU-SvetlanaNeural
- фронтенд app.js вызывает этот эндпоинт для натуральной озвучки ответов коуча
- Добавлен эндпоинт POST /api/voice/tts с поддержкой edge-tts (голос ru-RU-SvetlanaNeural)
- фронтенд озвращает ответы коуча через Edge TTS в фоновом режиме
- зависимости обновлены в requirements.txt
- Добавлен блок if __name__ == '__main__' в main.py для корректного запуска uvicorn
- старткоманда в render.yaml заменена на python main.py
- Интегрирован Gemini 2.5 через google-genai
- Подключен Supabase для истории и досье жены
- Добавлена кнопка и режим Живого голосового диалога в веб-интерфейсе
- Расширена база немецких фраз (30 шт) и цитат психологов (10 шт)
- Настроен uvicorn и health-check.
- Каскад моделей Gemini: gemini-3.1-flash-lite, gemini-3.5-flash-lite, gemini-3.8-flash
- Добавлены все роуты для немецкого и библиотеки в main.py
- Добавлена отдельная большая кнопка Живого разговора в шапку чата с пульсацией
- непрерывный цикл распознавания речи и озвучки через серверный TTS
- Режим 1: текстовый чат с развернутыми терапевтическими ответами
- Режим 2: модальное окно Google Live Voice с пульсирующей сферой, переключением голоса (Светлана / Katja) и короткими ответами (1-3 предложения при is_voice_mode=True)
- Модуль storage.py для сохранения аудиозаписей в S3 Storj
- Эндпоинт POST /api/voice/save
- Добавлено модальное окно Google Live Voice в static/index.html
- в coach.py для голосового режима max_output_tokens=120 ограничено до 2 предложений
