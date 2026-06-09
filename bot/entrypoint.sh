#!/bin/bash
set -e

echo "==> Running database migrations..."
uv run alembic upgrade head

echo "==> Starting Telegram bot..."
exec uv run python -m app.main
