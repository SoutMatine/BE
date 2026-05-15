from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import REVIEW_INTERVALS, ALLOWED_USERS

async def is_allowed(message: Message) -> bool:
    return message.from_user.id in ALLOWED_USERS

router = Router()
router.message.filter(is_allowed)

# ── Состояния FSM ──────────────────────────────────────────────────────────────

class AddWord(StatesGroup):
    waiting_for_word = State()
    waiting_for_translation = State()

class ReviewWord(StatesGroup):
    waiting_for_answer = State()


# ── /start ─────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 Привет!\n\n"
        "📚 <b>Команды:</b>\n"
        "/add — добавить новое слово\n"
        "/review — повторить слова\n"
        "/stats — статистика\n"
        "/help — справка",
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Как это работает:</b>\n\n"
        "1. Добавь слово командой /add\n"
        "2. Бот попросит перевод - введи его\n"
        "3. В нужное время бот пришлёт напоминание\n"
        "4. Ты пишешь перевод (или «я не помню»)\n\n"
        "⏱ <b>Интервалы повторения:</b>\n"
        "1ч → 6ч → 1д → 3д → 7д → 14д → 30д → 60д\n\n"
        "💡 Если ответишь «я не помню» — интервал не увеличится,\n"
        "слово придёт снова через тот же промежуток.",
        parse_mode="HTML"
    )


# ── /add — добавление слова ────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.set_state(AddWord.waiting_for_word)
    await message.answer(
        "✏️ Введи английское слово (или фразу):",
    )


@router.message(AddWord.waiting_for_word)
async def process_word(message: Message, state: FSMContext):
    word = message.text.strip()
    if not word:
        await message.answer("❗ Слово не может быть пустым. Попробуй ещё раз:")
        return

    # Проверяем дубликат
    if await db.word_exists(message.from_user.id, word):
        await message.answer(
            f"⚠️ Слово <b>{word}</b> уже есть в твоём словаре!\n"
            "Введи другое слово или /cancel для отмены:",
            parse_mode="HTML"
        )
        return

    await state.update_data(word=word)
    await state.set_state(AddWord.waiting_for_translation)
    await message.answer(
        f"🔤 Слово: <b>{word}</b>\n\nТеперь введи его перевод на русский:",
        parse_mode="HTML"
    )


@router.message(AddWord.waiting_for_translation)
async def process_translation(message: Message, state: FSMContext):
    translation = message.text.strip()
    if not translation:
        await message.answer("❗ Перевод не может быть пустым. Попробуй ещё раз:")
        return

    data = await state.get_data()
    word = data["word"]

    await db.add_word(message.from_user.id, word, translation)
    await state.clear()

    await message.answer(
        f"✅ Сохранено!\n\n"
        f"🇬🇧 <b>{word}</b> — 🇷🇺 {translation}\n\n"
        f"⏰ Первое повторение через <b>{REVIEW_INTERVALS[0]} минут</b>.",
        parse_mode="HTML"
    )


# ── /cancel — отмена ───────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.")


# ── /review — ручной запуск повторения ────────────────────────────────────────

@router.message(Command("review"))
async def cmd_review(message: Message, state: FSMContext):
    due = await db.get_due_words(message.from_user.id)
    if not due:
        await message.answer("🎉 Нет слов для повторения прямо сейчас. Загляни позже!")
        return
    await state.update_data(due_words=due, current_index=0)
    await state.set_state(ReviewWord.waiting_for_answer)
    await send_review_word(message, state)


async def send_review_word(message: Message, state: FSMContext):
    data = await state.get_data()
    due_words = data["due_words"]
    idx = data["current_index"]

    if idx >= len(due_words):
        await state.clear()
        await message.answer("🏆 Повторение завершено! Отличная работа!")
        return

    word_data = due_words[idx]
    stage = word_data["stage"]
    total = len(due_words)

    await message.answer(
        f"📝 <b>{idx + 1}/{total}</b>\n\n"
        f"🇬🇧 Слово: <b>{word_data['word']}</b>\n\n"
        f"Напиши перевод (или «я не помню»):",
        parse_mode="HTML"
    )


