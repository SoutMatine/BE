import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

import database as db

logger = logging.getLogger(__name__)


async def send_reminders(bot: Bot):
    try:
        users = await db.get_all_due_users()
        for user_row in users:
            user_id = user_row["user_id"]
            due_words = await db.get_due_words(user_id)
            # Только те у кого reminded = 0
            new_due = [w for w in due_words if not w.get("reminded")]
            if not new_due:
                continue

            count = len(new_due)
            word_examples = ", ".join(w["word"] for w in new_due[:3])
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
                # Помечаем — уже напомнили
                await db.mark_reminded([w["id"] for w in new_due])
            except Exception as e:
                logger.warning(f"Не удалось отправить напоминание {user_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка в send_reminders: {e}")


async def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_reminders,
        trigger=IntervalTrigger(minutes=15),
        args=[bot],
        id="reminder_job",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
