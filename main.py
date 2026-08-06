"""main.py — نقطة الدخول الرسمية لبوت Knight المهجّن إلى Python.
تشغيل هذا الملف يستورد ويطلق bot.py.
يقرأ التوكن من TELEGRAM_BOT_TOKEN (بيئة) أو settings.json.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# تحميل التوكن من البيئة إلى settings.json قبل تشغيل البوت
_env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
_settings_path = BASE_DIR / "settings.json"
if _env_token and _settings_path.exists():
    import json
    try:
        _data = json.loads(_settings_path.read_text(encoding="utf-8"))
        if not _data.get("telegram_bot_token"):
            _data["telegram_bot_token"] = _env_token
            _settings_path.write_text(json.dumps(_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    import bot as _bot
    raise SystemExit(_bot.main())
