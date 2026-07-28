# 🤖 GitHub Backup Telegram Bot

بات تلگرام برای بک‌آپ کامل و لایو از همه‌ی ریپوهای گیت‌هاب — روی **GitHub Actions** رایگان اجرا میشه.

## ✨ امکانات

- 📋 لیست کامل ریپوها با `/start`
- 🔍 نمایش تاریخچه‌ی تغییرات هر ریپو با یک کلیک (کامیت + diff فایل‌ها)
- ⏰ اجرای دوره‌ای هر ~۵.۵ ساعت با GitHub Actions
- 📡 مانیتور زنده تا ~۵ ساعت در هر اجرا (چک هر ۵ دقیقه)
- 📦 آپلود **ZIP + changelog + full diff** روی کانال تلگرام
- ✏️ تشخیص تغییر نام ریپو
- 🧠 حافظه‌ی `memory.json` که تاریخچه‌ی همه‌ی رویدادها رو نگه می‌داره و در پایان روی کانال پین میشه
- ➕ دکمه‌ی افزودن اکانت جدید (username + token)
- 🔐 پشتیبانی از ریپوهای پابلیک و پرایوت
- 🔄 هر ران، همه‌ی تغییرات فایل‌ها از ران قبل رو می‌گیره

## 🚀 راه‌اندازی

### ۱) این ریپو رو fork/clone کن
```bash
git clone https://github.com/YOUR_USERNAME/github-backup-bot
```

### ۲) Secrets لازم رو تنظیم کن
در `Settings → Secrets and variables → Actions` این‌ها رو اضافه کن:

| نام | توضیح |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | توکن بات از @BotFather |
| `TELEGRAM_OWNER_CHAT_ID` | چت آیدی عددی خودت |
| `TELEGRAM_CHANNEL` | آیدی کانال (مثل `@GITHUBBOTBACKUP` یا `-100...`) |
| `GH_PAT` | Personal Access Token گیت‌هاب با scope `repo` |
| `GH_USERNAME` | نام کاربری گیت‌هاب اصلی |
| `MEMORY_REPO` | ریپوی نگهداری `memory.json` (مثل `user/github-backup-bot`) |

### ۳) بات رو ادمین کانال کن
با دسترسی **Post Messages** و **Pin Messages**.

### ۴) Workflow رو اجرا کن
- خودکار: هر ۵ ساعت
- دستی: از تب Actions → **Run workflow**

## 🧭 دستورات بات
- `/start` — نمایش لیست ریپوها
- کلیک روی هر ریپو — تاریخچه‌ی تغییرات
- **⬇️ بک‌آپ همین حالا** — اجبار بک‌آپ فوری
- **💾 بک‌آپ همه ریپوها** — بک‌آپ کامل حساب
- **➕ افزودن اکانت جدید** — گرفتن username/token و بک‌آپ کامل اکانت دیگه

## 📁 ساختار پروژه

```
github-backup-bot/
├── .github/workflows/bot.yml     # اجرای دوره‌ای
├── bot/
│   ├── __init__.py
│   ├── config.py                 # env vars
│   ├── memory.py                 # مدیریت memory.json
│   ├── github_client.py          # کلاینت GitHub REST API
│   ├── telegram_client.py        # wrapper تلگرام
│   ├── backup.py                 # منطق بک‌آپ و diff
│   ├── handlers.py               # دستورات و دکمه‌های بات
│   └── main.py                   # entry point
├── requirements.txt
└── memory.json                   # (خودکار ساخته میشه)
```

## ⚠️ نکات مهم

- **حداکثر سایز آپلود**: ۴۵MB (محدودیت بات‌های تلگرام). ریپوهای بزرگ‌تر skip میشن با هشدار.
- **Rate limit**: کلاینت هوشمندانه بک‌آف می‌کنه.
- **حریم خصوصی**: توکن‌ها فقط در Secrets ذخیره میشن، نه در کد.
- **کد ۵.۵ ساعت**: چون cron گیت‌هاب اکشن دقت دقیقه‌ای داره و بازه‌های نامنظم پشتیبانی نمی‌کنه، از `0 */5 * * *` استفاده می‌کنیم (هر ۵ ساعت). خود ران هم تا ~۵ ساعت و ۲۰ دقیقه فعاله، پس عملاً پوشش پیوسته است.

## 🛡 امنیت
اگه توکن‌هات لو رفت:
1. از https://github.com/settings/tokens توکن قدیمی رو **Revoke** کن
2. از @BotFather با `/revoke` توکن بات رو عوض کن
3. توکن جدید رو فقط در GitHub Secrets ذخیره کن
