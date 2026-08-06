"""Knight Bot - ملف الإعدادات الرئيسي (محول من config.js)
يحتوي على ثوابت البوت وروابط الـ APIs والمفاتيح.
يتم تحميل القيم من settings.json إن وُجدت، وإلا تُستخدم القيم الافتراضية.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict

# ============================ APIs ============================
APIs: Dict[str, str] = {
    "xteam": "https://api.xteam.xyz",
    "dzx": "https://api.dhamzxploit.my.id",
    "lol": "https://api.lolhuman.xyz",
    "violetics": "https://violetics.pw",
    "neoxr": "https://api.neoxr.my.id",
    "zenzapis": "https://zenzapis.xyz",
    "akuari": "https://api.akuari.my.id",
    "akuari2": "https://apimu.my.id",
    "nrtm": "https://fg-nrtm.ddns.net",
    "bg": "http://bochil.ddns.net",
    "fgmods": "https://api-fgmods.ddns.net",
}

APIKeys: Dict[str, str] = {
    "https://api.xteam.xyz": "d90a9e986e18778b",
    "https://api.lolhuman.xyz": "85faf717d0545d14074659ad",
    "https://api.neoxr.my.id": "yourkey",
    "https://violetics.pw": "beta",
    "https://zenzapis.xyz": "yourkey",
    "https://api-fgmods.ddns.net": "fg-dylux",
}

WARN_COUNT = 3


# ============================ Defaults ============================
DEFAULT_SETTINGS: Dict[str, Any] = {
    "packname": "Knight Bot",
    "author": "",
    "botName": "Knight Bot",
    "botOwner": "Professor",
    "ownerNumber": "919876543210",
    "giphyApiKey": "qnl7ssQChTdPjsKta2Ax2LMaGXz303tq",
    "commandMode": "public",
    "maxStoreMessages": 10,
    "storeWriteInterval": 10000,
    "description": "بوت واتساب لإدارة المجموعات والتحميل من السوشل ميديا والذكاء الاصطناعي.",
    "version": "3.0.8",
    "repoUrl": "https://t.me/Faresw_bot",
    "channelLink": "https://whatsapp.com/channel/0029Vb8jjfWCRs1sVz0x1w3v",
    "updateZipUrl": "https://github.com/faresjahsh/Knightbot-MD/archive/refs/heads/main.zip",
    "telegram_bot_token": "",
    "allowed_telegram_user_ids": [],
    "default_language": "ar",
}


def _load_settings_file() -> Dict[str, Any]:
    settings_path = Path(__file__).resolve().parent / "settings.json"
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_settings() -> Dict[str, Any]:
    merged = {**DEFAULT_SETTINGS, **_load_settings_file()}
    env_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if env_token:
        merged["telegram_bot_token"] = env_token
    env_allowed = os.getenv("ALLOWED_TELEGRAM_USER_IDS")
    if env_allowed:
        try:
            merged["allowed_telegram_user_ids"] = [
                int(x.strip()) for x in env_allowed.split(",") if x.strip()
            ]
        except Exception:
            pass
    return merged


SETTINGS: Dict[str, Any] = load_settings()


# Global convenient globals (compat with JS-style global.X)
PACKNAME = SETTINGS.get("packname", "Knight Bot")
AUTHOR = SETTINGS.get("author", "")
BOT_NAME = SETTINGS.get("botName", "Knight Bot")
BOT_OWNER = SETTINGS.get("botOwner", "Professor")
OWNER_NUMBER = SETTINGS.get("ownerNumber", "919876543210")
CHANNEL_LINK = SETTINGS.get("channelLink", "https://whatsapp.com/channel/0029Vb8jjfWCRs1sVz0x1w3v")
REPO_URL = SETTINGS.get("repoUrl", "https://t.me/Faresw_bot")
VERSION = SETTINGS.get("version", "3.0.8")
COMMAND_MODE = SETTINGS.get("commandMode", "public")
TELEGRAM_BOT_TOKEN = SETTINGS.get("telegram_bot_token", "")
ALLOWED_TELEGRAM_USER_IDS = set(SETTINGS.get("allowed_telegram_user_ids", []) or [])
DEFAULT_LANGUAGE = SETTINGS.get("default_language", "ar")
GIPHY_API_KEY = SETTINGS.get("giphyApiKey", "")
