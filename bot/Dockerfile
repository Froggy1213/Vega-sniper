# Используем официальный легковесный образ Python 3.13
FROM python:3.13-slim

# Копируем бинарник uv напрямую из их официального образа. 
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем только файлы зависимостей (чтобы Docker закэшировал этот слой)
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости (--frozen гарантирует точные версии)
RUN uv sync --frozen --no-dev

# Теперь копируем исходный код приложения и миграции базы данных
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Команда, которая будет выполняться при старте контейнера
CMD ["uv", "run", "python", "-m", "app.main"]