# 🔄 Git Workflow для cudaCrimea

## 📋 Структура работы

```
Локально (Windows/Mac)
  ↓ git push
GitHub/GitLab (Remote)
  ↓ git pull
Сервер (Production)
```

## 🚀 Первоначальная настройка

### 1. Создание Git репозитория (Локально)

Уже сделано! Репозиторий инициализирован.

### 2. Создание remote репозитория

Выберите один из вариантов:

#### Вариант A: GitHub (Рекомендуется)

1. Создайте репозиторий на https://github.com/new
   - Название: `cudaCrimea` (или любое другое)
   - Private (рекомендуется для production проектов)
   - НЕ создавайте README, .gitignore (уже есть)

2. Добавьте remote:
```bash
git remote add origin https://github.com/ваш-username/cudaCrimea.git
```

#### Вариант B: GitLab

```bash
git remote add origin https://gitlab.com/ваш-username/cudaCrimea.git
```

#### Вариант C: Свой Git сервер

```bash
git remote add origin ssh://user@your-server.com/path/to/repo.git
```

### 3. Первый коммит

```bash
# Проверяем что будет добавлено
git status

# Добавляем все файлы
git add .

# Создаём первый коммит
git commit -m "Initial commit: Project ready for production deployment"

# Отправляем на remote
git push -u origin master
# или
git push -u origin main
```

### 4. Настройка на сервере

```bash
# На сервере
cd /opt
git clone https://github.com/ваш-username/cudaCrimea.git
cd cudaCrimea

# Настройка окружения
cp .env.example .env
nano .env  # Настройте production значения

# Первый запуск
cd infra
docker compose build
docker compose up -d
docker compose exec api alembic upgrade head
```

## 🔧 Ежедневная работа

### Workflow для разработки новых функций

#### 1. Локально - Разработка

```bash
# Создайте ветку для новой функции (опционально)
git checkout -b feature/new-feature

# Вносите изменения в код
# Я (Claude) помогаю вам писать код

# Тестируйте локально
cd infra
docker compose up -d
# Проверяете что всё работает
```

#### 2. Коммит изменений

```bash
# Проверяем изменения
git status
git diff

# Добавляем изменённые файлы
git add app/api/new_file.py
git add app/admin/templates/new_page.html
# или добавить всё:
git add .

# Коммитим с понятным сообщением
git commit -m "feat: Add CSV export functionality for events"

# Отправляем на remote
git push origin feature/new-feature
# или если работаете на master:
git push origin master
```

#### 3. Deployment на сервер

```bash
# На сервере
ssh user@your-server.com
cd /opt/cudaCrimea

# Получаем последние изменения
git pull origin master

# Автоматический deployment
make deploy

# Или вручную:
cd infra
docker compose down
docker compose build
docker compose up -d
docker compose exec api alembic upgrade head

# Проверяем
docker compose ps
docker compose logs -f --tail 50
```

### Workflow для срочных исправлений (hotfix)

#### Если нужно быстро исправить баг на сервере:

```bash
# 1. На сервере - делаем исправление
ssh user@server
cd /opt/cudaCrimea
nano app/api/main.py  # Исправляем проблему
docker compose restart api

# 2. Сохраняем изменения в git (ВАЖНО!)
git add app/api/main.py
git commit -m "hotfix: Fix critical bug in API endpoint"
git push origin master

# 3. Синхронизируем локально
# На локальном компьютере:
git pull origin master
```

## 📝 Git commit сообщения

Используйте понятные сообщения:

```bash
# ✅ Хорошие примеры:
git commit -m "feat: Add Telegram photo upload functionality"
git commit -m "fix: Fix timezone error in parser"
git commit -m "docs: Update deployment instructions"
git commit -m "refactor: Improve database query performance"

# ❌ Плохие примеры:
git commit -m "update"
git commit -m "fix bug"
git commit -m "changes"
```

### Префиксы для коммитов:

- `feat:` - Новая функциональность
- `fix:` - Исправление бага
- `docs:` - Изменения в документации
- `style:` - Форматирование кода
- `refactor:` - Рефакторинг
- `test:` - Добавление тестов
- `chore:` - Обновление зависимостей, конфигов

## 🌿 Работа с ветками (опционально, для больших проектов)

```bash
# Создание новой ветки
git checkout -b feature/export-to-csv

# Работа в ветке
# ... делаете изменения ...
git add .
git commit -m "feat: Add CSV export"
git push origin feature/export-to-csv

# Переключение на master
git checkout master

# Слияние ветки
git merge feature/export-to-csv

# Отправка на remote
git push origin master

# Удаление ветки (после слияния)
git branch -d feature/export-to-csv
git push origin --delete feature/export-to-csv
```

