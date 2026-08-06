"""وحدة الأدوات المساعدة (محولة من lib/myfunc.js + lib/index.js)
توفر دوال مساعدة شائعة: قراءة JSON، حفظ JSON، تطبيع الأرقام،
التحقق من الحظر، إدارة قائمة السودو، والتحقق من المالك.
"""
from __future__ import annotations
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ============================ JSON helpers ============================
def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return default
        return json.loads(text)
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[utils] failed writing {path}: {exc}")


# ============================ Banned ============================
BANNED_PATH = DATA_DIR / "banned.json"


def load_banned() -> List[str]:
    return _read_json(BANNED_PATH, [])


def save_banned(values: Iterable[str]) -> None:
    _write_json(BANNED_PATH, list(values))


def is_banned(user_id: str) -> bool:
    return str(user_id) in [str(x) for x in load_banned()]


def add_ban(user_id: str) -> bool:
    current = [str(x) for x in load_banned()]
    if str(user_id) in current:
        return False
    current.append(str(user_id))
    save_banned(current)
    return True


def remove_ban(user_id: str) -> bool:
    current = [str(x) for x in load_banned()]
    target = str(user_id)
    if target not in current:
        return False
    current.remove(target)
    save_banned(current)
    return True


# ============================ Owner ============================
OWNER_PATH = DATA_DIR / "owner.json"


def load_owner() -> List[str]:
    return _read_json(OWNER_PATH, [])


def save_owner(values: Iterable[str]) -> None:
    _write_json(OWNER_PATH, list(values))


# ============================ User/Group Data ============================
UGDATA_PATH = DATA_DIR / "userGroupData.json"

DEFAULT_UGDATA: Dict[str, Any] = {
    "users": [],
    "groups": [],
    "antilink": {},
    "antitag": {},
    "antibadword": {},
    "warnings": {},
    "sudo": [],
    "welcome": {},
    "goodbye": {},
    "chatbot": {},
    "autoReaction": False,
    "messageCount": {},
}


def ensure_ugdata_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    for key, default in DEFAULT_UGDATA.items():
        if key not in data:
            data[key] = default
    return data


def load_ugdata() -> Dict[str, Any]:
    data = _read_json(UGDATA_PATH, {})
    return ensure_ugdata_keys(data)


def save_ugdata(data: Dict[str, Any]) -> None:
    ensure_ugdata_keys(data)
    _write_json(UGDATA_PATH, data)


# ============================ Sudo ============================
def is_sudo(user_id: str) -> bool:
    data = load_ugdata()
    sudo_list = [str(x) for x in data.get("sudo", []) or []]
    return str(user_id) in sudo_list


def add_sudo(user_jid: str) -> bool:
    data = load_ugdata()
    lst = [str(x) for x in data.get("sudo", []) or []]
    if str(user_jid) not in lst:
        lst.append(str(user_jid))
        data["sudo"] = lst
        save_ugdata(data)
    return True


def remove_sudo(user_jid: str) -> bool:
    data = load_ugdata()
    lst = [str(x) for x in data.get("sudo", []) or []]
    target = str(user_jid)
    if target in lst:
        lst.remove(target)
        data["sudo"] = lst
        save_ugdata(data)
    return True


def get_sudo_list() -> List[str]:
    return [str(x) for x in load_ugdata().get("sudo", []) or []]


# ============================ Owners ============================
def is_owner(user_id: str) -> bool:
    target = re.sub(r"\D", "", str(user_id) or "")
    if not target:
        return False
    owners = [re.sub(r"\D", "", str(x)) for x in load_owner() if x]
    if target in owners:
        return True
    from config import OWNER_NUMBER
    return target == re.sub(r"\D", "", str(OWNER_NUMBER))


def is_owner_or_sudo(user_id: str) -> bool:
    return is_owner(user_id) or is_sudo(user_id)


# ============================ Antilink ============================
def set_antilink(group_id: str, enabled: bool, action: str = "delete") -> bool:
    data = load_ugdata()
    data.setdefault("antilink", {})[group_id] = {
        "enabled": bool(enabled),
        "action": action or "delete",
    }
    save_ugdata(data)
    return True