@router.message(ReviewWord.waiting_for_answer)
async def process_review_answer(message: Message, state: FSMContext):
    answer = message.text.strip().lower()
    data = await state.get_data()
    due_words = data["due_words"]
    idx = data["current_index"]
    word_data = due_words[idx]

    # Проверяем «не помню»
    forgot_phrases = ["я не помню", "не помню", "не знаю", "незнаю", "забыл", "забыла"]
    forgot = any(phrase in answer for phrase in forgot_phrases)

    correct_translation = word_data["translation"].lower()

    if forgot:
        remembered = False
        await db.update_word_stage(word_data["id"], remembered=False)
        interval = REVIEW_INTERVALS[word_data["stage"]]
        await message.answer(
            f"😔 Не страшно!\n"
            f"🇬🇧 <b>{word_data['word']}</b> = 🇷🇺 <b>{correct_translation}</b>\n\n"
            f"⏰ Повторим через <b>{_fmt_interval(interval)}</b> (интервал не изменился).",
            parse_mode="HTML"
        )
    elif answer == correct_translation or _close_enough(answer, correct_translation):
        remembered = True
        await db.update_word_stage(word_data["id"], remembered=True)
        new_stage = min(word_data["stage"] + 1, len(REVIEW_INTERVALS) - 1)
        interval = REVIEW_INTERVALS[new_stage]
        await message.answer(
            f"✅ Правильно!\n"
            f"🇬🇧 <b>{word_data['word']}</b> = 🇷🇺 <b>{correct_translation}</b>\n\n"
            f"⏰ Следующее повторение через <b>{_fmt_interval(interval)}</b>.",
            parse_mode="HTML"
        )
    else:
        remembered = False
        await db.update_word_stage(word_data["id"], remembered=False)
        interval = REVIEW_INTERVALS[word_data["stage"]]
        await message.answer(
            f"❌ Неверно.\n"
            f"Твой ответ: <i>{answer}</i>\n"
            f"🇬🇧 <b>{word_data['word']}</b> = 🇷🇺 <b>{correct_translation}</b>\n\n"
            f"⏰ Повторим через <b>{_fmt_interval(interval)}</b>.",
            parse_mode="HTML"
        )

    await state.update_data(current_index=idx + 1)

    # Следующее слово
    new_data = await state.get_data()
    if new_data["current_index"] >= len(due_words):
        await state.clear()
        await message.answer("🏆 Повторение завершено! Так держать! 💪")
    else:
        await send_review_word(message, state)


# ── /stats ─────────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = await db.get_user_stats(message.from_user.id)

    recent_text = ""
    if stats["recent"]:
        recent_text = "\n\n📋 <b>Последние добавленные:</b>\n"
        stage_emojis = ["🌱", "🌿", "🌳", "⭐", "🌟", "💫", "🏅", "🏆"]
        for word, translation, stage in stats["recent"]:
            emoji = stage_emojis[min(stage, len(stage_emojis) - 1)]
            recent_text += f"{emoji} {word} — {translation}\n"

    await message.answer(
        f"📊 <b>Твоя статистика:</b>\n\n"
        f"📚 Всего слов: <b>{stats['total']}</b>\n"
        f"🔔 Ожидают повторения: <b>{stats['due']}</b>\n"
        f"✅ Изучаются: <b>{stats['learned']}</b>"
        f"{recent_text}",
        parse_mode="HTML"
    )


# ── Вспомогательные функции ────────────────────────────────────────────────────

def _fmt_interval(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} мин."
    elif minutes < 1440:
        hours = minutes // 60
        mins = minutes % 60
        if mins:
            return f"{hours} ч. {mins} мин."
        return f"{hours} ч."
    else:
        days = minutes // 1440
        return f"{days} дн."


def _close_enough(answer: str, correct: str) -> bool:
    """Допускаем небольшие опечатки (1 символ) для коротких слов."""
    if abs(len(answer) - len(correct)) > 1:
        return False
    if len(correct) <= 3:
        return answer == correct
    # Расстояние Хэмминга / простая проверка
    diffs = sum(a != b for a, b in zip(answer, correct))
    return diffs <= 1 and abs(len(answer) - len(correct)) == 0