## 🔄 Типичные сценарии

### Сценарий 1: Добавление новой функции через Claude

```bash
# 1. Вы: "Нужно добавить экспорт событий в CSV"

# 2. Claude: Пишет код
# Создаёт файл app/api/export.py
# Обновляет app/api/main.py
# Показывает вам diff

# 3. Вы применяете изменения:
# Копируете код в файлы
# Или Claude может использовать инструменты для редактирования

# 4. Тестируете локально:
docker compose restart api
curl http://localhost:8000/api/events/export/csv

# 5. Коммитите:
git add app/api/export.py app/api/main.py
git commit -m "feat: Add CSV export endpoint"
git push origin master

# 6. На сервере:
ssh user@server
cd /opt/cudaCrimea
git pull origin master
make deploy
```

### Сценарий 2: Исправление бага

```bash
# 1. Вы: "Парсер падает с ошибкой KeyError"
docker compose logs worker --tail 100
# Показываете логи Claude

# 2. Claude: Анализирует и находит проблему
# Показывает что нужно изменить в app/ingestors/telegram_channels.py

# 3. Вы исправляете:
nano app/ingestors/telegram_channels.py
# Вносите изменение

# 4. Тестируете:
docker compose restart worker
docker compose logs worker -f

# 5. Коммитите:
git add app/ingestors/telegram_channels.py
git commit -m "fix: Handle missing 'title' key in Telegram messages"
git push origin master

# 6. Deploy на сервер (если нужно)
```

### Сценарий 3: Обновление конфигурации

```bash
# 1. Изменение docker-compose.yml или nginx.conf

# 2. Тест локально:
docker compose down
docker compose up -d

# 3. Коммит:
git add infra/docker-compose.yml
git commit -m "chore: Update docker-compose health checks"
git push

# 4. На сервере:
git pull
make deploy
```

## 🆘 Частые проблемы

### Конфликт при git pull

```bash
# Если есть изменения на сервере и локально
git pull origin master
# Конфликт!

# Решение:
git stash  # Сохраняем локальные изменения
git pull origin master
git stash pop  # Восстанавливаем изменения

# Или принудительно взять с remote:
git fetch origin
git reset --hard origin/master
```

### Забыли сделать commit перед deploy

```bash
# На сервере появились изменения, но не закоммичены
git status  # Показывает изменённые файлы

# Решение:
git add .
git commit -m "hotfix: Emergency fix"
git push origin master

# Синхронизируем локально:
git pull origin master
```

### Нужно откатить изменения

```bash
# Откат последнего коммита (сохраняя изменения):
git reset --soft HEAD~1

# Откат с удалением изменений (ОПАСНО!):
git reset --hard HEAD~1

# Откат конкретного файла:
git checkout HEAD -- app/api/main.py
```

## 📊 Полезные команды

```bash
# Просмотр истории
git log --oneline --graph --all

# Просмотр изменений
git diff
git diff app/api/main.py

# Статус
git status

# Кто и когда изменял файл
git blame app/api/main.py

# Поиск в истории
git log --grep="parser"

# Удаление не отслеживаемых файлов
git clean -fd

# Просмотр remote
git remote -v

# Обновление .gitignore (если добавили новые правила)
git rm -r --cached .
git add .
git commit -m "chore: Update .gitignore"
```

## ✅ Чеклист первоначальной настройки

- [ ] Git репозиторий инициализирован (`git status`)
- [ ] Создан `.gitignore` (есть)
- [ ] Создан `.gitattributes` (есть)
- [ ] Создан remote репозиторий (GitHub/GitLab)
- [ ] Добавлен remote: `git remote add origin <url>`
- [ ] Сделан первый коммит: `git add . && git commit -m "Initial commit"`
- [ ] Отправлено на remote: `git push -u origin master`
- [ ] На сервере склонирован репозиторий
- [ ] На сервере настроен `.env`
- [ ] На сервере запущен проект
- [ ] Протестирован workflow: изменение → commit → push → pull на сервере → deploy

## 🎯 Следующие шаги

1. **Сейчас:** Создайте remote репозиторий (GitHub/GitLab)
2. **Сейчас:** Сделайте первый commit и push
3. **Перед deploy:** Убедитесь что все секреты в `.gitignore`
4. **На сервере:** Clone репозитория и первый запуск
5. **Тестирование:** Попробуйте сделать тестовое изменение и задеплоить

---

**Нужна помощь?**
- Проблемы с Git: Покажите вывод `git status` и `git log`
- Проблемы с deployment: Покажите логи `docker compose logs`
- Вопросы по workflow: Опишите что пытаетесь сделать
