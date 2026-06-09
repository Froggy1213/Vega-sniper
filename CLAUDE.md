# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Marketplace Sniffer v2** — a Telegram bot that monitors Mercari JP for new items matching user search criteria and sends real-time alerts. It's a two-service microservice monorepo: a Python Telegram bot (aiogram) and a Go scraper, communicating via RabbitMQ and sharing a PostgreSQL database.

## Architecture

```
User → Telegram Bot (Python/aiogram) → PostgreSQL (searches table)
                                            ↑
Go Mercari Scraper ──reads keywords──→ PostgreSQL
        │
        └──publishes new items──→ RabbitMQ ──consumed by──→ Bot sends Telegram alert
```

- **User creates a search** via the Telegram bot → saved to `searches` table in PostgreSQL.
- **Go scraper** reads active keywords from the shared DB → scrapes Mercari API → checks item dedup via its own `mercari_parsed_items` table → publishes new items to RabbitMQ's `new_items_queue`.
- **Python bot** consumes RabbitMQ → matches items against an in-memory cache of active searches (refreshed every 60s) → sends Telegram notifications with photos.

Both services share the same PostgreSQL but the scraper uses its own `mercari_parsed_items` table (separate from the bot's Alembic-managed schema) for deduplication.

## Service Layout

### `bot/` — Python Telegram Bot (aiogram 3.x)

```
bot/
├── main.py                          # Entry point
├── pyproject.toml                   # Dependencies (uv)
├── Dockerfile                       # Multi-stage build with uv
├── alembic.ini / alembic/           # Database migrations (SQLAlchemy + Alembic)
└── app/
    ├── main.py                      # Bot initialization, router registration, RabbitMQ consumer startup
    ├── core/config.py               # Pydantic-settings (reads from .env at project root)
    ├── db/
    │   ├── base.py                  # DeclarativeBase, TimestampMixin, UUIDPrimaryKeyMixin
    │   ├── enums.py                 # Platform (mercari), SubscriptionProvider, SubscriptionStatus
    │   ├── session.py               # async engine, session factory, init_db/close_db
    │   ├── middleware.py            # DbSessionMiddleware — injects session + user into handlers
    │   └── models/
    │       ├── user.py              # User — telegram_id, is_premium, is_active
    │       ├── search.py            # Search — user_id, platform, keyword, price_min/max, is_active
    │       └── subscription.py      # Subscription — user_id, provider, status, external_id, expires_at
    ├── handlers/
    │   ├── base.py                  # /start, /help — main menu
    │   ├── search.py                # /add, /list, /cancel — FSM for creating searches
    │   ├── premium.py               # /premium — Telegram Stars payments
    │   └── errors.py                # Global error handler, notifies admin
    ├── keyboards/
    │   ├── menu.py                  # Main reply keyboard with Add Search / My Searches / Premium / Help
    │   └── search.py                # Inline keyboards for price presets and custom input
    └── services/
        ├── user_service.py          # get_or_create_user + premium status refresh
        ├── search_service.py        # Price formatting helpers
        ├── matcher.py               # MarketplaceItem model, in-memory matching against active searches
        ├── rabbitmq.py              # RabbitMQ consumer with auto-reconnect and 60s cache refresh loop
        ├── premium_service.py       # Telegram Stars invoice creation + payment handling
        └── subscription_service.py  # activate_stars_subscription + refresh_premium_status
```

#### Key patterns (bot)

- **DB Session per update**: `DbSessionMiddleware` opens an `AsyncSession`, gets/creates the `User`, injects both into every handler via `data["session"]` and `data["user"]`.
- **FSM for search creation**: `AddSearchFSM` (StatesGroup) walks users through keyword → min price → max price.
- **In-memory matching**: Active searches are cached in `_ACTIVE_SEARCHES_CACHE` and refreshed every 60s. Incoming RabbitMQ items are matched against this cache on the Python side (no per-item DB queries).
- **Premium via Telegram Stars**: Users pay with Telegram Stars (`XTR` currency). Subscription duration is configurable via `PREMIUM_DURATION_DAYS`.

### `scrapers/mercari/` — Go Mercari Scraper (Clean Architecture)

```
scrapers/mercari/
├── go.mod / go.sum                 # Go 1.26
├── Dockerfile                      # Multi-stage build (golang:1.26 → alpine)
├── cmd/scraper/main.go             # Entry point: wires domain, infrastructure, starts scraper loop
└── internal/
    ├── domain/
    │   ├── models.go               # Item, SearchCondition
    │   └── interfaces.go           # ScraperGateway, Publisher, ItemRepository interfaces
    ├── usecase/scraper.go          # Scraper orchestrator: 3 workers + 30s dispatch loop
    └── infrastructure/
        ├── mercari/client.go       # Mercari API client (DPoP auth, request impersonation, proxy rotation)
        ├── rabbitmq/publisher.go   # RabbitMQ publisher with retry (7 attempts, 3s apart)
        └── postgres/repository.go  # Repository: dedup table, GetActiveKeywords, Exists, Save
```

#### Key patterns (scraper)

- **Clean Architecture**: `usecase.Scraper` depends only on domain interfaces; infrastructure packages implement them.
- **Worker pool**: 3 goroutines consume a `chan string` of keywords; dispatcher reads keywords from DB every 30s.
- **Mercari API evasion**: DPoP (Demonstration of Proof-of-Possession) JWT tokens, Chrome impersonation via `req/v3`, optional proxy rotation, random 2-6s jitter between requests.
- **Shared DB access**: Reads directly from the bot's `searches` table via `pgx` (not SQLAlchemy). `GetActiveKeywords` gets distinct active mercari keywords. Item dedup uses its own `mercari_parsed_items` table.

## Infrastructure

- **PostgreSQL** (`sniffer_db`) — port 5432, user `sniffer_admin`
- **RabbitMQ** (`sniffer_rabbitmq`) — port 5672 (AMQP), port 15672 (management UI)
- **Shared `.env`** at project root for local dev. Docker Compose overrides `RABBITMQ_URL` and `DATABASE_URL` with container names.

## Common Dev Commands

### Start all services (Docker)
```bash
docker compose up --build
```

### Run the bot locally (from `bot/`)
```bash
cd bot
uv sync
uv run python -m app.main
```

### Run the scraper locally (from `scrapers/mercari/`)
```bash
cd scrapers/mercari
go run ./cmd/scraper/main.go
```

### Build the scraper
```bash
cd scrapers/mercari
go build -o mercari-scraper ./cmd/scraper/main.go
```

### Run database migrations
```bash
cd bot
uv run alembic upgrade head
```

### Create a new migration
```bash
cd bot
uv run alembic revision --autogenerate -m "description"
```

## Configuration

All settings are in `.env` at the project root (which feeds both services):

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `ADMIN_ID` | Telegram user ID for error alerts |
| `RABBITMQ_URL` | RabbitMQ connection string |
| `DATABASE_URL` | PostgreSQL async connection string |
| `PREMIUM_STARS_PRICE` | Telegram Stars cost for premium (default: 250) |
| `PREMIUM_DURATION_DAYS` | Premium subscription length (default: 30) |
| `PROXIES` | Comma-separated proxy list for Mercari scraper |
| `DB_ECHO` | SQLAlchemy echo mode (boolean) |

## Key Design Decisions

- **Delay-tolerant**: The scraper runs every 30s. Matching is in-memory with a 60s cache refresh. Not real-time but fast enough for marketplace monitoring.
- **Worker-queue dedup**: The scraper uses a DB-backed dedup (`mercari_parsed_items`), so publishing the same item twice is safe — RabbitMQ consumers are idempotent.
- **No gRPC/REST between services**: Communication is purely async via RabbitMQ, making each service independently deployable.
- **Only Mercari supported**: `Platform` enum only has `mercari`. Adding new platforms means: new enum value, new Go scraper microservice publishing to `new_items_queue`, and the matcher handles it generically by `search.platform`.
