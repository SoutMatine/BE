import aiosqlite
from datetime import datetime
from config import DB_PATH, REVIEW_INTERVALS


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                translation TEXT NOT NULL,
                stage INTEGER DEFAULT 0,
                next_review TEXT NOT NULL,
                reminded INTEGER DEFAULT 0,
                added_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def add_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username or "")
        )
        await db.commit()


async def add_word(user_id: int, word: str, translation: str):
    """Добавить слово. Первое повторение через 1 час."""
    from datetime import timedelta
    next_review = datetime.utcnow() + timedelta(minutes=REVIEW_INTERVALS[0])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO words (user_id, word, translation, stage, next_review) VALUES (?, ?, ?, 0, ?)",
            (user_id, word.strip().lower(), translation.strip().lower(), next_review.isoformat())
        )
        await db.commit()


async def word_exists(user_id: int, word: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM words WHERE user_id = ? AND word = ?",
            (user_id, word.strip().lower())
        ) as cursor:
            return await cursor.fetchone() is not None


async def get_due_words(user_id: int) -> list[dict]:
    """Получить слова, которые пора повторить."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM words WHERE user_id = ? AND next_review <= ? ORDER BY next_review ASC",
            (user_id, now)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_due_users() -> list[dict]:

    """Получить всех пользователей у которых есть слова на повторение."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT DISTINCT user_id FROM words WHERE next_review <= ? AND reminded = 0",
            (now,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def update_word_stage(word_id: int, remembered: bool):
    """
    remembered=True  → stage+1, следующий интервал
    remembered=False → stage остаётся, повтор через тот же интервал (не увеличивается)
    """
    from datetime import timedelta
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT stage FROM words WHERE id = ?", (word_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            stage = row["stage"]

        if remembered:
            new_stage = min(stage + 1, len(REVIEW_INTERVALS) - 1)
        else:
            new_stage = stage  # не сдвигаем стадию

        interval_minutes = REVIEW_INTERVALS[new_stage]
        next_review = datetime.utcnow() + timedelta(minutes=interval_minutes)

        await db.execute(
            "UPDATE words SET stage = ?, next_review = ? WHERE id = ?",
            (new_stage, next_review.isoformat(), word_id)
        )
        await db.commit()


async def get_user_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM words WHERE user_id = ?", (user_id,)) as c:
            total = (await c.fetchone())[0]
        now = datetime.utcnow().isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM words WHERE user_id = ? AND next_review > ?", (user_id, now)
        ) as c:
            learned = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM words WHERE user_id = ? AND next_review <= ?", (user_id, now)
        ) as c:
            due = (await c.fetchone())[0]
        async with db.execute(
            "SELECT word, translation, stage FROM words WHERE user_id = ? ORDER BY added_at DESC LIMIT 5",
            (user_id,)
        ) as cursor:
            recent = await cursor.fetchall()
    return {"total": total, "learned": learned, "due": due, "recent": recent}

async def mark_reminded(word_ids: list[int]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "UPDATE words SET reminded = 1 WHERE id = ?",
            [(wid,) for wid in word_ids]
        )
        await db.commit()

async def reset_reminded(word_id: int):
    """Сбросить флаг после повторения — чтобы следующий цикл снова напомнил."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE words SET reminded = 0 WHERE id = ?", (word_id,))
        await db.commit()
