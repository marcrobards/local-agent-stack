import aiosqlite

DB_PATH = "/data/shopping.db"


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS searches (
                id          TEXT PRIMARY KEY,
                created_at  DATETIME DEFAULT (datetime('now')),
                updated_at  DATETIME DEFAULT (datetime('now')),
                status      TEXT DEFAULT 'clarifying',
                spec        TEXT,
                results     TEXT,
                error       TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          TEXT PRIMARY KEY,
                search_id   TEXT REFERENCES searches(id),
                role        TEXT,
                content     TEXT,
                created_at  DATETIME DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS preferences (
                id          TEXT PRIMARY KEY,
                key         TEXT UNIQUE,
                value       TEXT,
                updated_at  DATETIME DEFAULT (datetime('now'))
            );
        """)
        await db.commit()
    finally:
        await db.close()
