#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index.py — Master orchestrator for the Fares-Omar bot.

This is the ONLY entry point of the project. Responsibilities:

1. Telegram bot host (python-telegram-bot v20.x, async).
2. Per-number WhatsApp session manager — spawns an isolated Node.js
   worker per linked phone number. No shared state between numbers,
   so linking a new number never slows down or blocks the rest.
3. Pair-code / linking backend — talks to the existing Node pairing
   runtime (`index.js` / `server.js`) over HTTP and listens for the
   `linked` webhook to dispatch the FULL number bundle to the Telegram
   user immediately, and the alive message to the linked WhatsApp
   number the moment the worker connects.
4. Settings orchestration — every number has its own sessionId,
   session directory, settings JSON, logger prefix, reconnect timer.

Dependencies: requests, python-telegram-bot>=20,<23, pymongo.
Node-side: the project must have `npm install` ran once so the
`@whiskeysockets/baileys` engine and the embedded pairing runtime
(`server.js` / `index.js`) are available.
"""
from __future__ import annotations

import asyncio
import atexit
import html
import json
import logging
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import importlib.util
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# 0.  Bootstrap deps (auto-install if missing)
# ---------------------------------------------------------------------------
def _ensure(mod: str, pip: Optional[str] = None) -> None:
    if importlib.util.find_spec(mod) is not None:
        return
    name = pip or mod
    print(f"[boot] installing missing python package: {name}", flush=True)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


for _mod, _pip in (
    ("requests", "requests>=2.31.0"),
    ("pymongo", "pymongo[srv]>=4.6.0"),
    ("telegram", "python-telegram-bot>=20,<23"),
):
    try:
        _ensure(_mod, _pip)
    except Exception as exc:  # pragma: no cover - bootstrap only
        print(f"[boot] could not install {_pip}: {exc}", flush=True)

import requests
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Conflict
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# 1.  Paths and constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SETTINGS_PATH = BASE_DIR / "bot_settings.json"
USERS_PATH = BASE_DIR / "bot_users.json"
USERS_EMOJI_PATH = BASE_DIR / "user_emoji_settings.json"
LINKED_NUMBERS_PATH = BASE_DIR / "linked_whatsapp_users.json"
NUMBERS_SECRETS_PATH = BASE_DIR / "numbers_secrets.json"
WORKER_OUT_DIR = BASE_DIR / "data" / "workers"
WORKER_OUT_DIR.mkdir(parents=True, exist_ok=True)

# Defaults — overridable via env / settings
DEFAULT_BOT_TOKEN = "8631941557:AAH-d476_Rrtvvgc5aOba8SPzMJnno5sG4o"
DEFAULT_ADMIN_ID = 7231690686
DEFAULT_CONTACT_NUMBER = "967773987296"
DEFAULT_CHANNEL_URL = "https://whatsapp-pairing-api-production-639f.up.railway.app/"
DEFAULT_BRAND = "بوت الربط بايثون"
DEFAULT_PAIR_API_URL = "http://127.0.0.1:3100"
PAIRING_API_ROUTE = os.getenv("PAIRING_API_ROUTE", "/api/pairing").strip() or "/api/pairing"
LEGACY_PAIRING_API_ROUTE = os.getenv("LEGACY_PAIRING_API_ROUTE", "/pair").strip() or "/pair"

# MongoDB (used as the only durable backend; /data stays as cache)
MONGODB_URI = (
    os.getenv("MONGODB_URI") or os.getenv("MONGO_URL") or ""
).strip()
MONGODB_DB_NAME = (os.getenv("MONGODB_DB_NAME") or "whatsapp_pairing_api").strip()
MONGODB_SESSIONS_COLL = (
    os.getenv("MONGODB_SESSIONS_COLLECTION") or "whatsapp_sessions"
).strip()
MONGODB_STATE_COLL = (os.getenv("MONGODB_STATE_COLLECTION") or "telegram_bot_state").strip()
MONGODB_USERS_COLL = (
    os.getenv("MONGODB_USER_CONFIG_COLLECTION") or "user_configs"
).strip()
MONGODB_TIMEOUT_MS = max(5000, int(os.getenv("MONGODB_TIMEOUT_MS") or "20000"))

# Companion / pairing backend (Node `server.js` or `index.js`)
COMPANION_PORT = int(os.getenv("COMPANION_PORT") or os.getenv("PAIRING_SERVER_PORT") or "3100")
COMPANION_BASE_URL = (
    os.getenv("COMPANION_BASE_URL") or f"http://127.0.0.1:{COMPANION_PORT}"
).rstrip("/")
ORCHESTRATOR_PORT = int(
    os.getenv("ORCHESTRATOR_PORT") or os.getenv("PORT") or os.getenv("WEB_PORT") or "8080"
)
TEMP_SESSION_TTL_SECONDS = max(120, int(os.getenv("PAIR_CODE_TTL_SECONDS") or "120"))

# ---------------------------------------------------------------------------
# 2.  Logging
# ---------------------------------------------------------------------------
LOG_THROTTLE_WINDOW = 5.0
_LOG_BUCKETS: Dict[str, List[float]] = defaultdict(list)
_LOG_SUPPRESSED_COUNTERS: Dict[str, int] = defaultdict(int)

_NOISY_PATTERNS = (
    re.compile(r"closing session", re.I),
    re.compile(r"decrypted message with closed session", re.I),
    re.compile(r"pendingprekey", re.I),
    re.compile(r"currentratchet", re.I),
    re.compile(r"ephemeralkeypair", re.I),
    re.compile(r"basekeytype", re.I),
)

_real_log = logging.getLogger


def _real_logger() -> logging.Logger:
    logger = _real_log("index")
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


logger = _real_logger()


def _should_suppress(line: str) -> bool:
    return any(p.search(line) for p in _NOISY_PATTERNS)


def _emit(level: int, msg: str) -> None:
    if _should_suppress(msg):
        bucket = msg[:60]
        now = time.time()
        bucket_times = _LOG_BUCKETS[bucket]
        bucket_times[:] = [t for t in bucket_times if now - t < LOG_THROTTLE_WINDOW]
        bucket_times.append(now)
        if len(bucket_times) > 3:
            _LOG_SUPPRESSED_COUNTERS[bucket] += 1
            return
    logger.log(level, msg)


# ---------------------------------------------------------------------------
# 3.  .env loader and settings
# ---------------------------------------------------------------------------
ENV_CACHE: Dict[str, str] = {}


def _load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value
            ENV_CACHE[key] = value


_load_env_file()

BOT_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TOKEN")
    or DEFAULT_BOT_TOKEN
).strip()
ADMIN_ID = int(os.getenv("TELEGRAM_DEVELOPER_ID") or os.getenv("ADMIN_ID") or DEFAULT_ADMIN_ID)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "start_message": "🤖 أهلاً بك في بوت الربط.\nاكتب /menu لإدارة أرقامك.",
    "alive_message": "✅ *بوتك يعمل الآن*\n\n📱 الرقم: {phone}\n⚙️ الجلسة: {session_id}\n⏱ الحالة: متصل",
    "linked_message_template": (
        "✅ *تم ربط الرقم بنجاح*\n\n"
        "🔢 *الرقم:* `{phone}`\n"
        "🔐 *كود الربط:* `{code}`\n"
        "🆔 *معرّف الجلسة:* `{session_id}`\n"
        "🔗 *رابط البوت:* `{bot_link}`\n"
        "🔑 *كلمة المرور:* `{password}`\n"
        "📅 *وقت الربط:* `{ts}`"
    ),
    "force_sub_channel": os.getenv("FORCE_SUB_CHANNEL", DEFAULT_CHANNEL_URL),
    "auto_alive_on_link": True,
    "send_alive_to_phone_on_link": True,
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null") or default
    except Exception:
        return default


def _write_json_atomic(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


SETTINGS: Dict[str, Any] = {**DEFAULT_SETTINGS, **_read_json(SETTINGS_PATH, {})}
for k, v in DEFAULT_SETTINGS.items():
    SETTINGS.setdefault(k, v)
REGISTERED_USERS: Set[int] = set(_read_json(USERS_PATH, []))
USER_EMOJI_SETTINGS: Dict[str, str] = _read_json(USERS_EMOJI_PATH, {})  # key: str(user_id)
LINKED_NUMBERS: Dict[str, Dict[str, Any]] = _read_json(LINKED_NUMBERS_PATH, {})  # phone → record
NUMBER_SECRETS: Dict[str, Dict[str, Any]] = _read_json(NUMBERS_SECRETS_PATH, {})  # phone/site → {password, settings_url, ts}


def persist_settings() -> None:
    _write_json_atomic(SETTINGS_PATH, SETTINGS)


def persist_registered_users() -> None:
    _write_json_atomic(USERS_PATH, sorted(REGISTERED_USERS))


def persist_user_emoji() -> None:
    _write_json_atomic(USERS_EMOJI_PATH, USER_EMOJI_SETTINGS)


def persist_linked_numbers() -> None:
    _write_json_atomic(LINKED_NUMBERS_PATH, LINKED_NUMBERS)


def persist_number_secrets() -> None:
    _write_json_atomic(NUMBERS_SECRETS_PATH, NUMBER_SECRETS)


# ---------------------------------------------------------------------------
# 4.  MongoDB bridge — best-effort, falls back to flat JSON
# ---------------------------------------------------------------------------
_MONGO: Optional[MongoClient] = None
_DB = None


def _mongo_db():
    global _MONGO, _DB
    if not MONGODB_URI:
        return None
    if _DB is not None:
        return _DB
    try:
        _MONGO = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS,
            connectTimeoutMS=MONGODB_TIMEOUT_MS,
            maxPoolSize=10,
            retryWrites=True,
        )
        _DB = _MONGO[MONGODB_DB_NAME]
        return _DB
    except Exception as exc:
        logger.warning(f"mongo not reachable, falling back to local files: {exc}")
        return None


def _mongo_sync_local_to_cloud() -> None:
    db = _mongo_db()
    if db is None:
        return
    try:
        db[MONGODB_STATE_COLL].update_one(
            {"_id": "settings"},
            {"$set": SETTINGS},
            upsert=True,
        )
        db[MONGODB_STATE_COLL].update_one(
            {"_id": "users"},
            {"$set": {"ids": sorted(REGISTERED_USERS)}},
            upsert=True,
        )
        db[MONGODB_STATE_COLL].update_one(
            {"_id": "emoji"},
            {"$set": USER_EMOJI_SETTINGS},
            upsert=True,
        )
        db[MONGODB_STATE_COLL].update_one(
            {"_id": "linked"},
            {"$set": LINKED_NUMBERS},
            upsert=True,
        )
        db[MONGODB_STATE_COLL].update_one(
            {"_id": "secrets"},
            {"$set": NUMBER_SECRETS},
            upsert=True,
        )
    except Exception as exc:
        logger.warning(f"mongo sync skipped: {exc}")


# ---------------------------------------------------------------------------
# 5.  Utilities
# ---------------------------------------------------------------------------
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_phone(raw: Any) -> str:
    s = str(raw or "").translate(ARABIC_DIGITS)
    return re.sub(r"\D", "", s).strip()


def safe_jid(phone: str) -> str:
    n = normalize_phone(phone)
    return f"{n}@s.whatsapp.net" if n else ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def tg_send(bot, chat_id: int, text: str, reply_markup=None, parse_mode=None) -> None:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode or "Markdown",
        )
    except Exception as exc:
        logger.warning(f"tg_send failed for {chat_id}: {exc}")
        # Fallback: send as plain text
        try:
            await bot.send_message(chat_id=chat_id, text=html.escape(text))
        except Exception as exc2:
            logger.warning(f"tg_send plain fallback failed: {exc2}")


# ---------------------------------------------------------------------------
# 6.  Telegram keyboards + UI
# ---------------------------------------------------------------------------
EMOJI_CHOICES = ["💤", "❤️", "🔥", "🌹", "⭐", "😎", "🤖", "👑", "🧠", "🎯"]


def main_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("📱 أرقامي المربوطة", callback_data="cb:my_numbers")],
        [InlineKeyboardButton("🔗 ربط رقم جديد", callback_data="cb:new_pair")],
        [
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="cb:settings"),
            InlineKeyboardButton("❓ المساعدة", callback_data="cb:help"),
        ],
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton("🛠 لوحة المطور", callback_data="cb:dev"),
                InlineKeyboardButton("📊 الإحصائيات", callback_data="cb:stats"),
            ]
        )
    return InlineKeyboardMarkup(rows)


def emoji_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(EMOJI_CHOICES), 5):
        rows.append(
            [
                InlineKeyboardButton(e, callback_data=f"cb:emoji:{i}")
                for i, e in enumerate(EMOJI_CHOICES[i : i + 5], start=i)
            ]
        )
    rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="cb:cancel")])
    return InlineKeyboardMarkup(rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 رسالة البدء", callback_data="cb:set:start_message")],
            [InlineKeyboardButton("💚 رسالة Alive", callback_data="cb:set:alive_message")],
            [InlineKeyboardButton("📢 قناة الاشتراك الإجباري", callback_data="cb:set:force_sub")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="cb:home")],
        ]
    )


def owned_numbers_keyboard(phones: List[str]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for p in phones[:10]:
        rows.append(
            [InlineKeyboardButton(f"📱 {p}", callback_data=f"cb:nb:{p}")]
        )
    if not phones:
        rows.append([InlineKeyboardButton("❗ لا يوجد أرقام مربوطة بعد", callback_data="cb:cancel")])
    rows.append([InlineKeyboardButton("🔗 ربط رقم جديد", callback_data="cb:new_pair")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="cb:home")])
    return InlineKeyboardMarkup(rows)


def number_detail_keyboard(phone: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("♻️ إعادة الاتصال", callback_data=f"cb:nact:reconnect:{phone}")],
            [InlineKeyboardButton("🧪 فحص الجلسة", callback_data=f"cb:nact:check:{phone}")],
            [InlineKeyboardButton("🚪 فصل الرقم", callback_data=f"cb:nact:unlink:{phone}")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="cb:my_numbers")],
        ]
    )


# ---------------------------------------------------------------------------
# 7.  Worker manager — one subprocess per linked number, isolated
# ---------------------------------------------------------------------------
class WorkerSpec:
    """Immutable per-number spawn specification."""

    __slots__ = (
        "phone",
        "session_id",
        "session_dir",
        "user_id",
        "started_at",
        "alive_message",
        "linked_at",
        "site_password",
        "bot_link",
    )

    def __init__(
        self,
        phone: str,
        session_id: str,
        session_dir: Path,
        user_id: int,
        alive_message: str,
        linked_at: str,
        site_password: str,
        bot_link: str,
    ) -> None:
        self.phone = phone
        self.session_id = session_id
        self.session_dir = session_dir
        self.user_id = user_id
        self.alive_message = alive_message
        self.linked_at = linked_at
        self.site_password = site_password
        self.bot_link = bot_link


class WorkerManager:
    """Owns all live WhatsApp worker subprocesses. Thread-safe."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self._lock = threading.RLock()
        self._procs: Dict[str, subprocess.Popen] = {}
        self._specs: Dict[str, WorkerSpec] = {}
        self._events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._reader_threads: Dict[str, threading.Thread] = {}
        self._auto_reconnect: Dict[str, Dict[str, Any]] = {}

    # ---------- spawn ----------
    def spawn(self, spec: WorkerSpec) -> None:
        with self._lock:
            # Kill any existing worker for the same phone to keep it single
            self._kill_locked(spec.phone, reason="respawn")
            session_dir = spec.session_dir
            session_dir.mkdir(parents=True, exist_ok=True)

            node_entry = BASE_DIR / "worker.js"
            if not node_entry.exists():
                logger.error("worker.js missing — cannot spawn worker")
                return

            env = os.environ.copy()
            env["WORKER_PHONE"] = spec.phone
            env["WORKER_SESSION_ID"] = spec.session_id
            env["WORKER_SESSION_DIR"] = str(session_dir)
            env["WORKER_USER_ID"] = str(spec.user_id or 0)
            env["WORKER_ALIVE_MESSAGE"] = spec.alive_message
            env["WORKER_LINKED_AT"] = spec.linked_at
            env["WORKER_SITE_PASSWORD"] = spec.site_password
            env["WORKER_BOT_LINK"] = spec.bot_link
            env["WORKER_MONGO_URI"] = MONGODB_URI
            env["WORKER_MONGO_DB"] = MONGODB_DB_NAME
            env["WORKER_MONGO_COLL"] = MONGODB_SESSIONS_COLL
            env["WORKER_COMPANION_URL"] = COMPANION_BASE_URL
            # Prevent the child from forking back into the orchestrator
            env["WORKER_CHILD"] = "1"

            log_file = WORKER_OUT_DIR / f"{spec.session_id}.log"
            log_handle = open(log_file, "ab", buffering=0)

            proc = subprocess.Popen(
                ["node", str(node_entry)],
                cwd=str(BASE_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
            self._procs[spec.phone] = proc
            self._specs[spec.phone] = spec
            logger.info(f"[worker:{spec.session_id}] spawned pid={proc.pid} phone={spec.phone}")

            t = threading.Thread(
                target=self._reader_loop,
                args=(spec.phone, proc, log_handle),
                daemon=True,
                name=f"worker-reader-{spec.session_id}",
            )
            t.start()
            self._reader_threads[spec.phone] = t

    # ---------- reader loop ----------
    def _reader_loop(self, phone: str, proc: subprocess.Popen, log_handle) -> None:
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").rstrip()
                log_handle.write((raw + "\n").encode("utf-8", errors="replace"))
                if not raw:
                    continue
                if raw.startswith("{") and raw.endswith("}"):
                    try:
                        evt = json.loads(raw)
                    except Exception:
                        continue
                    self._dispatch_event(phone, evt)
                elif raw.startswith("[worker"):
                    # friendly readable log, surface at INFO level
                    _emit(logging.INFO, raw)
        except Exception as exc:
            logger.warning(f"[worker:{phone}] reader crashed: {exc}")
        finally:
            try:
                log_handle.close()
            except Exception:
                pass
            self._handle_death(phone, proc)

    # ---------- event dispatch ----------
    def _dispatch_event(self, phone: str, evt: Dict[str, Any]) -> None:
        kind = str(evt.get("type") or "").lower()
        self._events[phone].append(evt)
        # Keep recent only
        if len(self._events[phone]) > 50:
            self._events[phone] = self._events[phone][-50:]
        if kind == "connected":
            asyncio.run_coroutine_threadsafe(
                self._announce_ready(phone), self.bot._loop
            )
        elif kind == "alive_sent":
            logger.info(f"[worker:{phone}] alive delivered")
        elif kind == "credentials_saved":
            logger.info(f"[worker:{phone}] local creds ok")
        elif kind == "message":
            pass  # reserved for future cross-bridge forwarding
        elif kind == "fatal":
            logger.warning(f"[worker:{phone}] fatal: {evt.get('reason')}")

    async def _announce_ready(self, phone: str) -> None:
        spec = self._specs.get(phone)
        if not spec:
            return
        record = LINKED_NUMBERS.get(phone) or {}
        owner = record.get("owner_id") or spec.user_id or ADMIN_ID
        text = (
            f"✅ *الرقم متصل الآن*\n\n"
            f"🔢 الرقم: `{phone}`\n"
            f"🆔 الجلسة: `{spec.session_id}`\n"
            f"⏱ منذ: {now_iso()}"
        )
        try:
            await self.bot.app.bot.send_message(chat_id=int(owner), text=text)
        except Exception as exc:
            logger.warning(f"announce_ready send failed: {exc}")
        # Auto-send alive message to the linked phone (its own jid)
        try:
            payload = {
                "cmd": "send_message",
                "to": safe_jid(phone),
                "text": spec.alive_message,
            }
            requests.post(
                f"{COMPANION_BASE_URL}/internal/send",
                json=payload,
                timeout=5,
            )
        except Exception:
            pass  # best-effort

    # ---------- crash / reconnect ----------
    def _handle_death(self, phone: str, proc: subprocess.Popen) -> None:
        with self._lock:
            if self._procs.get(phone) is proc:
                self._procs.pop(phone, None)
        logger.warning(f"[worker:{phone}] exited code={proc.returncode}")
        # Schedule auto-reconnect for linked phones — never affects other workers
        if phone in LINKED_NUMBERS:
            self._auto_reconnect[phone] = {"at": time.time() + 5.0}
            threading.Thread(
                target=self._auto_reconnect_loop, args=(phone,), daemon=True
            ).start()

    def _auto_reconnect_loop(self, phone: str) -> None:
        while phone in LINKED_NUMBERS and phone not in self._procs:
            target_at = self._auto_reconnect.get(phone, {}).get("at") or time.time()
            sleep_for = max(1.0, target_at - time.time())
            time.sleep(sleep_for)
            if phone in self._procs:
                return
            spec = self._specs.get(phone)
            if not spec:
                record = LINKED_NUMBERS.get(phone, {})
                spec = self._build_spec_from_record(phone, record)
                if not spec:
                    return
            logger.info(f"[worker:{phone}] auto-reconnecting")
            try:
                self.spawn(spec)
            except Exception as exc:
                logger.warning(f"[worker:{phone}] reconnect failed: {exc}")
                self._auto_reconnect[phone] = {"at": time.time() + 10.0}

    # ---------- helpers ----------
    def _build_spec_from_record(self, phone: str, record: Dict[str, Any]) -> Optional[WorkerSpec]:
        sid = record.get("session_id") or phone
        session_dir = (BASE_DIR / "data" / "sessions" / sid).resolve()
        return WorkerSpec(
            phone=phone,
            session_id=sid,
            session_dir=session_dir,
            user_id=int(record.get("owner_id") or ADMIN_ID),
            alive_message=record.get("alive_message")
            or SETTINGS.get("alive_message")
            or DEFAULT_SETTINGS["alive_message"],
            linked_at=record.get("linked_at") or now_iso(),
            site_password=record.get("site_password") or "",
            bot_link=record.get("bot_link") or "",
        )

    def _kill_locked(self, phone: str, reason: str = "stop") -> None:
        proc = self._procs.pop(phone, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            except Exception as exc:
                logger.warning(f"[worker:{phone}] kill error ({reason}): {exc}")
        self._specs.pop(phone, None)
        self._events.pop(phone, None)
        self._reader_threads.pop(phone, None)

    def kill_all(self) -> None:
        with self._lock:
            phones = list(self._procs.keys())
        for p in phones:
            self._kill_locked(p, reason="shutdown")

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                phone: {
                    "pid": self._procs.get(phone).pid if self._procs.get(phone) else None,
                    "alive": (self._procs.get(phone).poll() is None)
                    if self._procs.get(phone)
                    else False,
                    "session_id": self._specs.get(phone).session_id if self._specs.get(phone) else None,
                    "linked_at": self._specs.get(phone).linked_at if self._specs.get(phone) else None,
                    "last_event": (self._events.get(phone) or [None])[-1],
                }
                for phone in self._specs.keys()
            }


# ---------------------------------------------------------------------------
# 8.  HTTP control plane: /pair, /internal/send, /health, /workers
# ---------------------------------------------------------------------------
class _PairingAPI:
    """Talks to the Node-side pairing runtime and brokers pair events."""

    def __init__(self, manager: WorkerManager) -> None:
        self.manager = manager

    def _candidate_routes(self, *routes: str) -> List[str]:
        seen: Set[str] = set()
        ordered: List[str] = []
        for route in routes:
            route = str(route or "").strip()
            if not route:
                continue
            normalized = route if route.startswith("/") else f"/{route}"
            if normalized not in seen:
                seen.add(normalized)
                ordered.append(normalized)
        return ordered

    def _json_request(
        self,
        method: str,
        routes: List[str],
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        timeout: int = 15,
    ) -> Tuple[Optional[requests.Response], Dict[str, Any], str]:
        last_error = ""
        for route in self._candidate_routes(*routes):
            try:
                response = requests.request(
                    method.upper(),
                    f"{COMPANION_BASE_URL}{route}",
                    json=json_payload,
                    timeout=timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                logger.warning(f"{route} request failed: {exc}")
                continue

            data: Dict[str, Any] = {}
            try:
                if response.headers.get("Content-Type", "").startswith("application/json"):
                    data = response.json() or {}
            except Exception:
                data = {}
            if response.status_code in {404, 405}:
                last_error = data.get("error") or f"HTTP {response.status_code}"
                continue
            return response, data, route
        return None, {}, last_error

    # -- calls into Node --
    def request_pair_code(self, phone: str, user_id: int) -> Tuple[bool, str, str]:
        phone = normalize_phone(phone)
        if not phone or len(phone) < 8:
            return False, "", "رقم غير صالح"

        response, data, route = self._json_request(
            "POST",
            [PAIRING_API_ROUTE, LEGACY_PAIRING_API_ROUTE],
            json_payload={"phone": phone, "user_id": user_id},
            timeout=20,
        )
        if response is None:
            return False, "", "خادم الاقتران غير متاح"

        if response.status_code == 200 and (data.get("code") or data.get("pairCode")):
            code = str(data.get("code") or data.get("pairCode") or "").strip()
            return True, code, "ok"

        error_message = (
            data.get("error")
            or data.get("message")
            or (f"HTTP {response.status_code}" if response is not None else route or "طلب فاشل")
        )
        return False, "", str(error_message)

    def fetch_site_credentials(self, phone: str, code: str) -> Dict[str, str]:
        response, data, _route = self._json_request(
            "POST",
            ["/pair/site-credentials", "/api/pairing/site-credentials"],
            json_payload={"phone": phone, "code": code},
            timeout=10,
        )
        if response is not None and response.status_code == 200:
            return data
        return {}

    def delete_session_remote(self, phone: str) -> bool:
        phone = normalize_phone(phone)
        if not phone:
            return False

        response, _data, _route = self._json_request(
            "DELETE",
            [f"/api/session/{phone}", "/unpair"],
            json_payload={"phone": phone},
            timeout=10,
        )
        return bool(response is not None and response.status_code == 200)


# HTTP request handler exposed to the Node pairing runtime
class PairWebhookHandler(BaseHTTPRequestHandler):
    pair_api: _PairingAPI = None  # populated at boot
    bot = None  # populated at boot

    def log_message(self, *_args) -> None:  # silence stderr noise
        return

    def _write(self, code: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._write(200, {"ok": True, "ts": now_iso()})
        elif path == "/workers":
            state = PairWebhookHandler.pair_api.manager.state() if PairWebhookHandler.pair_api else {}
            self._write(200, {"workers": state})
        else:
            self._write(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        if path == "/pair/webhook":
            self._on_link_event(payload)
        elif path == "/internal/send":
            self._write(200, {"ok": True})
        else:
            self._write(404, {"error": "not_found"})

    # -- link event from Node pairing runtime --
    def _on_link_event(self, payload: Dict[str, Any]) -> None:
        phone = normalize_phone(payload.get("phone") or payload.get("number") or "")
        code = str(payload.get("code") or "").strip()
        user_id = int(payload.get("user_id") or payload.get("owner_id") or 0)
        sess_id = (payload.get("session_id") or phone).strip()
        ts = payload.get("linked_at") or now_iso()
        password = str(payload.get("site_password") or "")
        bot_link = str(payload.get("bot_link") or "")
        if not phone:
            self._write(400, {"error": "missing phone"})
            return

        # Persist linked record immediately so even if worker is slow,
        # /my_numbers works without delay.
        record = {
            "phone": phone,
            "session_id": sess_id,
            "owner_id": user_id,
            "linked_at": ts,
            "code": code,
            "site_password": password,
            "bot_link": bot_link,
            "status": "linked",
        }
        LINKED_NUMBERS[phone] = record
        if password:
            NUMBER_SECRETS[phone] = {
                "password": password,
                "ts": ts,
                "settings_url": bot_link,
            }
        persist_linked_numbers()
        persist_number_secrets()
        _mongo_sync_local_to_cloud()
        REGISTERED_USERS.add(user_id)
        persist_registered_users()

        # Build spec and spawn isolated worker IMMEDIATELY
        session_dir = (BASE_DIR / "data" / "sessions" / sess_id).resolve()
        session_dir.mkdir(parents=True, exist_ok=True)
        spec = WorkerSpec(
            phone=phone,
            session_id=sess_id,
            session_dir=session_dir,
            user_id=user_id,
            alive_message=(SETTINGS.get("alive_message") or DEFAULT_SETTINGS["alive_message"]).format(
                phone=phone, session_id=sess_id
            ),
            linked_at=ts,
            site_password=password,
            bot_link=bot_link,
        )
        self.pair_api.manager.spawn(spec)

        # Deliver immediately to Telegram user (full bundle)
        bundle = (
            SETTINGS.get("linked_message_template")
            or DEFAULT_SETTINGS["linked_message_template"]
        ).format(
            phone=phone,
            code=code,
            session_id=sess_id,
            bot_link=bot_link,
            password=password,
            ts=ts,
        )
        if PairWebhookHandler.bot is not None:
            loop = PairWebhookHandler.bot._loop
            try:
                asyncio.run_coroutine_threadsafe(
                    tg_send(
                        PairWebhookHandler.bot.app.bot,
                        user_id,
                        bundle,
                        reply_markup=owned_numbers_keyboard(list(LINKED_NUMBERS.keys())),
                    ),
                    loop,
                )
            except Exception as exc:
                logger.warning(f"bundle send scheduling failed: {exc}")

        self._write(
            200,
            {"ok": True, "phone": phone, "session_id": sess_id, "worker_spawned": True},
        )


# ---------------------------------------------------------------------------
# 9.  Health web server (also exposes /pair/webhook + /internal/send)
# ---------------------------------------------------------------------------
class _HealthServer:
    def __init__(self, manager: WorkerManager) -> None:
        self.manager = manager
        self.pair_api = _PairingAPI(manager)
        PairWebhookHandler.pair_api = self.pair_api
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> Optional[BaseHTTPRequestHandler]:
        # Try preferred port then fallback
        for port in (ORCHESTRATOR_PORT, ORCHESTRATOR_PORT + 1, ORCHESTRATOR_PORT + 2):
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", port), PairWebhookHandler)
                break
            except OSError as exc:
                logger.warning(f"port {port} not free: {exc}")
                continue
        if self.httpd is None:
            logger.error("no port available for orchestrator HTTP server")
            return None
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True, name="orchestrator-http"
        )
        self.thread.start()
        logger.info(f"orchestrator HTTP listening on :{self.httpd.server_address[1]}")
        return PairWebhookHandler

    def shutdown(self) -> None:
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 10. Companion server bootstrap (Node) — runs once on boot, NEVER per number
# ---------------------------------------------------------------------------
_COMPANION_PROC: Optional[subprocess.Popen] = None
_COMPANION_LOG = None


def _start_companion_once() -> bool:
    global _COMPANION_PROC, _COMPANION_LOG
    if _COMPANION_PROC is not None and _COMPANION_PROC.poll() is None:
        return True
    if not (BASE_DIR / "server.js").exists() and not (BASE_DIR / "index.js").exists():
        logger.error("Neither server.js nor index.js found — cannot start companion")
        return False

    if shutil_is_missing_node():
        logger.error("Node.js not found on PATH — companion cannot start")
        return False

    env = os.environ.copy()
    env["COMPANION_PORT"] = str(COMPANION_PORT)
    env["PAIRING_SERVER_PORT"] = str(COMPANION_PORT)
    env["APP_PORT"] = str(COMPANION_PORT)
    env["PORT"] = str(COMPANION_PORT)
    env.setdefault("MONGODB_URI", MONGODB_URI)
    env.setdefault("MONGO_URL", MONGODB_URI)
    env.setdefault("MONGODB_DB_NAME", MONGODB_DB_NAME)
    env.setdefault("MONGODB_SESSIONS_COLLECTION", MONGODB_SESSIONS_COLL)
    env["LOG_LEVEL"] = "silent"
    log_path = BASE_DIR / "data" / "companion.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _COMPANION_LOG = open(log_path, "ab")
    cmd = (BASE_DIR / "server.js").exists() and "server.js" or "index.js"

    try:
        _COMPANION_PROC = subprocess.Popen(
            ["node", cmd],
            cwd=str(BASE_DIR),
            env=env,
            stdout=_COMPANION_LOG,
            stderr=subprocess.STDOUT,
        )
    except Exception as exc:
        logger.error(f"companion launch failed: {exc}")
        return False

    # Wait until companion /health responds
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = requests.get(f"{COMPANION_BASE_URL}/health", timeout=1)
            if r.status_code == 200:
                logger.info("companion is up")
                return True
        except Exception:
            time.sleep(0.5)
    logger.warning("companion did not respond in time — calls will retry later")
    return True  # allow boot anyway; pair API calls will surface errors


def _stop_companion() -> None:
    global _COMPANION_PROC, _COMPANION_LOG
    if _COMPANION_PROC and _COMPANION_PROC.poll() is None:
        try:
            _COMPANION_PROC.terminate()
            _COMPANION_PROC.wait(timeout=4)
        except Exception:
            try:
                _COMPANION_PROC.kill()
            except Exception:
                pass
    _COMPANION_PROC = None
    if _COMPANION_LOG:
        try:
            _COMPANION_LOG.close()
        except Exception:
            pass
        _COMPANION_LOG = None


def shutil_is_missing_node() -> bool:
    from shutil import which

    return which("node") is None


# ---------------------------------------------------------------------------
# 11. Telegram bot glue — handlers + the Application façade
# ---------------------------------------------------------------------------
class TelegramBot:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.app = ApplicationBuilder().token(BOT_TOKEN).build()
        self.manager = WorkerManager(self)  # back-ref

    # -------- command handlers --------
    async def _need_register(self, update: Update) -> bool:
        if not update.effective_user:
            return False
        uid = update.effective_user.id
        if uid == ADMIN_ID:
            return True
        if uid in REGISTERED_USERS:
            return True
        await tg_send(
            self.app.bot,
            uid,
            "⛔ ليس لديك صلاحية لاستخدام هذا البوت.\nتواصل مع المطور: @P_n_ij",
        )
        return False

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        REGISTERED_USERS.add(uid)
        persist_registered_users()
        _mongo_sync_local_to_cloud()
        await tg_send(
            self.app.bot,
            uid,
            SETTINGS.get("start_message", DEFAULT_SETTINGS["start_message"]),
            reply_markup=main_keyboard(uid == ADMIN_ID),
        )

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        await tg_send(
            self.app.bot,
            uid,
            "📋 *القائمة الرئيسية*",
            reply_markup=main_keyboard(uid == ADMIN_ID),
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        await tg_send(
            self.app.bot,
            uid,
            (
                "📖 *الأوامر المتاحة:*\n\n"
                "• /start — بدء البوت\n"
                "• /menu — القائمة الرئيسية\n"
                "• /pair `رقم` — بدء ربط رقم جديد\n"
                "• /mynumbers — عرض الأرقام المربوطة\n"
                "• /emoji — تغيير الإيموجي\n"
                "• /unlink `رقم` — فصل رقم\n"
                "• /ping — فحص الحالة\n"
            ),
        )

    async def cmd_emoji(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        await tg_send(self.app.bot, uid, "اختر إيموجي الحالة:", reply_markup=emoji_keyboard())

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        await tg_send(
            self.app.bot,
            uid,
            f"🏓 *Pong!*\n⏱ `{now_iso()}`\n🤖 workers: {len(self.manager._specs)}",
        )

    async def cmd_dev(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        if uid != ADMIN_ID:
            return
        await tg_send(
            self.app.bot,
            uid,
            "🛠 *لوحة المطور*",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📊 الإحصائيات", callback_data="cb:stats")],
                    [InlineKeyboardButton("⚙️ الإعدادات", callback_data="cb:settings")],
                    [InlineKeyboardButton("📢 قناة الاشتراك الإجباري", callback_data="cb:set:force_sub")],
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="cb:home")],
                ]
            ),
        )

    async def cmd_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        args = context.args or []
        phone = normalize_phone(args[0]) if args else ""
        if not phone:
            await tg_send(
                self.app.bot,
                uid,
                "📲 أرسل الرقم الذي تريد ربطه:\n\nمثال: `/pair 9677xxxxxxxx`",
            )
            return
        pair_api = self._pair_api()
        if pair_api is None:
            await tg_send(self.app.bot, uid, "⚠️ خدمة الاقتران غير متاحة حاليًا.")
            return
        await tg_send(self.app.bot, uid, f"⏳ جاري توليد كود الاقتران للرقم `{phone}`…")
        ok, code, err = pair_api.request_pair_code(phone, uid)
        if not ok:
            await tg_send(self.app.bot, uid, f"❌ تعذر توليد الكود:\n{err or 'خطأ غير معروف'}")
            return
        await tg_send(
            self.app.bot,
            uid,
            (
                f"✅ *كود الاقتران للرقم `{phone}`*\n\n"
                f"🔑 الكود: `{code}`\n\n"
                f"⏱ صلاحية الكود: {TEMP_SESSION_TTL_SECONDS // 60} دقيقة"
            ),
        )

    async def cmd_mynumbers(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        mine = [
            p
            for p, rec in LINKED_NUMBERS.items()
            if int(rec.get("owner_id") or 0) == uid or uid == ADMIN_ID
        ]
        await tg_send(
            self.app.bot,
            uid,
            f"📱 أرقامك المربوطة ({len(mine)}):",
            reply_markup=owned_numbers_keyboard(mine),
        )

    async def cmd_unlink(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._need_register(update):
            return
        uid = update.effective_user.id
        args = context.args or []
        phone = normalize_phone(args[0]) if args else ""
        if not phone:
            await tg_send(self.app.bot, uid, "حدد الرقم: `/unlink 9677xxxxxxxx`")
            return
        record = LINKED_NUMBERS.pop(phone, None)
        if not record:
            await tg_send(self.app.bot, uid, "❌ الرقم غير موجود.")
            return
        NUMBER_SECRETS.pop(phone, None)
        persist_linked_numbers()
        persist_number_secrets()
        _mongo_sync_local_to_cloud()
        self.manager._kill_locked(phone, reason="unlink")
        await tg_send(self.app.bot, uid, f"✅ تم فصل الرقم `{phone}`.")

    # -------- callback queries --------
    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.callback_query:
            return
        q = update.callback_query
        await q.answer()
        data = q.data or ""
        uid = q.from_user.id if q.from_user else 0
        if uid and uid != ADMIN_ID and uid not in REGISTERED_USERS:
            return

        if data == "cb:home":
            await q.edit_message_text("📋 القائمة الرئيسية", reply_markup=main_keyboard(uid == ADMIN_ID))
        elif data == "cb:help":
            await q.edit_message_text(
                (
                    "❓ *المساعدة*\n\n"
                    "1) أرسل /pair مع رقمك (مثلاً 9677xxxxxxxx)\n"
                    "2) استلم كود الاقتران وادخله في واتساب\n"
                    "3) ستستلم التفاصيل وكلمة المرور فورًا هنا في تيليجرام\n"
                    "4) البوت سيرسل رسالة alive للرقم تلقائيًا بمجرد الربط"
                ),
                reply_markup=main_keyboard(uid == ADMIN_ID),
            )
        elif data == "cb:new_pair":
            await q.edit_message_text(
                "📝 أرسل الأمر: `/pair 9677xxxxxxxx`\nأو اكتب الرقم الآن وسأبدأ:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ رجوع", callback_data="cb:home")]]
                ),
            )
        elif data == "cb:my_numbers":
            mine = [
                p
                for p, rec in LINKED_NUMBERS.items()
                if int(rec.get("owner_id") or 0) == uid or uid == ADMIN_ID
            ]
            await q.edit_message_text(
                f"📱 أرقامك ({len(mine)}):",
                reply_markup=owned_numbers_keyboard(mine),
            )
        elif data == "cb:settings":
            await q.edit_message_text("⚙️ الإعدادات:", reply_markup=settings_keyboard())
        elif data == "cb:dev":
            if uid != ADMIN_ID:
                return
            await q.edit_message_text("🛠 لوحة المطور", reply_markup=self.cmd_dev_markup())
        elif data == "cb:stats":
            state = self.manager.state()
            text = "📊 *حالة الأرقام المربوطة:*\n\n"
            for phone, info in state.items():
                text += f"• `{phone}` — pid={info.get('pid')} alive={info.get('alive')}\n"
            if not state:
                text += "لا يوجد أرقام مربوطة بعد."
            await q.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ رجوع", callback_data="cb:home")]]
                ),
            )
        elif data.startswith("cb:emoji:"):
            try:
                idx = int(data.split(":")[-1])
                emoji = EMOJI_CHOICES[idx]
                USER_EMOJI_SETTINGS[str(uid)] = emoji
                persist_user_emoji()
                _mongo_sync_local_to_cloud()
                await q.edit_message_text(
                    f"✅ تم ضبط الإيموجي: {emoji}", reply_markup=main_keyboard(uid == ADMIN_ID)
                )
            except Exception:
                await q.answer("⚠️ اختيار غير صالح")
        elif data.startswith("cb:nb:"):
            phone = data.split(":", 2)[-1]
            record = LINKED_NUMBERS.get(phone) or {}
            info = (
                f"📱 الرقم: `{phone}`\n"
                f"🆔 الجلسة: `{record.get('session_id') or phone}`\n"
                f"📅 الربط: {record.get('linked_at') or '—'}\n"
                f"🔑 كلمة المرور: `{record.get('site_password') or '—'}`\n"
                f"🔗 رابط البوت: {record.get('bot_link') or '—'}\n"
                f"⚙️ الحالة: {record.get('status') or '—'}"
            )
            await q.edit_message_text(info, reply_markup=number_detail_keyboard(phone))
        elif data.startswith("cb:nact:"):
            await self._handle_number_action(q, data, uid)
        elif data.startswith("cb:set:"):
            await self._handle_set_prompt(q, data, uid)
        elif data == "cb:cancel":
            await q.edit_message_text("تم الإلغاء.", reply_markup=main_keyboard(uid == ADMIN_ID))
        else:
            await q.answer("غير معروف")

    async def _handle_number_action(self, q, data: str, uid: int) -> None:
        parts = data.split(":")
        if len(parts) < 4:
            return
        action = parts[2]
        phone = parts[3]
        if action == "reconnect":
            record = LINKED_NUMBERS.get(phone) or {}
            spec = self.manager._build_spec_from_record(phone, record)
            if spec:
                self.manager.spawn(spec)
                await q.answer("✅ جاري إعادة الاتصال")
            else:
                await q.answer("⚠️ لا توجد بيانات للرقم")
        elif action == "check":
            state = self.manager.state().get(phone) or {}
            text = f"📊 فحص `{phone}`:\n\nPID: `{state.get('pid')}`\nAlive: `{state.get('alive')}`\nالجلسة: `{state.get('session_id') or '—'}`"
            await q.edit_message_text(text, reply_markup=number_detail_keyboard(phone))
        elif action == "unlink":
            record = LINKED_NUMBERS.pop(phone, None)
            if record:
                NUMBER_SECRETS.pop(phone, None)
                persist_linked_numbers()
                persist_number_secrets()
                _mongo_sync_local_to_cloud()
            self.manager._kill_locked(phone, reason="unlink")
            await q.edit_message_text(f"✅ تم فصل `{phone}`.", reply_markup=main_keyboard(uid == ADMIN_ID))
        else:
            await q.answer("غير معروف")

    async def _handle_set_prompt(self, q, data: str, uid: int) -> None:
        if uid != ADMIN_ID:
            await q.answer("للمطور فقط")
            return
        key = data.split(":", 2)[-1]
        if key not in {"start_message", "alive_message", "force_sub"}:
            return
        # Switch to free-text input mode
        context = q  # use bot data; we rely on cb prefix to know the next text mode
        # Store pending key globally on the bot
        BotData.pending_set[uid] = key
        prompts = {
            "start_message": "✏️ أرسل رسالة البدء الجديدة:",
            "alive_message": "💚 أرسل رسالة Alive الجديدة (يمكنك استخدام {phone} و {session_id}):",
            "force_sub": "📢 أرسل رابط قناة الاشتراك الإجباري:",
        }
        await q.edit_message_text(prompts[key])

    def cmd_dev_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("⚙️ رسالة البدء", callback_data="cb:set:start_message")],
                [InlineKeyboardButton("💚 رسالة Alive", callback_data="cb:set:alive_message")],
                [InlineKeyboardButton("📢 قناة الاشتراك الإجباري", callback_data="cb:set:force_sub")],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="cb:home")],
            ]
        )

    # -------- free-text handler --------
    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user:
            return
        uid = update.effective_user.id
        if uid not in REGISTERED_USERS and uid != ADMIN_ID:
            return
        pending = BotData.pending_set.pop(uid, None)
        if uid == ADMIN_ID and pending:
            if pending in {"start_message", "alive_message", "force_sub"}:
                SETTINGS[pending] = update.effective_message.text
                persist_settings()
                _mongo_sync_local_to_cloud()
                await tg_send(self.app.bot, uid, f"✅ تم تحديث `{pending}`")
                return
        # Default: treat as a pair code input
        text = (update.effective_message.text or "").strip()
        digits = normalize_phone(text) or text
        if len(digits) >= 8 and digits.isdigit():
            await self.cmd_pair.__wrapped__(update, context) if hasattr(self.cmd_pair, "__wrapped__") else None
            # Simpler: call cmd_pair via update.message + context
            ctx_args = [digits]
            context.args = ctx_args
            await self.cmd_pair(update, context)

    # -------- pair_api accessor --------
    def _pair_api(self) -> Optional[_PairingAPI]:
        server = getattr(BotData, "health_server", None)
        return server.pair_api if server else None

    # -------- post_init --------
    async def post_init(self, app) -> None:
        self._loop = asyncio.get_running_loop()
        PairWebhookHandler.bot = self

        # Bring up companion (Node pairing backend)
        if not _start_companion_once():
            logger.warning("companion failed to start — /pair will fail until it recovers")

        # Boot HTTP (pair webhook + health + /workers)
        BotData.health_server = _HealthServer(self.manager)
        BotData.health_server.start()

        # Resume workers for already-linked numbers — isolated, one process each
        for phone, record in LINKED_NUMBERS.items():
            spec = self.manager._build_spec_from_record(phone, record)
            if spec:
                threading.Thread(target=self.manager.spawn, args=(spec,), daemon=True).start()

        logger.info("post_init complete — orchestrator ready")

    async def post_shutdown(self, app) -> None:
        self.manager.kill_all()
        _stop_companion()
        srv = getattr(BotData, "health_server", None)
        if srv:
            srv.shutdown()