def get_antilink(group_id: str) -> Optional[Dict[str, Any]]:
    data = load_ugdata()
    val = data.get("antilink", {}).get(group_id)
    return val if val and val.get("enabled") else None


def remove_antilink(group_id: str) -> bool:
    data = load_ugdata()
    if group_id in data.get("antilink", {}):
        del data["antilink"][group_id]
        save_ugdata(data)
    return True


# ============================ Antitag ============================
def set_antitag(group_id: str, enabled: bool, action: str = "delete") -> bool:
    data = load_ugdata()
    data.setdefault("antitag", {})[group_id] = {
        "enabled": bool(enabled),
        "action": action or "delete",
    }
    save_ugdata(data)
    return True


def get_antitag(group_id: str) -> Optional[Dict[str, Any]]:
    data = load_ugdata()
    val = data.get("antitag", {}).get(group_id)
    return val if val and val.get("enabled") else None


def remove_antitag(group_id: str) -> bool:
    data = load_ugdata()
    if group_id in data.get("antitag", {}):
        del data["antitag"][group_id]
        save_ugdata(data)
    return True


# ============================ Antibadword ============================
def set_antibadword(group_id: str, enabled: bool, action: str = "delete", words: Optional[List[str]] = None) -> bool:
    data = load_ugdata()
    data.setdefault("antibadword", {})[group_id] = {
        "enabled": bool(enabled),
        "action": action or "delete",
        "words": words or data.get("antibadword", {}).get(group_id, {}).get("words", []),
    }
    save_ugdata(data)
    return True


def get_antibadword(group_id: str) -> Optional[Dict[str, Any]]:
    data = load_ugdata()
    val = data.get("antibadword", {}).get(group_id)
    return val if val and val.get("enabled") else None


def remove_antibadword(group_id: str) -> bool:
    data = load_ugdata()
    if group_id in data.get("antibadword", {}):
        del data["antibadword"][group_id]
        save_ugdata(data)
    return True


# ============================ Warnings ============================
def increment_warning(group_id: str, user_id: str) -> int:
    data = load_ugdata()
    warnings = data.setdefault("warnings", {})
    grp = warnings.setdefault(group_id, {})
    grp[user_id] = int(grp.get(user_id, 0)) + 1
    save_ugdata(data)
    return grp[user_id]


def reset_warning(group_id: str, user_id: str) -> bool:
    data = load_ugdata()
    if group_id in data.get("warnings", {}) and user_id in data["warnings"][group_id]:
        data["warnings"][group_id][user_id] = 0
        save_ugdata(data)
    return True


def get_warnings(group_id: str, user_id: str) -> int:
    return int(load_ugdata().get("warnings", {}).get(group_id, {}).get(user_id, 0))


# ============================ Welcome / Goodbye ============================
WELCOME_DEFAULT = (
    "╔═⚔️ WELCOME ⚔️═╗\n"
    "║ 🛡️ User: {user}\n"
    "║ 🏰 Kingdom: {group}\n"
    "╠═══════════════╣\n"
    "║ 📜 Message:\n"
    "║ {description}\n"
    "╚═══════════════╝"
)
GOODBYE_DEFAULT = (
    "╔═⚔️ GOODBYE ⚔️═╗\n"
    "║ 🛡️ User: {user}\n"
    "║ 🏰 Kingdom: {group}\n"
    "╠═══════════════╣\n"
    "║ ⚰️ We will never miss you!\n"
    "╚═══════════════╝"
)


def set_welcome(group_id: str, enabled: bool, message: Optional[str] = None) -> bool:
    data = load_ugdata()
    data.setdefault("welcome", {})[group_id] = {
        "enabled": bool(enabled),
        "message": message or WELCOME_DEFAULT,
        "channelId": "120363161513685998@newsletter",
    }
    save_ugdata(data)
    return True


def remove_welcome(group_id: str) -> bool:
    data = load_ugdata()
    if group_id in data.get("welcome", {}):
        del data["welcome"][group_id]
        save_ugdata(data)
    return True


