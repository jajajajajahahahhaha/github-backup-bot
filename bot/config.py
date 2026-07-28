"""
پیکربندی مرکزی بات
همه‌ی توکن‌ها از environment variables یا GitHub Secrets خونده میشن
"""
import os

# ====== Telegram ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_OWNER_CHAT_ID = int(os.getenv("TELEGRAM_OWNER_CHAT_ID", "0") or 0)
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "").strip()  # e.g. @GITHUBBOTBACKUP or -100xxxx

# ====== GitHub ======
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "").strip()

# ====== Storage / Memory Repo ======
# ریپو ای که فایل memory.json و بک‌آپ‌ها توش نگه‌داری میشن
MEMORY_REPO = os.getenv("MEMORY_REPO", "").strip()  # e.g. jajajajajahahahhaha/github-backup-bot
MEMORY_FILE = "memory.json"

# ====== Runtime ======
# چند ثانیه polling در هر اجرای GitHub Actions فعال بمونه
# 5.5 ساعت = 19800 ثانیه اما GitHub Actions حداکثر 6 ساعت میده
# ما 5 ساعت و 20 دقیقه polling می‌کنیم بعد graceful shutdown
POLL_DURATION_SECONDS = int(os.getenv("POLL_DURATION_SECONDS", str(5 * 3600 + 20 * 60)))

# هر چند ثانیه یک بار ریپوها چک بشن برای تغییرات
REPO_CHECK_INTERVAL = int(os.getenv("REPO_CHECK_INTERVAL", "300"))  # 5 minutes

# حداکثر سایز فایل برای آپلود تلگرام (2GB برای بات‌ها اما ما محدودش می‌کنیم)
MAX_UPLOAD_SIZE = 45 * 1024 * 1024  # 45 MB safe limit

# پوشه‌ی کاری موقت
WORK_DIR = "/tmp/gh_backup_bot"
os.makedirs(WORK_DIR, exist_ok=True)
