import os
import re
import json
import subprocess
import telebot
from dotenv import load_dotenv
import google.generativeai as genai

# Load central environment file
load_dotenv("/home/vandal/.env")

TELEGRAM_BOT_TOKEN = os.getenv("TIKTOK_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("TIKTOK_GEMINI_API_KEY")

# Configure AI & Telegram
genai.configure(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Load Categories from the shared JSON file
def load_categories():
    try:
        with open("categories.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"Default": "intel_vault.txt"}


CATEGORIES = load_categories()


def track_usage(increment=1):
    print(f"📊 Usage tracked: +{increment}")
    return True


def archive_intel(summary, category_key):
    filename = CATEGORIES.get(category_key, "intel_vault.txt")

    with open(filename, "a") as f:
        f.write(f"\n---\n{summary}\n")

    subprocess.run(
        ["rclone", "copy", filename, "gdrive:Googs 2 shared with googs 1/TikTok_Intel"]
    )


def analyze_video(video_path):
    model = genai.GenerativeModel("gemini-1.5-flash")
    video_file = genai.upload_file(path=video_path)

    prompt = "Summarize this video. Extract key insights, tools mentioned, and actionable advice."
    response = model.generate_content([video_file, prompt])
    return response.text


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Vandal-Agent Active. Send me a TikTok link to analyze it, or type /sweep to check your inbox.",
    )


@bot.message_handler(func=lambda m: m.text and "tiktok.com" in m.text)
def handle_tiktok(message):
    url = re.search(r"(https?://[^\s]+)", message.text).group(1)
    bot.reply_to(message, f"🎬 Processing video from: {url}")

    try:
        subprocess.run(["yt-dlp", "-o", "temp_video.mp4", url], check=True)

        summary = analyze_video("temp_video.mp4")

        category = "Default"
        for key in CATEGORIES.keys():
            if key.lower() in message.text.lower():
                category = key
                break

        archive_intel(summary, category)

        bot.reply_to(message, f"✅ Success! Saved to {CATEGORIES[category]}")
        os.remove("temp_video.mp4")

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")


@bot.message_handler(commands=["sweep"])
def manual_sweep(message):
    bot.reply_to(message, "🚀 Starting manual inbox sweep...")
    subprocess.run(["python3", "catchup_scanner.py"])
    bot.reply_to(message, "🏁 Sweep complete. Vaults updated.")


if __name__ == "__main__":
    print("Bot is running...")
    bot.polling()
