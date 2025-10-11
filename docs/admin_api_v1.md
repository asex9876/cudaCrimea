# Admin API v1 Draft

## Overview
Новый SPA обращается к JSON API с префиксом `/admin/api/v1`. Авторизация — по текущей сессии (Cookie), позже можно перейти на JWT.

## Сводка эндпоинтов

### Dashboard
- `GET /admin/api/v1/dashboard/summary`
  - Возвращает агрегаты: количество новых UGC-заявок, количество опубликованных событий за период, CTR кнопок за 7 дней, счетчики ошибок интеграций.
  - Ответ:
    ```json
    {
      "new_requests": 12,
      "published_today": 8,
      "ctr_week": 0.124,
      "error_count": 1,
      "tasks": [
        { "id": "ugc:123", "title": "Проверить заявку", "status": "pending" }
      ]
    }
    ```

### UGC Queue
- `GET /admin/api/v1/ugc`
  - Параметры: `status` (pending|approved|rejected), `search`, `limit`, `offset`.
  - Ответ содержит массив карточек + пагинацию.
- `GET /admin/api/v1/ugc/{id}`
  - Полная информация о заявке, включая историю правок.
- `POST /admin/api/v1/ugc/{id}/approve`
  - Тело: `{ "publish": true, "notes": "optional" }`.
- `POST /admin/api/v1/ugc/{id}/reject`
  - Тело: `{ "reason": "спам" }`.
- `PATCH /admin/api/v1/ugc/{id}`
  - Позволяет отредактировать поля перед публикацией.

### Scheduler
- `GET /admin/api/v1/scheduler/posts`
  - Возвращает список запланированных публикаций (фильтр по состоянию).
- `POST /admin/api/v1/scheduler/posts`
  - Создает задачу. Тело: `{ "event_id": "uuid", "channel": "@mychannel", "run_at": "2025-09-20T09:00:00Z" }`.
- `PATCH /admin/api/v1/scheduler/posts/{id}`
  - Изменить время/канал.
- `DELETE /admin/api/v1/scheduler/posts/{id}`
  - Удалить задачу.
- `POST /admin/api/v1/scheduler/posts/{id}/run`
  - Запустить немедленно.

### Notifications
- `GET /admin/api/v1/settings/alerts`
  - Получить текущее состояние каналов (email, telegram).
- `PATCH /admin/api/v1/settings/alerts`
  - Обновить настройки. Тело: `{ "email": "admin@example.com", "telegram_chat_id": 123456789, "events": { "ugc": true, "errors": true } }`.

## Модели данных
- `ugc_requests`
  - `id` UUID, `status` enum, `payload` JSONB, `images` JSONB, `history` JSONB, `created_at`, `updated_at`, `assigned_to` (nullable FK на пользователя).
- `scheduled_posts`
  - `id` UUID, `event_id`, `channel`, `run_at`, `status` (scheduled/sent/error), `result` JSONB.
- `notification_settings`
  - `user_id`, `email`, `telegram_chat_id`, `preferences` JSONB.

## Следующие шаги
1. Реализовать схемы (Pydantic) для запросов/ответов.
2. Добавить маршруты в `app/admin/api.py` (новый модуль, чтобы не смешивать с Jinja).
3. Подключить React Query к этим эндпоинтам и отрисовать данные.
