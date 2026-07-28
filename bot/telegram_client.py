"""
رَپِر تلگرام - همه ارتباط با API تلگرام از اینجا رد میشه
"""
import telebot
from telebot import types
import os
from . import config


bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN, parse_mode="HTML", threaded=True)


def send_channel_document(file_path: str, caption: str = None) -> int:
    """آپلود فایل روی کانال، برمی‌گردونه message_id"""
    with open(file_path, "rb") as f:
        msg = bot.send_document(
            chat_id=config.TELEGRAM_CHANNEL,
            document=f,
            caption=(caption or "")[:1024],
            visible_file_name=os.path.basename(file_path),
        )
    return msg.message_id


def send_channel_text(text: str, disable_notification: bool = False) -> int:
    msg = bot.send_message(
        chat_id=config.TELEGRAM_CHANNEL,
        text=text[:4000],
        disable_notification=disable_notification,
        disable_web_page_preview=True,
    )
    return msg.message_id


def pin_channel_message(message_id: int):
    try:
        bot.pin_chat_message(config.TELEGRAM_CHANNEL, message_id, disable_notification=True)
    except Exception as e:
        print(f"[tg] pin failed: {e}")


def unpin_channel_message(message_id: int):
    try:
        bot.unpin_chat_message(config.TELEGRAM_CHANNEL, message_id)
    except Exception as e:
        print(f"[tg] unpin failed: {e}")


def send_owner(text: str, reply_markup=None):
    return bot.send_message(
        config.TELEGRAM_OWNER_CHAT_ID,
        text[:4000],
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