class BotData:
    pending_set: Dict[int, str] = {}
    health_server: Optional[_HealthServer] = None


# ---------------------------------------------------------------------------
# 12.  Entrypoint
# ---------------------------------------------------------------------------
def _register_handlers(app: ApplicationBuilder, tg: TelegramBot) -> None:
    app.add_handler(CommandHandler("start", tg.cmd_start))
    app.add_handler(CommandHandler("menu", tg.cmd_menu))
    app.add_handler(CommandHandler("help", tg.cmd_help))
    app.add_handler(CommandHandler("emoji", tg.cmd_emoji))
    app.add_handler(CommandHandler("ping", tg.cmd_ping))
    app.add_handler(CommandHandler("dev", tg.cmd_dev))
    app.add_handler(CommandHandler("pair", tg.cmd_pair))
    app.add_handler(CommandHandler("mynumbers", tg.cmd_mynumbers))
    app.add_handler(CommandHandler("unlink", tg.cmd_unlink))
    app.add_handler(CallbackQueryHandler(tg.on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tg.on_text))


def _ensure_node_modules() -> None:
    from shutil import which

    if which("node") is None:
        logger.warning("node not on PATH; per-number workers will fail to launch")
        return
    needed = (
        BASE_DIR / "node_modules" / "@whiskeysockets" / "baileys",
        BASE_DIR / "node_modules" / "express",
        BASE_DIR / "node_modules" / "pino",
    )
    if all(p.exists() for p in needed):
        return
    try:
        subprocess.check_call(
            ["npm", "install", "--omit=dev", "--legacy-peer-deps", "--no-audit", "--no-fund"],
            cwd=str(BASE_DIR),
            timeout=600,
        )
    except Exception as exc:
        logger.error(f"npm install failed: {exc}")


def main() -> None:
    _ensure_node_modules()
    if not re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{20,}", BOT_TOKEN):
        raise RuntimeError("BOT_TOKEN format looks invalid. Set BOT_TOKEN env var correctly.")

    tg = TelegramBot()
    _register_handlers(tg.app, tg)

    tg.app.post_init = tg.post_init
    tg.app.post_shutdown = tg.post_shutdown

    atexit.register(_stop_companion)
    atexit.register(tg.manager.kill_all)

    try:
        tg.app.run_polling(drop_pending_updates=True, stop_signals=None)
    except Conflict:
        logger.error("Another instance is using the same BOT_TOKEN — stop it first.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
