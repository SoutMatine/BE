import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

import database as db

logger = logging.getLogger(__name__)


async def send_reminders(bot: Bot):
    """Каждые 30 минут проверяем — у кого есть слова на повторение."""
    try:
        users = await db.get_all_due_users()
        for user_row in users:
            user_id = user_row["user_id"]
            due_words = await db.get_due_words(user_id)
            if not due_words:
                continue
            count = len(due_words)
            word_examples = ", ".join(w["word"] for w in due_words[:3])
            if count > 3:
                word_examples += f" и ещё {count - 3}..."

            try:
                await bot.send_message(
                    user_id,
                    f"🔔 <b>Время повторить слова!</b>\n\n"
                    f"📚 Слов для повторения: <b>{count}</b>\n"
                    f"📝 {word_examples}\n\n"
                    f"Используй /review чтобы начать.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить напоминание {user_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка в send_reminders: {e}")


async def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_reminders,
        trigger=IntervalTrigger(minutes=30),
        args=[bot],
        id="reminder_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started (check every 30 min)")
    return scheduler
