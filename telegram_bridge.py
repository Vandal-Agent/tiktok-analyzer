import os
import re
import telebot
from dotenv import load_dotenv

from tiktok_pipeline import process_tiktok_url, get_usage_summary

load_dotenv("/home/vandal/.env")

TELEGRAM_BOT_TOKEN = os.getenv("TIKTOK_TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Vandal-Agent Active.\n\n"
        "Send a TikTok link to analyze it.\n"
        "Commands:\n"
        "/stats - show monthly processing stats\n"
        "/sweep - run inbox sweep manually"
    )


@bot.message_handler(commands=["stats"])
def send_stats(message):
    stats = get_usage_summary()
    bot.reply_to(message, f"📊 TikTok Research Stats\n\n{stats}")


@bot.message_handler(func=lambda m: m.text and "tiktok.com" in m.text)
def handle_tiktok(message):

    match = re.search(r"(https?://[^\s]+)", message.text)

    if not match:
        bot.reply_to(message, "❌ Could not find a valid TikTok link.")
        return

    url = match.group(1)

    bot.reply_to(message, f"🎬 Processing TikTok...\n{url}")

    result = process_tiktok_url(url, source="telegram")

    status = result.get("status")

    if status == "success":
        bot.reply_to(
            message,
            f"✅ Saved\n\n"
            f"Title: {result.get('title')}\n"
            f"Creator: {result.get('creator')}\n"
            f"Tags: {', '.join(result.get('tags', []))}"
        )

    elif status == "duplicate":
        bot.reply_to(message, "⚠️ That TikTok was already processed.")

    elif status == "download_failed":
        bot.reply_to(message, "❌ Video download failed.")

    elif status == "analysis_failed":
        bot.reply_to(message, "❌ Gemini analysis failed.")

    elif status == "sync_failed":
        bot.reply_to(message, "⚠️ Saved locally but Drive sync failed.")

    else:
        bot.reply_to(message, f"⚠️ Unknown result: {status}")


@bot.message_handler(commands=["sweep"])
def manual_sweep(message):
    import subprocess

    bot.reply_to(message, "🚀 Running inbox sweep...")

    subprocess.run(["python3", "catchup_scanner.py"])

    bot.reply_to(message, "🏁 Sweep complete.")


if __name__ == "__main__":
    print("TikTok Telegram bot running...")
    bot.polling()
