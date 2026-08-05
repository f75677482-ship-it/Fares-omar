# DEPRECATED — DO NOT RUN
# This file is intentionally locked. The project now runs through `index.py`
# which is the ONLY master entry point.
# Anything left here is preserved only so old imports that look for bot_core.py
# do not break imports during a migration.
raise SystemExit(
    "bot_core.py is locked. Run `python index.py` instead. "
    "All Telegram + WhatsApp logic has been moved to index.py."
)
