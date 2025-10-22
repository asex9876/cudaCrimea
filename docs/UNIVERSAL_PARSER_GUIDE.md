# 🌐 Универсальный AI-Парсер - Руководство

## Что это?

**Универсальный парсер** - система, которая позволяет добавить ЛЮБОЙ сайт, и AI автоматически начнёт парсить с него события.

**Без кода. Без селекторов. Без настройки.**

## Как работает?

1. **Вы добавляете URL** любого сайта с событиями
2. **AI анализирует HTML** и находит все события на странице
3. **Система автоматически парсит** каждые 30 минут (настраивается)
4. **События добавляются** в базу со всеми полями

## 🎯 Возможности

### Автоматическое извлечение

AI извлекает **17 полей** из любого HTML:
- Название
- Дата и время (начало + конец)
- Место и адрес
- Цены (мин/макс)
- Категория
- Возрастные ограничения
- Организатор
- Длительность
- Тип билета
- И многое другое

### Умная обработка

- **Автогеокодинг** адресов
- **Автоисправление** данных (даты, цены)
- **Дедупликация** через embeddings
- **Валидация** всех полей

### Мониторинг

- Периодическая проверка (по умолчанию: 30 мин)
- Статистика по источникам
- Логи ошибок
- Включение/отключение источников

## 📝 Как использовать

### Добавление источника (через код)

```python
from app.db.models import UniversalSource
from sqlalchemy.ext.asyncio import AsyncSession

async def add_source(session: AsyncSession):
    source = UniversalSource(
        url="https://example.com/events",
        name="Пример событий",
        description="Сайт с концертами",
        city="Севастополь",
        parse_interval_minutes=30,
        is_active=True,
    )
    session.add(source)
    await session.commit()
```

### Добавление через SQL

```sql
INSERT INTO universal_sources (
    id, url, name, city, is_active, parse_interval_minutes
) VALUES (
    gen_random_uuid(),
    'https://example.com/events',
    'Пример событий',
    'Севастополь',
    true,
    30
);
```

### Ручной запуск парсинга

```python
from app.ingestors.universal_parser import process_source, process_all_active_sources
from app.db.session import get_sessionmaker

async def run_parser():
    async_session = get_sessionmaker()
    async with async_session() as session:
        # Парсить все активные источники
        result = await process_all_active_sources(session)
        print(f"Обработано: {result['total_sources']} источников")
        print(f"Добавлено: {result['total_events']} событий")
```

## 🔧 Интеграция с APScheduler

Добавьте в `app/ingestors/worker.py`:

```python
from app.ingestors.universal_parser import process_all_active_sources

# Добавить задачу
scheduler.add_job(
    lambda: asyncio.run(run_universal_parser()),
    'interval',
    minutes=30,
    id='universal_parser',
    replace_existing=True,
)

async def run_universal_parser():
    """Run universal parser for all active sources."""
    async_session_maker = get_sessionmaker()
    async with async_session_maker() as session:
        result = await process_all_active_sources(session)
        logger.info("universal_parser.scheduled_run", result=result)
```

## 🎨 UI в Админ-панели (планируется)

### Раздел "Источники парсинга"

- **Список источников** с статусом
- **Добавить источник** - форма с URL и настройками
- **Редактировать** - изменить интервал, город и т.д.
- **Включить/Выключить** - кнопка toggle
- **Удалить** - с подтверждением
- **Запустить сейчас** - ручной запуск парсинга

### Статистика

- Всего источников
- Активных источников
- Всего событий спарсено
- Последний запуск
- Ошибки

## 🚀 Примеры использования

### Пример 1: Парсинг афиши театра

```python
source = UniversalSource(
    url="https://lukomorie.crimea.com/afisha/",
    name="Лукоморье - Афиша",
    description="Детский театр Лукоморье",
    city="Севастополь",
    parse_interval_minutes=60,  # Раз в час
)
```

**Результат**: AI найдёт все спектакли и добавит их автоматически.

### Пример 2: Парсинг концертного зала

```python
source = UniversalSource(
    url="https://концертный-зал.рф/расписание",
    name="Концертный зал",
    city="Симферополь",
    parse_interval_minutes=30,
)
```

**Результат**: Все концерты с датами, временем и ценами.

### Пример 3: Парсинг музея

```python
source = UniversalSource(
    url="https://панорама.рф/выставки",
    name="Панорама - Выставки",
    description="Музей-панорама обороны Севастополя",
    city="Севастополь",
    parse_interval_minutes=1440,  # Раз в день
)
```

