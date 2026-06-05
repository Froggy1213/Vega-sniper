"""Entry point: run with `uv run python -m app.main` from the bot/ directory."""

from app.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
