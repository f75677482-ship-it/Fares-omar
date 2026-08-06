"""bot.py
البوت الرئيسي الموحد - master entry point.
هذا الملف هو نتاج دمج كل الملفات الموجودة في المشروع الأصلي إلى ملف واحد
يعمل على تيليجرام (طبقا لـ requirements.txt الخاص بالمشروع).
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import config  # الإعدادات المركزية
from lib import utils as U

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger("knight-bot")


def log(msg: str) -> None:
    LOGGER.info(msg)


# -----------------------------------------------------------------------------
# قاموس الأوامر المستعار (COMMAND_ALIASES + DISPLAY_COMMAND_ALIASES) كما في main.js
# -----------------------------------------------------------------------------
COMMAND_ALIASES: Dict[str, List[str]] = {
    "help": ["الاوامر", "الأوامر", "اوامر", "مساعدة", "قائمة", "منيو"],
    "menu": ["المنيو"],
    "alive": ["حي", "شغال", "فحص"],
    "ping": ["بنج", "سرعة"],
    "owner": ["المالك", "مطور", "المطور"],
    "tts": ["تكلم", "صوت"],
    "ban": ["حظر"],
    "unban": ["فكالحظر", "فك_الحظر", "الغاءالحظر", "إلغاءالحظر"],
    "promote": ["ترقية"],
    "demote": ["تنزيل"],
    "mute": ["كتم"],
    "unmute": ["فكالكتم", "فك_الكتم"],
    "delete": ["حذف"],
    "del": ["مسح"],
    "sticker": ["ستيكر", "ملصق"],
    "simage": ["صورةالملصق", "صورة_الملصق"],
    "attp": ["ملصقنص", "ملصق_نص"],
    "settings": ["الاعدادات", "الإعدادات"],
    "mode": ["الوضع"],
    "anticall": ["منعالاتصال", "منع_الاتصال"],
    "pmblocker": ["منعالخاص", "منع_الخاص"],
    "tagall": ["منشنالكل", "منشن_الكل"],
    "tagnotadmin": ["منشنالاعضاء", "منشن_الاعضاء"],
    "hidetag": ["منشنمخفي", "منشن_مخفي"],
    "tag": ["منشن", "تاق"],
    "antilink": ["منعالروابط", "منع_الروابط"],
    "antitag": ["منعالمنشن", "منع_المنشن"],
    "antibadword": ["منعالسب", "منع_السب"],
    "weather": ["طقس"],
    "news": ["اخبار", "أخبار"],
    "tictactoe": ["اكساو", "اكس_او", "xo"],
    "guess": ["خمن"],
    "trivia": ["سؤال"],
    "answer": ["اجابة", "إجابة"],
    "warnings": ["تحذيرات"],
    "warn": ["تحذير"],
    "lyrics": ["كلمات"],
    "joke": ["نكتة"],
    "quote": ["اقتباس"],
    "fact": ["معلومة"],
    "kick": ["طرد"],
    "groupinfo": ["معلوماتالقروب", "معلومات_القروب"],
    "staff": ["المشرفين", "الادمنية", "الأدمنية"],
    "chatbot": ["شاتبوت", "دردشة"],
    "resetlink": ["اعادةالرابط", "إعادةالرابط", "اعادة_الرابط", "إعادة_الرابط"],
    "welcome": ["ترحيب"],
    "goodbye": ["وداع"],
    "clear": ["تنظيف"],
    "github": ["السورس"],
    "git": ["كود"],
    "repo": ["المستودع"],
    "sc": ["شفرة"],
    "take": ["اخذ", "أخذ"],
    "flirt": ["مغازلة"],
    "character": ["شخصية"],
    "wasted": ["هلاك"],
    "ship": ["شيب"],
    "url": ["رابط"],
    "emojimix": ["دمجايموجي", "دمج_ايموجي"],
    "tgsticker": ["ملصقاتتيليجرام", "ملصقات_تيليجرام"],
    "vv": ["فتح"],
    "clearsession": ["تنظيفالجلسات", "تنظيف_الجلسات"],
    "autostatus": ["حالةتلقائية", "حالة_تلقائية"],
    "simp": ["سمب"],
    "truth": ["صراحة"],
    "dare": ["تحدي"],
    "setpp": ["صورةالبوت", "صورة_البوت"],
    "setgdesc": ["وصفالقروب", "وصف_القروب"],
    "setgname": ["اسمالقروب", "اسم_القروب"],
    "setgpp": ["صورةالقروب", "صورة_القروب"],
    "instagram": ["انستا", "إنستا"],
    "igs": ["ستوري"],
    "igsc": ["انستاميديا", "إنستاميديا"],
    "facebook": ["فيسبوك"],
    "spotify": ["سبوتيفاي"],
    "play": ["شغل"],
    "song": ["اغنية", "أغنية"],
    "video": ["فيديو"],
    "tiktok": ["تيك", "تيكتوك", "تيك_توك"],
    "ai": ["ذكاء"],
    "gpt": ["جيبيتي", "جي_بي_تي"],
    "gemini": ["جيميني"],
    "translate": ["ترجمة"],
    "trt": ["ترجم"],
    "ss": ["صورةموقع", "صورة_موقع"],
    "autoreact": ["تفاعلتلقائي", "تفاعل_تلقائي"],
    "areact": ["تفاعل"],
    "sudo": ["سودو"],
    "goodnight": ["تصبحتعلىخير", "تصبح_على_خير"],
    "shayari": ["شعر"],
    "roseday": ["ورد"],
    "imagine": ["تخيل"],
    "flux": ["فلوكس"],
    "jid": ["معرف"],
    "autotyping": ["كتابةتلقائية", "كتابة_تلقائية"],
    "autoread": ["قراءةتلقائية", "قراءة_تلقائية"],
    "update": ["تحديث"],
    "removebg": ["شفاف"],
    "remini": ["تحسين"],
    "sora": ["سورا"],
    "antidelete": ["منعالحذف", "منع_الحذف"],
    "tempm": ["تنظيفالمؤقت", "تنظيف_المؤقت"],
}


def normalize_token(token: str) -> str:
    """تطبيع نص الأمر (إزالة التشكيل، توحيد الحروف العربية المتقاربة)."""
    t = (token or "").strip().lower()
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub(r"[ً-ٰٟ]", "", t)
    t = t.replace("ـ", "")
    return t


# خريطة alias (مطبّع) -> canonical command name
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canon, _aliases in COMMAND_ALIASES.items():
    ALIAS_TO_CANONICAL[_canon] = _canon
    for _alias in _aliases:
        ALIAS_TO_CANONICAL[normalize_token(_alias)] = _canon


def canonicalize(name: str) -> str:
    return ALIAS_TO_CANONICAL.get(normalize_token(name), (name or "").lower())


# -----------------------------------------------------------------------------
# معالجة الأوامر - قوائم محلية لكل لعبة
# -----------------------------------------------------------------------------
JOKES_AR = [
    "واحد بصّ على المزة، قال: وين رايحة؟ قالت: وين ما رايحة.",
    "مرة واحد اشترى حذاء من الإنترنت، طلع حذاء يمين .. ما داس فيه أحد.",
    "معلم سأل طالب: وين فلسطين؟ قال: على يمين مصر، يسار الأردن، فوق إسرائيل.",
    "مرة فهد راح المطعم، قالوا له: وش تبي؟ قال: قهوة باللبن! قالوا: حليب مكثّف؟",
]
QUOTES_AR = [
    "«لا تَحْسبنَّ أنَّ الصمتَ ضعفٌ، أحياناً الصمتُ أبلغُ رد.»",
    "«من جدّ وجد، ومن زرع حصد.»",
    "«اصبر على الأذى، فالعاقبةُ للمتّقين.»",
]
FACTS_AR = [
    "الدماغ البشري يستهلك 20% من طاقة الجسم.",
    "عسل النمل لا يفسد أبداً.",
    "قلب الحوت الزرقاء بوزن سيارة صغيرة.",
]
SHIPS_AR = [
    "أنتما مثل القهوة والهيل.. كِلتُكما تجعل حياة الآخر أطيب.",
    "بينكما كمثل الوردة والعطر، كلما اقتربت زاد العطر.",
    "توافقكما كتوافق الشمس والقمر، جميل لكن نادر.",
]
SIMP_AR = [
    "يا قمر، أنتِ ما تدرين شو تسوين في قلبي.",
    "عينيكِ كوفيتين الصباح، ما أقدر أبدأ يومي بدونكم.",
]
STUPID_AR = [
    "تحاول تكتب بالعكس وأنت تكتب بالعكس حتى بالعكس.. غبي؟ 😜",
    "حتى بوتك ما يفهم عليك، فكيف أريد أفهمك؟ 🫠",
]
GOODNIGHT_AR = [
    "تصبح على خير يا غالي، أحلامك حلوة 🌙",
    "نوم العوافي يا رب العالمين 😴",
]
SHAYARI_AR = [
    "ما بين نجمتين وبين الغيم احتضن الليل كل ما ليالي.",
    "أحبّك ما يوفي الكلام، يكفي إنك هنا.",
]

GAMES_STATE: Dict[str, Dict[str, Any]] = {}


def help_text() -> str:
    return (
        f"╔═══════════════════╗\n"
        f"   *🤖 {config.BOT_NAME}*\n"
        f"   الإصدار: *{config.VERSION}*\n"
        f"   المطور: *{config.BOT_OWNER}*\n"
        f"╚═══════════════════╝\n\n"
        f"📜 *قائمة الأوامر* — البادئة هي *.*\n\n"
        f"*عامة*\n"
        f"• .الأوامر / .حي / .بنج / .المالك / .المعرف / .السورس\n"
        f"• .نكتة / .اقتباس / .معلومة / .كلمات / .أخبار / .طقس\n"
        f"• .ملصق / .ملصق_نص / .رابط / .صورة_موقع / .مغازلة / .شخصية\n"
        f"• .تشارلوت / .تصبح_على_خير / .شعر / .ورد\n\n"
        f"*الإدارة*\n"
        f"• .حظر / .فك_الحظر / .ترقية / .تنزيل / .كتم / .فك_الكتم\n"
        f"• .حذف / .طرد / .تحذير / .تحذيرات / .إعادة_الرابط\n"
        f"• .منع_الروابط / .منع_السب / .منع_المنشن / .شاتبوت\n"
        f"• .منشن / .منشن_الكل / .منشن_الأعضاء / .منشن_مخفي\n"
        f"• .ترحيب / .وداع / .وصف_القروب / .اسم_القروب\n\n"
        f"*المالك*\n"
        f"• .الوضع / .سودو / .الإعدادات / .منع_الاتصال / .منع_الخاص\n"
        f"• .حالة_تلقائية / .كتابة_تلقائية / .قراءة_تلقائية / .تفاعل_تلقائي\n"
        f"• .تحديث / .صورة_البوت / .تنظيف_المؤقت / .تنظيف_الجلسات\n\n"
        f"*السوشل ميديا والتحميل*\n"
        f"• .شغل / .أغنية / .فيديو / .سبوتيفاي / .إنستا / .ستوري\n"
        f"• .فيسبوك / .تيك_توك / .رابط / .شفاف / .تحسين\n\n"
        f"*الذكاء الاصطناعي*\n"
        f"• .ذكاء / .جيميني / .تخيل / .فلوكس / .سورا / .ترجمة\n\n"
        f"📥 {config.REPO_URL}"
    )


# -----------------------------------------------------------------------------
# أدوات مساعدة للكتابة عبر تيليجرام
# -----------------------------------------------------------------------------
class _Codec:
    MIN_TG_MSG = 4000

    @staticmethod
    async def send_text(bot, chat_id: int, text: str, **kw) -> None:
        if not text:
            return
        if len(text) > _Codec.MIN_TG_MSG:
            for chunk in [text[i:i + _Codec.MIN_TG_MSG] for i in range(0, len(text), _Codec.MIN_TG_MSG)]:
                await bot.send_message(chat_id=chat_id, text=chunk, **kw)
        else:
            await bot.send_message(chat_id=chat_id, text=text, **kw)


def parse_args(text: str) -> Tuple[str, List[str]]:
    parts = re.split(r"\s+", (text or "").strip(), maxsplit=1)
    if not parts or not parts[0]:
        return "", []
    return parts[0].lstrip(".").lower(), (parts[1].split() if len(parts) > 1 else [])


def format_greeting(group_id: str, user_id: str, group_name: str = "المجموعة") -> str:
    msg = U.get_welcome_message(group_id) or U.WELCOME_DEFAULT
    return msg.format(user=user_id, group=group_name, description=" ")


def format_goodbye(group_id: str, user_id: str, group_name: str = "المجموعة") -> str:
    msg = U.get_goodbye_message(group_id) or U.GOODBYE_DEFAULT
    return msg.format(user=user_id, group=group_name)


# -----------------------------------------------------------------------------
# معالج رئيسي - entry point إن تم تشغيل هذا الملف مباشرة
# -----------------------------------------------------------------------------
def main() -> int:
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        log("⚠️ TELEGRAM_BOT_TOKEN غير موجود. ضعه في settings.json أو المتغير البيئي TELEGRAM_BOT_TOKEN.")
        print("Knight-Bot: لم يتم ضبط TELEGRAM_BOT_TOKEN — الخروج.")
        return 0

    from telegram import Update, Bot
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

    async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(f"مرحباً 👋 أنا {config.BOT_NAME} — أرسل .الأوامر لاستعراض القائمة.")

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (update.message.text or "").strip()
        if not text:
            return
        if U.is_banned(update.effective_user.id):
            await update.message.reply_text("❌ أنت محظور من استخدام البوت.")
            return
        cmd, args = parse_args(text)
        cmd = canonicalize(cmd)
        if not cmd:
            return
        await dispatch(update, context, cmd, args, text)

    async def dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE, cmd: str, args: List[str], full_text: str) -> None:
        func = COMMANDS.get(cmd)
        if not func:
            return
        sender = update.effective_user.id
        if not U.is_owner_or_sudo(sender) and config.COMMAND_MODE != "public":
            await update.message.reply_text("⛔ البوت في الوضع الخاص، لا يمكنك استخدامه.")
            return
        try:
            await func(update, context, args, full_text)
        except Exception as exc:
            LOGGER.exception("command error: %s", exc)
            try:
                await update.message.reply_text("❌ حدث خطأ أثناء تنفيذ الأمر.")
            except Exception:
                pass

    async def post_init(application) -> None:
        log("Knight-Bot running.")

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log("Starting bot polling…")
    app.run_polling(drop_pending_updates=True)
    return 0


# ============================================================================
#                      تعريف الأوامر - COMMANDS map
#  يحتوي كل أمر على: اسم + alias + دالة async (update, ctx, args, full)
# ============================================================================
COMMANDS: Dict[str, Callable[[Any, Any, List[str], str], Awaitable[None]]] = {}


def _register(name: str, aliases: Optional[List[str]] = None) -> Callable:
    def deco(fn: Callable) -> Callable:
        COMMANDS[name] = fn
        if aliases:
            for a in aliases:
                COMMAND_ALIASES.setdefault(a, []).append(name)
                ALIAS_TO_CANONICAL[normalize_token(a)] = name
        return fn
    return deco


# ----- الأوامر العامة -----
COMMAND_MODE = {"value": config.COMMAND_MODE}  # قابل للتعديل في الجلسة


@_register("help")
async def cmd_help(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, help_text())


@_register("ping")
async def cmd_ping(update, ctx, args, full):
    start = time.time()
    msg = await ctx.bot.send_message(chat_id=update.effective_chat.id, text="Pong!")
    ping = int((time.time() - start) * 1000)
    uptime = U.format_duration(int(time.time() - BOT_START_TIME))
    await msg.edit_text(
        f"┏━━〔 🤖 {config.BOT_NAME} 〕━━┓\n"
        f"┃ 🚀 Ping     : {ping} ms\n"
        f"┃ ⏱️ Uptime   : {uptime}\n"
        f"┃ 🔖 Version  : v{config.VERSION}\n"
        f"┗━━━━━━━━━━━━━━━━━━━┛"
    )


@_register("alive")
async def cmd_alive(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"*🤖 البوت يعمل بنجاح!*\n\n"
        f"*الإصدار:* {config.VERSION}\n"
        f"*الحالة:* متصل\n"
        f"*الوضع:* {'عام' if COMMAND_MODE['value']=='public' else 'خاص'}\n"
        f"\n"
        f"اكتب *.الأوامر* لعرض جميع الأوامر.")


@_register("owner")
async def cmd_owner(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"👑 *المالك:* {config.BOT_OWNER}\n📱 الرقم: `{config.OWNER_NUMBER}`\n🔗 القناة: {config.CHANNEL_LINK}")


@_register("github")
async def cmd_github(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🔗 *رابط المشروع:* {config.REPO_URL}\n📜 *الوصف:* {config.description}" if hasattr(config, 'description') else f"🔗 {config.REPO_URL}")


@_register("jid")
async def cmd_jid(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🆔 معرف الدردشة: `{update.effective_chat.id}`\n👤 معرفك: `{update.effective_user.id}`")


@_register("joke")
async def cmd_joke(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"😂 {U.get_random_item(JOKES_AR)}")


@_register("quote")
async def cmd_quote(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"📜 {U.get_random_item(QUOTES_AR)}")


@_register("fact")
async def cmd_fact(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"💡 {U.get_random_item(FACTS_AR)}")


@_register("weather")
async def cmd_weather(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب اسم المدينة، مثال: `.طقس الرياض`")
        return
    city = " ".join(args)
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🌦️ جاري جلب الطقس لـ *{city}*…\n(ميزة تجريبية، اربط API الطقس لاحقًا)")


@_register("news")
async def cmd_news(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, "📰 آخر الأخبار (ميزة تجريبية، اربط API الأخبار لاحقًا)")


@_register("lyrics")
async def cmd_lyrics(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب اسم الأغنية، مثال: `.كلمات بحبك`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🎵 كلمات أغنية: {' '.join(args)} (تجريبي)")


@_register("simmer")
async def _noop(update, ctx, args, full):
    pass


@_register("simp")
async def cmd_simp(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"💗 {U.get_random_item(SIMP_AR)}")


@_register("stupid")
async def cmd_stupid(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🤪 {U.get_random_item(STUPID_AR)}")


@_register("goodnight")
async def cmd_goodnight(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🌙 {U.get_random_item(GOODNIGHT_AR)}")


@_register("shayari")
async def cmd_shayari(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"📝 {U.get_random_item(SHAYARI_AR)}")


@_register("roseday")
async def cmd_roseday(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🌹 *ورد اليوم:*\n{U.get_random_item(['الأحمر يرمز للحب','الأبيض يرمز للنقاء','الوردي يرمز للودّ'])}")


@_register("flirt")
async def cmd_flirt(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"💘 {U.get_random_item(['في عيونك شي يشدّ القلب…','ضحكتك تذوّب الصقيع.','قربك يطيب الوقت.'])}")


@_register("character")
async def cmd_character(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🧑 شخصية اليوم: *{U.get_random_item(['قائد','مساعد','مغامر','حكيم','لطيف'])}* 🌟")


@_register("wasted")
async def cmd_wasted(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, "🪦 Wasted… (تجريبي يرسم حول صورة الردود)")


@_register("ship")
async def cmd_ship(update, ctx, args, full):
    a = args[0] if len(args) > 0 else "أ"
    b = args[1] if len(args) > 1 else "ب"
    score = U.hrand(50, 99)
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"💞 *{a}* × *{b}*\nنسبة التوافق: {score}%\n{U.get_random_item(SHIPS_AR)}")


# ----- أوامر الإدارة -----
@_register("ban")
async def cmd_ban(update, ctx, args, full):
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ هذا الأمر للمالك أو السودو فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب الجات/الآيدي المطلوب حظره.")
        return
    target = args[0].lstrip("@")
    if U.add_ban(target):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"✅ تم حظر `{target}`.")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"⚠️ `{target}` محظور بالفعل.")


@_register("unban")
async def cmd_unban(update, ctx, args, full):
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ هذا الأمر للمالك أو السودو فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب الجات/الآيدي.")
        return
    target = args[0].lstrip("@")
    if U.remove_ban(target):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"✅ تم رفع الحظر عن `{target}`.")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"⚠️ `{target}` غير محظور.")


@_register("sudo")
async def cmd_sudo(update, ctx, args, full):
    if not U.is_owner(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ لمالك البوت فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            "الاستخدام: `.سودو add <آيدي>` أو `.سودو remove <آيدي>` أو `.سودو list`")
        return
    op = args[0].lower()
    if op == "list":
        users = U.get_sudo_list()
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            "👑 السوادو: " + (", ".join(f"`{u}`" for u in users) if users else "لا أحد"))
        return
    if len(args) < 2:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "حدد الآيدي بعد add/remove.")
        return
    target = args[1].lstrip("@")
    if op == "add":
        U.add_sudo(target)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"✅ تم إضافة `{target}` للسوادو.")
    elif op == "remove":
        U.remove_sudo(target)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"✅ تم إزالة `{target}` من السوادو.")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "عملية غير معروفة.")


@_register("mode")
async def cmd_mode(update, ctx, args, full):
    if not U.is_owner(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ لمالك البوت فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            f"وضع البوت الحالي: *{'عام' if COMMAND_MODE['value']=='public' else 'خاص'}*\n"
            "الاستخدام: `.الوضع public` أو `.الوضع private`")
        return
    new_mode = canonicalize(args[0])
    if new_mode in ("public", "private"):
        COMMAND_MODE["value"] = new_mode
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            f"✅ تم تغيير وضع البوت إلى *{'عام' if new_mode=='public' else 'خاص'}*")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "وضع غير معروف. استخدم public أو private")


@_register("settings")
async def cmd_settings(update, ctx, args, full):
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك أو السوادو فقط.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"⚙️ *الإعدادات الحالية*\n"
        f"• الوضع: {'عام' if COMMAND_MODE['value']=='public' else 'خاص'}\n"
        f"• الإصدار: {config.VERSION}\n"
        f"• إيموجي التفاعل: ❤️\n"
        f"• قراءة تلقائية: مفعّلة\n"
        f"• كتابة تلقائية: معطّلة\n"
        f"• تفاعل تلقائي: {'مفعّل' if U.load_ugdata().get('autoReaction') else 'معطّل'}")


@_register("welcome")
async def cmd_welcome(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يعمل فقط داخل المجموعات.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            "الاستخدام: `.ترحيب on` أو `.ترحيب off` أو `.ترحيب set <النص>`")
        return
    op = canonicalize(args[0])
    gid = str(update.effective_chat.id)
    if op in ("on", "enable"):
        U.set_welcome(gid, True)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ تم تفعيل الترحيب.")
    elif op in ("off", "disable"):
        U.remove_welcome(gid)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ تم إيقاف الترحيب.")
    elif op == "set" and len(args) > 1:
        U.set_welcome(gid, True, " ".join(args[1:]))
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ تم ضبط رسالة الترحيب.")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "أمر غير معروف.")


@_register("goodbye")
async def cmd_goodbye(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يعمل فقط داخل المجموعات.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            "الاستخدام: `.وداع on` أو `.وداع off`")
        return
    op = canonicalize(args[0])
    gid = str(update.effective_chat.id)
    if op in ("on", "enable"):
        U.set_goodbye(gid, True)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ تم تفعيل رسالة الوداع.")
    elif op in ("off", "disable"):
        U.remove_goodbye(gid)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ تم إيقاف رسالة الوداع.")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "أمر غير معروف.")


@_register("chatbot")
async def cmd_chatbot(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يعمل فقط داخل المجموعات.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "الاستخدام: `.شاتبوت on` أو `.شاتبوت off`")
        return
    op = canonicalize(args[0])
    gid = str(update.effective_chat.id)
    if op in ("on", "enable"):
        U.set_chatbot(gid, True)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ الشاتبوت مفعّل في هذه المجموعة.")
    elif op in ("off", "disable"):
        U.remove_chatbot(gid)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ الشاتبوت معطّل في هذه المجموعة.")


@_register("antitag")
async def cmd_antitag(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يعمل فقط داخل المجموعات.")
        return
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك أو السوادو فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "الاستخدام: `.منع_المنشن on` أو `.منع_المنشن off`")
        return
    op = canonicalize(args[0])
    gid = str(update.effective_chat.id)
    if op in ("on", "enable"):
        U.set_antitag(gid, True, args[1] if len(args) > 1 else "delete")
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ تم تفعيل منع المنشن.")
    elif op in ("off", "disable"):
        U.remove_antitag(gid)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ تم إيقاف منع المنشن.")


@_register("antilink")
async def cmd_antilink(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يعمل فقط داخل المجموعات.")
        return
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك أو السوادو فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "الاستخدام: `.منع_الروابط on` أو `.منع_الروابط off`")
        return
    op = canonicalize(args[0])
    gid = str(update.effective_chat.id)
    if op in ("on", "enable"):
        U.set_antilink(gid, True, args[1] if len(args) > 1 else "delete")
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ تم تفعيل منع الروابط.")
    elif op in ("off", "disable"):
        U.remove_antilink(gid)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ تم إيقاف منع الروابط.")


@_register("antibadword")
async def cmd_antibadword(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يعمل فقط داخل المجموعات.")
        return
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك أو السوادو فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "الاستخدام: `.منع_السب on` أو `.منع_السب off` أو `.منع_السب add/remove <كلمة>`")
        return
    op = canonicalize(args[0])
    gid = str(update.effective_chat.id)
    if op in ("on", "enable"):
        U.set_antibadword(gid, True, args[1] if len(args) > 1 else "delete")
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ تم تفعيل منع السب.")
    elif op in ("off", "disable"):
        U.remove_antibadword(gid)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ تم إيقاف منع السب.")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "أمر غير معروف.")


# ----- أوامر ألعاب -----
@_register("tictactoe")
async def cmd_tictactoe(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يجب أن تكون في مجموعة.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            "اكتب:.أكس_او @مستخدم — يلعب ضد المستخدم المذكور")
        return
    other = args[0].lstrip("@")
    board = [" "] * 9
    GAMES_STATE.setdefault("ttt", {})[update.effective_chat.id] = {"board": board, "p1": update.effective_user.id, "p2": other, "turn": "X"}
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🎮 بدأت المباراة ضد @{other}!\nاستخدم `.خمن <رقم> 1..9` لحجز المربع. اللوحة:\n1 2 3\n4 5 6\n7 8 9")


@_register("guess")
async def cmd_guess(update, ctx, args, full):
    # يستخدم للألعاب: خمن حرف (شنق) أو رقم (xo)
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب رقم أو حرف بعد الأمر.")
        return
    chat = update.effective_chat.id
    ttt = GAMES_STATE.get("ttt", {}).get(chat)
    if ttt:
        token = args[0]
        if not token.isdigit() or not (1 <= int(token) <= 9):
            await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب رقم 1..9.")
            return
        idx = int(token) - 1
        if ttt["board"][idx] != " ":
            await _Codec.send_text(ctx.bot, update.effective_chat.id, "❌ المربع محجوز.")
            return
        ttt["board"][idx] = "X" if ttt["turn"] == "X" else "O"
        # فحص فوز مبسط
        b = ttt["board"]
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        winner = None
        for a,b2,c in wins:
            if b[a] == b[b2] == b[c] != " ":
                winner = b[a]
        await _Codec.send_text(ctx.bot, update.effective_chat.id,
            f"لوحة:\n{b[0]} {b[1]} {b[2]}\n{b[3]} {b[4]} {b[5]}\n{b[6]} {b[7]} {b[8]}\nالدور التالي: "
            f"{'O' if ttt['turn']=='X' else 'X'}"
        )
        if winner or " " not in b:
            await _Codec.send_text(ctx.bot, update.effective_chat.id, f"{'🏆 ' + winner + ' فاز!' if winner else '🤝 تعادل.'}")
            GAMES_STATE["ttt"].pop(chat, None)
        else:
            ttt["turn"] = "O" if ttt["turn"] == "X" else "X"
        return
    hang = GAMES_STATE.get("hangman", {}).get(chat)
    if hang and args[0].isalpha():
        letter = args[0][0].lower()
        if letter in hang["guessed"]:
            await _Codec.send_text(ctx.bot, update.effective_chat.id, "⚠️ جرّبت هذا الحرف.")
            return
        hang["guessed"].append(letter)
        if letter in hang["word"]:
            hang["hits"] += 1
            await _Codec.send_text(ctx.bot, update.effective_chat.id, f"✅ صح! الحرف `{letter}` موجود.")
        else:
            hang["misses"] += 1
            await _Codec.send_text(ctx.bot, update.effective_chat.id, f"❌ خطأ! الحرف `{letter}` غير موجود.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id, "لا توجد لعبة حالية.")


@_register("hangman")
async def cmd_hangman(update, ctx, args, full):
    if update.effective_chat.type not in ("group", "supergroup"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "يجب أن تكون في مجموعة.")
        return
    words = ["python", "knight", "bot", "sword", "shield"]
    word = U.hchoice(words)
    GAMES_STATE.setdefault("hangman", {})[update.effective_chat.id] = {"word": word, "guessed": [], "hits": 0, "misses": 0}
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🪢 لعبة الرجل المشنوق بدأت!\nالكلمة: {'_ ' * len(word)}\nاستخدم `.خمن <حرف>`")


@_register("trivia")
async def cmd_trivia(update, ctx, args, full):
    q = {"q": "ما هو أطول نهر في العالم؟", "a": "النيل"}
    GAMES_STATE.setdefault("trivia", {})[update.effective_chat.id] = q
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"❓ سؤال: {q['q']}\nاستخدم `.إجابة <النص>`")


@_register("answer")
async def cmd_answer(update, ctx, args, full):
    q = GAMES_STATE.get("trivia", {}).pop(update.effective_chat.id, None)
    if not q or not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "لا يوجد سؤال مفتوح.")
        return
    guess = " ".join(args).strip()
    if guess == q["a"]:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ إجابة صحيحة!")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"❌ خطأ. الإجابة الصحيحة: {q['a']}")


# ----- أوامر السوشل ميديا / التحميل -----
@_register("play")
async def cmd_play(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب اسم الأغنية بعد `.شغل`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🎵 جاري البحث عن: {' '.join(args)}\n(يجب ربط yt-dlp لتحميل الصوت)")


@_register("song")
async def cmd_song(update, ctx, args, full):
    return await cmd_play(update, ctx, args, full)


@_register("video")
async def cmd_video(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب اسم الفيديو بعد `.فيديو`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🎬 جاري البحث عن: {' '.join(args)}\n(يجب ربط yt-dlp لتحميل الفيديو)")


@_register("instagram")
async def cmd_instagram(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "ألصق رابط إنستغرام بعد `.إنستا`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        "📸 جاري تنزيل من إنستغرام… (ميزة تجريبية، اربط API)")


@_register("tiktok")
async def cmd_tiktok(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "ألصق رابط TikTok بعد `.تيك_توك`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        "🎵 جاري تنزيل من TikTok… (ميزة تجريبية)")


@_register("facebook")
async def cmd_facebook(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "ألصق رابط فيسبوك بعد `.فيسبوك`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        "📘 جاري تنزيل من فيسبوك… (ميزة تجريبية)")


@_register("spotify")
async def cmd_spotify(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب كلمة البحث بعد `.سبوتيفاي`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🎧 بحث Spotify: {' '.join(args)} (تجريبي)")


@_register("igs")
async def cmd_igs(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "ألصق رابط ستوري إنستغرام")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id, "📱 جاري تنزيل ستوري… (تجريبي)")


@_register("url")
async def cmd_url(update, ctx, args, full):
    if not update.message.reply_to_message:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "رد على رسالة تحتوي ميديا لاستخراج رابط مباشر.")
        return
    msg = update.message.reply_to_message
    if msg.photo:
        file_id = msg.photo[-1].file_id
        f = await ctx.bot.get_file(file_id)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🔗 رابط مباشر: {f.file_path}")
    elif msg.video or msg.document:
        target = msg.video or msg.document
        f = await ctx.bot.get_file(target.file_id)
        await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🔗 رابط مباشر: {f.file_path}")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "❌ لا توجد ميديا في الرسالة.")


@_register("sticker")
async def cmd_sticker(update, ctx, args, full):
    if not update.message.reply_to_message:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "رد على صورة أو فيديو لإنشاء ملصق.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        "🪄 ميزة الملصق تجريبية هنا، اربط مكتبة Pillow لرسم الملصقات.")


@_register("simage")
async def cmd_simage(update, ctx, args, full):
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "رد على ملصق لتحويله إلى صورة.")
        return
    sticker = update.message.reply_to_message.sticker
    f = await ctx.bot.get_file(sticker.file_id)
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🖼️ رابط الصورة: {f.file_path}")


@_register("removebg")
async def cmd_removebg(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, "🪄 إزالة الخلفية تجريبية، اربط remove.bg API لاحقًا.")


@_register("remini")
async def cmd_remini(update, ctx, args, full):
    await _Codec.send_text(ctx.bot, update.effective_chat.id, "🪄 تحسين جودة الصورة تجريبي.")


# ----- أوامر الذكاء الاصطناعي -----
@_register("imagine")
async def cmd_imagine(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب وصف الصورة بعد `.تخيل`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🎨 جاري توليد صورة… الوصف: {' '.join(args)}\n(اربط Gemini Image API لاحقًا)")


@_register("ai")
async def cmd_ai(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب سؤالك بعد `.ذكاء`")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"🤖 سؤال الذكاء: {' '.join(args)}\n(اربط Gemini/OpenAI لاحقًا)")


@_register("gemini")
async def cmd_gemini(update, ctx, args, full):
    return await cmd_ai(update, ctx, args, full)


@_register("translate")
async def cmd_translate(update, ctx, args, full):
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب النص للترجمة بعد `.ترجمة`")
        return
    target = args[0]
    text = " ".join(args[1:]) if len(args) > 1 else ""
    if not text:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "اكتب مثل: `.ترجمة en مرحبا`")
        return
    trans = U.simple_translate(text, target)
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🌍 `{text}` → `{target}`:\n{trans}")


# ----- أوامر التنظيف والصيانة -----
@_register("update")
async def cmd_update(update, ctx, args, full):
    if not U.is_owner(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك فقط.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        f"📦 النسخة الحالية: {config.VERSION}\n📥 التحديث متاح على {config.REPO_URL}")


@_register("clearsession")
async def cmd_clearsession(update, ctx, args, full):
    if not U.is_owner(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك فقط.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id, "🧹 تم تنظيف الجلسات القديمة (تجريبي).")


@_register("tempm")
async def cmd_cleartmp(update, ctx, args, full):
    if not U.is_owner(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك فقط.")
        return
    count = 0
    for f in TEMP_DIR.glob("*"):
        if f.is_file():
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
    await _Codec.send_text(ctx.bot, update.effective_chat.id, f"🧹 تم حذف {count} ملف مؤقت.")


# ----- أوامر الحالة التلقائية -----
@_register("autotyping")
async def cmd_autotyping(update, ctx, args, full):
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك أو السوادو فقط.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        "✍️ ميزة كتابة تلقائية — في وضع تيليجرام هذه عادةً تفاعل طبيعي.")


@_register("autoread")
async def cmd_autoread(update, ctx, args, full):
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك أو السوادو فقط.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        "👀 ميزة قراءة تلقائية — تيليجرام يقرأ تلقائياً عند توليد رسائل.")


@_register("autostatus")
async def cmd_autostatus(update, ctx, args, full):
    if not U.is_owner_or_sudo(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك أو السوادو فقط.")
        return
    await _Codec.send_text(ctx.bot, update.effective_chat.id,
        "📜 ميزة حالة تلقائية — لا تنطبق على تيليجرام، تأكد أو الأمر هنا مجرد placeholder.")


# ----- منع الاتصال / منع الخاص / إلخ (placeholders) -----
@_register("anticall")
async def cmd_anticall(update, ctx, args, full):
    if not U.is_owner(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك فقط.")
        return
    if not args or canonicalize(args[0]) in ("on", "enable"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ منع الاتصال مفعّل.")
    else:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ منع الاتصال معطّل.")


@_register("pmblocker")
async def cmd_pmblocker(update, ctx, args, full):
    if not U.is_owner(update.effective_user.id):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ للمالك فقط.")
        return
    if not args:
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "الاستخدام: `.منع_الخاص on|off|status`")
        return
    op = canonicalize(args[0])
    if op in ("on", "enable"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "✅ منع الخاص مفعّل.")
    elif op in ("off", "disable"):
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "⛔ منع الخاص معطّل.")
    elif op == "status":
        await _Codec.send_text(ctx.bot, update.effective_chat.id, "الحالة: مفعّل (افتراضي)")


# ----- antitag detection helper (يضاف كمثال على معالجة الرسائل) -----
async def handle_chat_message(update, ctx) -> Optional[str]:
    if not update.message or not update.message.text:
        return None
    if update.effective_chat.type not in ("group", "supergroup"):
        return None
    gid = str(update.effective_chat.id)
    if U.get_antitag(gid) and update.message.entities:
        # أي منشن (mention) للمستخدمين في الكلام يُعتبر انتاع
        for ent in update.message.entities:
            if ent.type == "mention":
                if not U.is_owner_or_sudo(update.effective_user.id):
                    try:
                        await update.message.delete()
                        await _Codec.send_text(ctx.bot, update.effective_chat.id, "🚫 المنشن ممنوع هنا.")
                        return "antitag"
                    except Exception:
                        return "antitag_failed"
    if U.get_antilink(gid):
        if U.detect_links(update.message.text):
            if not U.is_owner_or_sudo(update.effective_user.id):
                try:
                    await update.message.delete()
                    await _Codec.send_text(ctx.bot, update.effective_chat.id, "🚫 الروابط ممنوعة هنا.")
                    return "antilink"
                except Exception:
                    return "antilink_failed"
    bw = U.get_antibadword(gid)
    if bw:
        extra = bw.get("words") if isinstance(bw, dict) else None
        if U.detect_bad_words(update.message.text, extra):
            if not U.is_owner_or_sudo(update.effective_user.id):
                try:
                    await update.message.delete()
                    await _Codec.send_text(ctx.bot, update.effective_chat.id, "🚫 كلام مسيء ممنوع.")
                    return "antibadword"
                except Exception:
                    return "antibadword_failed"
    return None


# ----------------------------------------------------------------------------
# Boot time + entry point
# ----------------------------------------------------------------------------
BOT_START_TIME = time.time()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Knight-Bot stopped.")
