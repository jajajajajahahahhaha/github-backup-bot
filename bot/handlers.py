"""
هندلرهای بات تلگرام - /start، لیست ریپوها، نمایش تغییرات یک ریپو، دکمه بک‌آپ اکانت جدید
"""
from telebot import types
from datetime import datetime, timezone
from . import config, telegram_client, backup
from .telegram_client import bot
from .github_client import GitHubClient


# state سبک برای گفتگوی دکمه‌ی افزودن اکانت
_pending_new_account = {}  # chat_id -> {"stage": "await_username"/"await_token", "username": ...}


def owner_only(func):
    def wrapper(msg_or_cq, *args, **kwargs):
        chat_id = msg_or_cq.from_user.id if hasattr(msg_or_cq, "from_user") else msg_or_cq.chat.id
        if chat_id != config.TELEGRAM_OWNER_CHAT_ID:
            try:
                bot.reply_to(msg_or_cq, "⛔ دسترسی نداری.")
            except Exception:
                pass
            return
        return func(msg_or_cq, *args, **kwargs)
    return wrapper


def register_handlers(mem, main_gh: GitHubClient):
    """
    ثبت هندلرهای بات. mem و main_gh از خارج پاس داده میشن.
    """

    def build_repo_list_keyboard(username: str):
        acct = mem.data["accounts"].get(username, {"repos": {}})
        repos = list(acct["repos"].items())
        # sort by name
        repos.sort(key=lambda x: x[1]["name"].lower())
        kb = types.InlineKeyboardMarkup(row_width=2)
        for rid, r in repos:
            emoji = "🔒" if r.get("private") else "📂"
            kb.add(types.InlineKeyboardButton(
                f"{emoji} {r['name']}",
                callback_data=f"repo|{username}|{rid}"
            ))
        kb.add(types.InlineKeyboardButton("➕ افزودن اکانت جدید", callback_data="newacct"))
        kb.add(types.InlineKeyboardButton("🔄 رفرش لیست", callback_data=f"refresh|{username}"))
        kb.add(types.InlineKeyboardButton("💾 بک‌آپ همه ریپوها", callback_data=f"backupall|{username}"))
        return kb

    @bot.message_handler(commands=["start", "help"])
    def cmd_start(msg):
        if msg.from_user.id != config.TELEGRAM_OWNER_CHAT_ID:
            bot.reply_to(msg, "⛔ دسترسی نداری.")
            return

        # اطمینان از اکانت اصلی
        me = main_gh.whoami()
        if not me:
            bot.reply_to(msg, "❌ نمی‌تونم به گیت‌هاب متصل شم. توکن رو چک کن.")
            return
        username = me["login"]
        acct = mem.ensure_account(username, config.GITHUB_TOKEN)

        # اگر ریپوها هنوز لود نشدن، سریع لودشون کن
        if not acct["repos"]:
            repos = main_gh.list_all_repos()
            for r in repos:
                mem.upsert_repo(username, r)

        text = (
            f"👋 سلام رفیق!\n"
            f"🔑 اکانت گیت‌هاب: <b>{username}</b>\n"
            f"📊 تعداد ریپوها: <b>{len(mem.data['accounts'][username]['repos'])}</b>\n"
            f"⏱ آخرین ران: <code>{mem.data.get('last_run','-')}</code>\n\n"
            f"روی هر ریپو بزن تا تاریخچه‌ی تغییراتش رو ببینی 👇"
        )
        bot.reply_to(msg, text, reply_markup=build_repo_list_keyboard(username))

    @bot.callback_query_handler(func=lambda c: c.data.startswith("refresh|"))
    def cb_refresh(cq):
        if cq.from_user.id != config.TELEGRAM_OWNER_CHAT_ID:
            bot.answer_callback_query(cq.id, "⛔")
            return
        _, username = cq.data.split("|", 1)
        repos = main_gh.list_all_repos() if username == config.GITHUB_USERNAME else GitHubClient(mem.data["accounts"][username].get("_token", config.GITHUB_TOKEN)).list_public_repos_of(username)
        for r in repos:
            mem.upsert_repo(username, r)
        try:
            bot.edit_message_reply_markup(cq.message.chat.id, cq.message.message_id, reply_markup=build_repo_list_keyboard(username))
        except Exception:
            pass
        bot.answer_callback_query(cq.id, "🔄 رفرش شد")

    @bot.callback_query_handler(func=lambda c: c.data.startswith("repo|"))
    def cb_repo(cq):
        if cq.from_user.id != config.TELEGRAM_OWNER_CHAT_ID:
            bot.answer_callback_query(cq.id, "⛔")
            return
        _, username, rid = cq.data.split("|", 2)
        rec = mem.data["accounts"].get(username, {}).get("repos", {}).get(rid)
        if not rec:
            bot.answer_callback_query(cq.id, "پیدا نشد")
            return
        lines = [
            f"📦 <b>{rec['full_name']}</b>",
            f"🌿 branch: <code>{rec.get('default_branch','main')}</code>",
            f"🔒 private: {rec.get('private', False)}",
        ]
        if rec.get("previous_names"):
            lines.append(f"↪️ نام‌های قبلی: {', '.join(rec['previous_names'])}")
        lines.append(f"\n📜 <b>تاریخچه ({len(rec.get('history', []))} رویداد):</b>")
        for h in rec.get("history", [])[-25:]:
            at = h.get("at", "?")
            if h["type"] == "commit":
                msg1 = (h.get("message", "").splitlines()[0] if h.get("message") else "")[:80]
                files = h.get("files_changed", [])
                lines.append(f"• <code>{at}</code>\n  💬 {msg1}\n  🔗 <code>{h['sha'][:8]}</code>  📁 {len(files)} فایل")
            elif h["type"] == "rename":
                lines.append(f"• <code>{at}</code> ✏️ rename: {h.get('old_name')} → {h.get('new_name')}")
            elif h["type"] == "created_tracking":
                lines.append(f"• <code>{at}</code> 🎬 tracking شروع شد")

        lines.append(f"\n📦 بک‌آپ‌های آپلود شده: <b>{len(rec.get('backups', []))}</b>")

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 لیست ریپوها", callback_data=f"back|{username}"))
        kb.add(types.InlineKeyboardButton("⬇️ بک‌آپ همین حالا", callback_data=f"bknow|{username}|{rid}"))

        try:
            bot.edit_message_text("\n".join(lines)[:4000], cq.message.chat.id, cq.message.message_id, reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            bot.send_message(cq.message.chat.id, "\n".join(lines)[:4000], reply_markup=kb, disable_web_page_preview=True)
        bot.answer_callback_query(cq.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
    def cb_back(cq):
        if cq.from_user.id != config.TELEGRAM_OWNER_CHAT_ID:
            bot.answer_callback_query(cq.id, "⛔")
            return
        _, username = cq.data.split("|", 1)
        acct = mem.data["accounts"].get(username, {"repos": {}})
        text = (
            f"👋 اکانت گیت‌هاب: <b>{username}</b>\n"
            f"📊 تعداد ریپوها: <b>{len(acct['repos'])}</b>\n"
            f"⏱ آخرین ران: <code>{mem.data.get('last_run','-')}</code>"
        )
        try:
            bot.edit_message_text(text, cq.message.chat.id, cq.message.message_id, reply_markup=build_repo_list_keyboard(username), disable_web_page_preview=True)
        except Exception:
            pass
        bot.answer_callback_query(cq.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("bknow|"))
    def cb_backup_now(cq):
        if cq.from_user.id != config.TELEGRAM_OWNER_CHAT_ID:
            bot.answer_callback_query(cq.id, "⛔")
            return
        _, username, rid = cq.data.split("|", 2)
        rec = mem.data["accounts"].get(username, {}).get("repos", {}).get(rid)
        if not rec:
            bot.answer_callback_query(cq.id, "پیدا نشد")
            return
        bot.answer_callback_query(cq.id, "⏳ در حال بک‌آپ...")
        # force backup by clearing last_sha temporarily? no - just download & upload
        # ما یه دور check_repo_changes صداش می‌زنیم اگه تغییر نداشت هم یه zip می‌فرستیم
        repo_info = {
            "id": int(rid),
            "name": rec["name"],
            "full_name": rec["full_name"],
            "default_branch": rec.get("default_branch", "main"),
            "private": rec.get("private", False),
            "pushed_at": None,
        }
        # اگه تغییری نبود مصنوعی last_sha رو خالی کن یبار
        saved_sha = rec.get("last_sha")
        rec["last_sha"] = None
        rec["commits_seen"] = []
        try:
            gh = main_gh if username == config.GITHUB_USERNAME else GitHubClient(config.GITHUB_TOKEN)
            backup.check_repo_changes(gh, username, repo_info, mem, first_seen=False)
        except Exception as e:
            bot.send_message(cq.message.chat.id, f"❌ خطا: {e}")
        # restore
        if rec.get("last_sha") is None:
            rec["last_sha"] = saved_sha

    @bot.callback_query_handler(func=lambda c: c.data.startswith("backupall|"))
    def cb_backup_all(cq):
        if cq.from_user.id != config.TELEGRAM_OWNER_CHAT_ID:
            bot.answer_callback_query(cq.id, "⛔")
            return
        _, username = cq.data.split("|", 1)
        bot.answer_callback_query(cq.id, "⏳ شروع بک‌آپ همه...")
        try:
            gh = main_gh if username == config.GITHUB_USERNAME else GitHubClient(config.GITHUB_TOKEN)
            backup.full_backup_account(gh, username, mem)
        except Exception as e:
            bot.send_message(cq.message.chat.id, f"❌ خطا: {e}")

    @bot.callback_query_handler(func=lambda c: c.data == "newacct")
    def cb_new_account(cq):
        if cq.from_user.id != config.TELEGRAM_OWNER_CHAT_ID:
            bot.answer_callback_query(cq.id, "⛔")
            return
        _pending_new_account[cq.from_user.id] = {"stage": "await_username"}
        bot.send_message(cq.from_user.id, "📝 نام کاربری اکانت گیت‌هاب رو بفرست:")
        bot.answer_callback_query(cq.id)

    @bot.message_handler(func=lambda m: m.from_user.id in _pending_new_account)
    def flow_new_account(msg):
        state = _pending_new_account.get(msg.from_user.id)
        if not state:
            return
        if state["stage"] == "await_username":
            state["username"] = msg.text.strip()
            state["stage"] = "await_token"
            bot.reply_to(msg, "🔑 حالا Personal Access Token اون اکانت رو بفرست (پیام رو بعدش پاک کن):")
            return
        if state["stage"] == "await_token":
            token = msg.text.strip()
            username = state["username"]
            _pending_new_account.pop(msg.from_user.id, None)
            try:
                bot.delete_message(msg.chat.id, msg.message_id)
            except Exception:
                pass
            gh = GitHubClient(token, username=username)
            me = gh.whoami()
            if not me:
                bot.send_message(msg.chat.id, "❌ توکن معتبر نیست.")
                return
            actual = me["login"]
            mem.ensure_account(actual, token)
            bot.send_message(msg.chat.id, f"✅ اکانت <b>{actual}</b> اضافه شد. شروع بک‌آپ کامل...")
            backup.full_backup_account(gh, actual, mem)
            bot.send_message(msg.chat.id, "🏁 تموم شد. برای دیدن لیست /start رو بزن.")
