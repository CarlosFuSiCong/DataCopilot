"""Async PostgreSQL connection pool.

Initialised on application startup and closed on shutdown via FastAPI lifespan.
Services access the pool through this module:

    from app.core import database
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ...")
"""
import logging

import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None


async def connect() -> None:
    global pool
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=5,
    )
    logger.info("Database connection pool created")


async def disconnect() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("Database connection pool closed")