## 📊 Поддерживаемые типы сайтов

AI умеет парсить:
- **Афиши** (театры, кино, концерты)
- **Расписания** (музеи, выставки)
- **Календари событий**
- **Новостные сайты** с анонсами
- **Социальные сети** (публичные страницы)
- **Любые HTML-страницы** с информацией о событиях

## ⚙️ Конфигурация

### Настройки источника

| Поле | Описание | По умолчанию |
|------|----------|--------------|
| `url` | URL страницы | обязательно |
| `name` | Название источника | обязательно |
| `description` | Описание | опционально |
| `city` | Город для событий | опционально |
| `is_active` | Включен/выключен | `true` |
| `parse_interval_minutes` | Интервал парсинга | `30` |
| `parsing_strategy` | AI-стратегия | auto |

### Модель данных

```python
class UniversalSource:
    id: UUID                      # Уникальный ID
    url: str                      # URL источника
    name: str                     # Название
    description: str | None       # Описание
    is_active: bool               # Активен?
    parse_interval_minutes: int   # Интервал
    city: str | None              # Город
    parsing_strategy: dict | None # AI-стратегия
    total_parsed: int             # Всего событий
    last_parsed_at: datetime      # Последний парсинг
    last_error: str | None        # Последняя ошибка
    created_by: str | None        # Кто добавил
    created_at: datetime          # Дата создания
    updated_at: datetime          # Дата обновления
```

## 🔍 Как AI находит события?

### 1. Загрузка HTML

```python
html = await fetch_html(url)
```

### 2. Очистка

Удаляются:
- JavaScript
- CSS
- Комментарии
- SVG, iframe
- Лишние теги

### 3. AI-анализ

```
Промпт → "Найди все события на этой странице"
AI → Анализирует структуру
AI → Извлекает данные
AI → Возвращает JSON
```

### 4. Валидация

- Проверка полей
- Автоисправление
- Геокодинг

### 5. Сохранение

- Создание события
- Генерация embedding
- Проверка дубликатов

## 🐛 Troubleshooting

### Источник не парсится

**Проверьте:**
1. URL доступен (не требует авторизации)
2. Страница содержит события
3. `is_active = true`
4. Прошло достаточно времени с последнего парсинга

**Логи:**
```bash
docker logs cuda_worker | grep universal_parser
```

### События не добавляются

**Возможные причины:**
1. AI не нашёл события на странице
2. Ошибки валидации (проверьте даты, цены)
3. Дубликаты (события уже есть в БД)

**Проверка:**
```sql
SELECT last_error FROM universal_sources WHERE url = 'ваш_url';
```

### Слишком частый парсинг

**Решение:**
```sql
UPDATE universal_sources
SET parse_interval_minutes = 60
WHERE id = 'uuid';
```

## 📈 Мониторинг

### SQL запросы для мониторинга

```sql
-- Активные источники
SELECT name, url, last_parsed_at, total_parsed
FROM universal_sources
WHERE is_active = true
ORDER BY last_parsed_at DESC;

-- Источники с ошибками
SELECT name, url, last_error, last_parsed_at
FROM universal_sources
WHERE last_error IS NOT NULL;

-- Статистика
SELECT
    COUNT(*) as total_sources,
    SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active,
    SUM(total_parsed) as total_events
FROM universal_sources;
```

## 🎓 Best Practices

### 1. Правильный выбор URL

✅ **Хорошо:**
- `https://site.com/events` - страница со списком
- `https://site.com/afisha` - афиша
- `https://site.com/raspisanie` - расписание

❌ **Плохо:**
- `https://site.com` - главная страница
- `https://site.com/about` - страница "о нас"
- Страницы с авторизацией

### 2. Настройка интервала

- **Театры/музеи**: 1-6 часов (события редко меняются)
- **Концертные залы**: 30-60 минут
- **Новостные сайты**: 15-30 минут

### 3. Указание города

Всегда указывайте город для:
- Точной геолокации
- Правильной фильтрации
- Лучшего UX

## 🚀 Roadmap

- [ ] UI в админ-панели
- [ ] AI-learning (запоминание структуры сайта)
- [ ] Уведомления о новых событиях
- [ ] Webhook интеграция
- [ ] API для добавления источников
- [ ] Автоматическое определение города
- [ ] Поддержка JavaScript-сайтов (Playwright)

---

**Разработано с помощью Claude Code** 🤖
