# Marketplace Sniffer v2

Telegram-бот для мониторинга Mercari JP — отслеживает новые товары по ключевым словам и присылает мгновенные уведомления в Telegram.

## Как это работает

```
Пользователь → Telegram Bot (Python/aiogram) → PostgreSQL (searches)
                                                    ↑
Go Mercari Scraper ──читает ключевые слова──→ PostgreSQL
        │
        └──новые товары──→ RabbitMQ ──→ Bot отправляет уведомление в Telegram
```

1. **Пользователь** создаёт поиск через Telegram-бота: ключевое слово + ценовой диапазон.
2. **Go-скрапер** каждые 30 секунд обходит Mercari API по активным ключевым словам, проверяет новизну через dedup-таблицу и публикует находки в RabbitMQ.
3. **Python-бот** потребляет RabbitMQ, мгновенно сопоставляет товары с активными поисками в памяти и отправляет Telegram-уведомления с фото.

## Технологии

| Компонент | Стек |
|---|---|
| Telegram Bot | Python 3.13+, aiogram 3.x, SQLAlchemy 2.0 (async), Alembic |
| Mercari Scraper | Go 1.26, pgx, req/v3, Clean Architecture |
| Message Broker | RabbitMQ (AMQP) |
| Database | PostgreSQL 15 |
| Infrastructure | Docker Compose, health checks, graceful shutdown |

## Быстрый старт

### 1. Клонируй и настрой `.env`

```bash
cp .env.example .env
```

Заполни в `.env`:
- `BOT_TOKEN` — токен бота от [@BotFather](https://t.me/BotFather)
- `ADMIN_ID` — твой Telegram ID (узнай у [@getmyid_bot](https://t.me/getmyid_bot))

### 2. Запусти всё через Docker Compose

```bash
docker compose up --build
```

4 сервиса поднимутся автоматически: `db`, `rabbitmq`, `bot`, `scraper_mercari`.

### 3. Проверь

- Напиши `/start` своему боту в Telegram
- Создай поиск: `/add` → ключевое слово → ценовой диапазон
- RabbitMQ UI: http://localhost:15672 (guest/guest)
- Логи: `docker compose logs -f bot scraper_mercari`

## Разработка (запуск без Docker)

```bash
# Инфраструктура в Docker, код — локально
docker compose up -d db rabbitmq

# Бот (терминал 1)
cd bot
uv sync
uv run alembic upgrade head
uv run python -m app.main

# Скрапер (терминал 2)
cd scrapers/mercari
go run ./cmd/scraper/main.go
```

## Структура проекта

```
├── bot/                     # Python Telegram Bot
│   ├── app/
│   │   ├── handlers/        # /start, /add, /list, /premium
│   │   ├── services/        # user, search, matcher, rabbitmq, premium
│   │   ├── db/              # models, enums, middleware, session
│   │   └── keyboards/       # reply + inline keyboards
│   └── alembic/             # миграции БД
├── scrapers/mercari/        # Go Mercari Scraper
│   └── internal/
│       ├── domain/          # models + interfaces
│       ├── usecase/         # scraper orchestrator
│       └── infrastructure/  # mercari client, rabbitmq publisher, postgres repo
├── docker-compose.yml
└── .env
```

## Фичи

- **Мгновенные уведомления** — товары приходят в Telegram через 30-90 секунд после появления на Mercari
- **In-memory matching** — молниеносное сопоставление без запросов к БД на каждый товар
- **DPoP-авторизация** — парсер использует JWT DPoP-токены для обхода защиты Mercari API
- **Jitter + Chrome impersonation** — случайные задержки 2-6 сек и маскировка под браузер
- **Telegram Stars Premium** — монетизация через встроенные платежи Telegram
- **Graceful shutdown** — корректное завершение всех сервисов без потери данных
