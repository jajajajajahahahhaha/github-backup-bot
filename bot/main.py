"""
نقطه ورود بات - این با GitHub Actions اجرا میشه
- memory.json رو از ریپو لود میکنه
- polling رو برای مدت مشخص فعال میکنه
- در background هر REPO_CHECK_INTERVAL ثانیه ریپوها رو چک میکنه
- در پایان memory.json رو ذخیره و روی کانال پین میکنه
"""
import os
import sys
import time
import signal
import threading
from datetime import datetime, timezone

from . import config, telegram_client, backup
from .memory import Memory
from .github_client import GitHubClient
from .handlers import register_handlers
from .telegram_client import bot


_shutdown = threading.Event()


def periodic_checker(mem: Memory, gh: GitHubClient):
    """در background هر REPO_CHECK_INTERVAL ثانیه همه ریپوها رو چک میکنه"""
    print("[checker] started")
    while not _shutdown.is_set():
        try:
            me = gh.whoami()
            if me:
                username = me["login"]
                mem.ensure_account(username, config.GITHUB_TOKEN)
                repos = gh.list_all_repos()
                # detect deletions? we skip; only additions/changes tracked
                any_change = False
                for r in repos:
                    if _shutdown.is_set():
                        break
                    try:
                        changed = backup.check_repo_changes(gh, username, r, mem, first_seen=False)
                        if changed:
                            any_change = True
                    except Exception as e:
                        print(f"[checker] repo err {r.get('full_name')}: {e}")
                if any_change:
                    mem.touch()
                    mem.save_local()
        except Exception as e:
            print(f"[checker] loop error: {e}")

        # sleep with quick shutdown wake-up
        for _ in range(config.REPO_CHECK_INTERVAL):
            if _shutdown.is_set():
                break
            time.sleep(1)
    print("[checker] stopped")


def duration_watchdog():
    """بعد از POLL_DURATION_SECONDS به graceful shutdown سیگنال میده"""
    print(f"[watchdog] will shutdown after {config.POLL_DURATION_SECONDS}s")
    for _ in range(config.POLL_DURATION_SECONDS):
        if _shutdown.is_set():
            return
        time.sleep(1)
    print("[watchdog] time up, shutting down")
    _shutdown.set()
    try:
        bot.stop_polling()
    except Exception:
        pass


def graceful_shutdown(mem: Memory):
    """
    در پایان اجرا:
    1) memory.json روی گیت‌هاب push بشه
    2) memory.json روی کانال آپلود و پین بشه
    """
    print("[shutdown] starting graceful shutdown")
    mem.touch()

    # push to github
    ok = mem.save_to_github(commit_message=f"chore(memory): shutdown snapshot {datetime.now(timezone.utc).isoformat()}")
    print(f"[shutdown] github save: {ok}")

    # upload to channel and pin
    try:
        local = mem.save_local()
        # unpin previous
        prev_pin = mem.data.get("pinned_message_id")
        if prev_pin:
            telegram_client.unpin_channel_message(prev_pin)

        cap = (
            f"🧠 <b>memory.json snapshot</b>\n"
            f"🕒 at: {mem.data.get('last_run')}\n"
            f"👥 accounts: {len(mem.data.get('accounts', {}))}\n"
            f"📦 repos total: {sum(len(a.get('repos', {})) for a in mem.data.get('accounts', {}).values())}"
        )
        mid = telegram_client.send_channel_document(local, caption=cap)
        telegram_client.pin_channel_message(mid)
        mem.data["pinned_message_id"] = mid
        # save again with new pin id
        mem.save_to_github(commit_message=f"chore(memory): pin id {mid}")
    except Exception as e:
        print(f"[shutdown] channel snapshot error: {e}")

    try:
        telegram_client.send_owner("😴 بات خاموش شد، memory ذخیره و روی کانال پین شد. تا اجرای بعدی 👋")
    except Exception:
        pass


def main():
    # validate config
    missing = []
    for k in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID", "TELEGRAM_CHANNEL", "GITHUB_TOKEN", "MEMORY_REPO"]:
        if not getattr(config, k):
            missing.append(k)
    if missing:
        print(f"❌ missing env: {missing}")
        sys.exit(2)

    mem = Memory()
    if not mem.load_from_github():
        mem.load_local()
    mem.touch()

    gh = GitHubClient(config.GITHUB_TOKEN, username=config.GITHUB_USERNAME)
    me = gh.whoami()
    if not me:
        print("❌ github token invalid")
        sys.exit(2)
    username = me["login"]
    mem.ensure_account(username, config.GITHUB_TOKEN)
    # seed repos
    repos = gh.list_all_repos()
    for r in repos:
        mem.upsert_repo(username, r)
    mem.save_local()

    # register handlers
    register_handlers(mem, gh)

    # signal
    def _sig(_signum, _frame):
        _shutdown.set()
        try:
            bot.stop_polling()
        except Exception:
            pass
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    # boot notification
    try:
        telegram_client.send_owner(
            f"🚀 بات روشن شد!\n"
            f"👤 <b>{username}</b>\n"
            f"📦 ریپوها: <b>{len(repos)}</b>\n"
            f"⏱ این اجرا حداکثر: <code>{config.POLL_DURATION_SECONDS//60} دقیقه</code>\n"
            f"برای شروع /start رو بزن 👇"
        )
    except Exception as e:
        print(f"[main] boot notice failed: {e}")

    # start background threads
    t_check = threading.Thread(target=periodic_checker, args=(mem, gh), daemon=True)
    t_check.start()
    t_watch = threading.Thread(target=duration_watchdog, daemon=True)
    t_watch.start()

    # polling loop with auto-restart on network errors
    print("[main] starting polling")
    while not _shutdown.is_set():
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=False)
            break
        except Exception as e:
            print(f"[main] polling error: {e}, restarting in 5s")
            time.sleep(5)

    _shutdown.set()
    time.sleep(2)
    graceful_shutdown(mem)
    print("[main] bye")


if __name__ == "__main__":
    main()
