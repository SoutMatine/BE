import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8632006440:AAGN980erQPnE4U-GkXmUyeNCPqDttHaUgc")
DB_PATH = "vocab.db"

# Интервалы повторения в часах (алгоритм SuperMemo SM-2 упрощённый)
# [1ч, 6ч, 1д, 3д, 7д, 14д, 30д, 60д]
REVIEW_INTERVALS = [1, 6, 24, 72, 168, 336, 720, 1440]
