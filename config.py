import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8632006440:AAGN980erQPnE4U-GkXmUyeNCPqDttHaUgc")
DB_PATH = "vocab.db"

# Интервалы повторения в часах (алгоритм SuperMemo SM-2 упрощённый)
# [1ч, 6ч, 1д, 3д, 7д, 14д, 30д, 60д]
REVIEW_INTERVALS = [1, 20, 1440, 4320, 10080, 20160, 43200, 86400]