def is_welcome_on(group_id: str) -> bool:
    data = load_ugdata()
    val = data.get("welcome", {}).get(group_id)
    return bool(val and val.get("enabled"))


def get_welcome_message(group_id: str) -> Optional[str]:
    val = load_ugdata().get("welcome", {}).get(group_id)
    return val.get("message") if val else None


def set_goodbye(group_id: str, enabled: bool, message: Optional[str] = None) -> bool:
    data = load_ugdata()
    data.setdefault("goodbye", {})[group_id] = {
        "enabled": bool(enabled),
        "message": message or GOODBYE_DEFAULT,
        "channelId": "120363161513685998@newsletter",
    }
    save_ugdata(data)
    return True


def remove_goodbye(group_id: str) -> bool:
    data = load_ugdata()
    if group_id in data.get("goodbye", {}):
        del data["goodbye"][group_id]
        save_ugdata(data)
    return True


def is_goodbye_on(group_id: str) -> bool:
    data = load_ugdata()
    val = data.get("goodbye", {}).get(group_id)
    return bool(val and val.get("enabled"))


def get_goodbye_message(group_id: str) -> Optional[str]:
    val = load_ugdata().get("goodbye", {}).get(group_id)
    return val.get("message") if val else None


# ============================ Chatbot ============================
def set_chatbot(group_id: str, enabled: bool) -> bool:
    data = load_ugdata()
    data.setdefault("chatbot", {})[group_id] = {"enabled": bool(enabled)}
    save_ugdata(data)
    return True


def get_chatbot(group_id: str) -> Optional[Dict[str, Any]]:
    return load_ugdata().get("chatbot", {}).get(group_id)


def remove_chatbot(group_id: str) -> bool:
    data = load_ugdata()
    if group_id in data.get("chatbot", {}):
        del data["chatbot"][group_id]
        save_ugdata(data)
    return True


# ============================ Message Counter ============================
def increment_message_count(chat_id: str, user_id: str) -> int:
    data = load_ugdata()
    counts = data.setdefault("messageCount", {})
    chat = counts.setdefault(chat_id, {})
    chat[user_id] = int(chat.get(user_id, 0)) + 1
    save_ugdata(data)
    return chat[user_id]


def top_members(chat_id: str, limit: int = 10) -> List[Tuple[str, int]]:
    chat = load_ugdata().get("messageCount", {}).get(chat_id, {})
    sorted_items = sorted(chat.items(), key=lambda kv: int(kv[1]), reverse=True)
    return sorted_items[:limit]


# ============================ Misc helpers ============================
_LINK_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_BAD_RE = re.compile(r"\b(idiot|stupid|fuck|dumb|shit)\b", re.IGNORECASE)


def detect_links(text: str) -> bool:
    return bool(_LINK_RE.search(text or ""))


def detect_bad_words(text: str, extra_words: Optional[List[str]] = None) -> bool:
    if not text:
        return False
    if extra_words:
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(w) for w in extra_words) + r")\b", re.IGNORECASE
        )
        return bool(pattern.search(text))
    return bool(_BAD_RE.search(text))


def format_duration(seconds: int) -> str:
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def now_ts() -> int:
    return int(time.time())


# ============================ Random helpers ============================
def get_random_item(items):
    """اختيار عنصر عشوائي من قائمة."""
    if not items:
        return ""
    return items[int(time.time()) % len(items)]


def hrand(lo: int, hi: int) -> int:
    """رقم عشوائي بين lo و hi."""
    import random as _r
    return _r.randint(int(lo), int(hi))


def hchoice(items):
    """اختيار عنصر عشوائي."""
    import random as _r
    if not items:
        return None
    return _r.choice(list(items))


def simple_translate(text: str, target: str) -> str:
    """ترجمة بسيطة تستخدم deep-translator إن توفّر، وإلا إعادة النص كما هو."""
    target = (target or "en").lower()
    try:
        from deep_translator import GoogleTranslator  # type: ignore
        translation = GoogleTranslator(source="auto", target=target).translate(text or "")
        return translation or text
    except Exception:
        return text
