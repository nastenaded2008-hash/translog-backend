# ТРАНСЛОГ — backend

Backend MVP по двум документам проекта: Vision и Software Architecture Document.

## Стек
- Python + FastAPI
- PostgreSQL (Supabase)
- SQLAlchemy 2.x async + asyncpg
- JWT access tokens
- REST API

## Запуск локально
1. Установить Python 3.11+.
2. Создать виртуальное окружение:
   `python -m venv .venv`
3. Активировать его:
   Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
   macOS/Linux: `source .venv/bin/activate`
4. Установить зависимости:
   `pip install -r requirements.txt`
5. Скопировать `.env.example` в `.env` и заполнить `DATABASE_URL` и `SECRET_KEY`.
6. Установить переменные окружения из `.env` (или использовать расширение Python dotenv, если добавите его в requirements).
7. Запустить:
   `uvicorn app.main:app --reload`
8. Документация: `http://127.0.0.1:8000/docs`

## Render
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Root Directory: оставить пустым, если requirements.txt лежит в корне репозитория.
- Environment:
  - `DATABASE_URL` = Supabase Session Pooler URL с паролем
  - `SECRET_KEY` = длинная случайная строка

## Роли
- `shipper` — создаёт заявки и видит только свои.
- `driver` — видит назначенные ему заявки и обновляет статус/GPS.
- `dispatcher` — управляет заявками, назначениями и транспортом.
- `manager` — просмотр пользователей и сводного отчёта.
- `admin` — административные операции.

Публичная регистрация создаёт только роль `shipper`. Для MVP роли сотрудников назначаются администратором напрямую в БД Supabase. Не выдавайте роль admin через публичную регистрацию.

## Основные endpoint-ы
- `GET /health` — проверяет API и соединение с БД.
- `POST /auth/register` — регистрация отправителя.
- `POST /auth/login` — получение JWT.
- `GET /users/me` — текущий пользователь.
- `GET/POST /vehicles`, `PATCH /vehicles/{id}` — транспорт.
- `GET/POST /shipments`, `GET/PATCH /shipments/{id}` — заявки.
- `POST /shipments/{id}/assign` — назначить автомобиль и водителя.
- `PUT /shipments/{id}/route` — сохранить маршрут вручную.
- `PATCH /shipments/{id}/status` — изменить статус.
- `POST /shipments/{id}/gps` — записать GPS-координаты.
- `GET /shipments/{id}/gps/latest` — последние координаты.
- `GET /shipments/{id}/history` — история статусов.
- `GET /notifications` — уведомления внутри приложения.
- `GET /reports/summary` — сводный отчёт.

## Что пока не подключено
Документы требуют картографический сервис, GPS и внешний сервис уведомлений, но не называют поставщиков/API-ключи. Поэтому:
- маршрут сохраняется вручную; автоматическое построение маршрута по адресам ещё не реализовано;
- GPS endpoint принимает координаты от мобильного клиента, но сам backend не получает GPS с телефона;
- уведомления сохраняются в таблицу `notifications`, но SMS/push/email не отправляются;
- нет готового веб-/мобильного интерфейса: этот репозиторий — только backend API.

## Важные замечания перед реальным использованием
- `Base.metadata.create_all()` создаёт таблицы при старте, но для дальнейших изменений схемы нужна система миграций (например, Alembic).
- Создайте первого сотрудника и назначьте ему роль `dispatcher` или `admin` вручную в Supabase Table Editor.
- Установите собственный `SECRET_KEY` в Render. Не храните секреты в GitHub и не отправляйте их в чат.
- Это учебный MVP: перед реальным использованием нужны полноценные проверки прав, аудит, миграции, резервное копирование и тестирование.
