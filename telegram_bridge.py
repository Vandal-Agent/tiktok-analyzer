import os
import asyncio
import subprocess
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

def track_usage():
    """Tracks daily API usage and resets at Pacific Time midnight."""
    tz = ZoneInfo("America/Los_Angeles")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    
    usage_file = "usage.json"
    data = {"date": today, "count": 0}
    
    if os.path.exists(usage_file):
        with open(usage_file, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                pass
                
    if data.get("date") != today:
        data = {"date": today, "count": 0}
        
    data["count"] += 1
    
    with open(usage_file, "w") as f:
        json.dump(data, f)
        
    return data["count"]

# Local imports from your project
from email_listener import check_for_openclaw_emails
from analyze_video import analyze_tiktok

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def archive_intel(subject, url, analysis):
    """Routes intel to the correct vault based on keywords in the subject."""
    # Default vault if no keyword matches
    filename = "general_vault.md"
    
    # Load the categories rules
    if os.path.exists("categories.json"):
        with open("categories.json", "r") as f:
            try:
                categories = json.load(f)
                subject_lower = subject.lower()
                for keyword, vault in categories.items():
                    if keyword in subject_lower:
                        filename = vault
                        break
            except json.JSONDecodeError:
                pass

    with open(filename, "a") as f:
        f.write(f"## Target: {subject}\n")
        f.write(f"**URL:** {url}\n\n")
        f.write(f"### Analysis:\n{analysis}\n")
        f.write("\n---\n\n")

    # Sync only the specific file that was updated to Google Drive
    subprocess.run(["rclone", "copy", filename, "gdrive:TikTok_Intel"])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scans inbox and presents the first found email."""
    await update.message.reply_text("Scanning your inbox for intel, Tracy...")

    emails = check_for_openclaw_emails()

    if not emails:
        await update.message.reply_text("No new emails found right now.")
        return

    first_email = emails[0]
    context.user_data['current_item'] = first_email

    keyboard = [[InlineKeyboardButton("✅ Process", callback_data="yes"),
                 InlineKeyboardButton("⏭️ Skip", callback_data="no")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📩 **Found:** {first_email['subject']}\nWould you like to analyze this?",
        reply_markup=reply_markup
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes your choice for the current email."""
    query = update.callback_query
    await query.answer()

    current = context.user_data.get('current_item')

    if not current:
        await query.edit_message_text(text="⚠️ **Session timed out.** Please run /start again.")
        return

    if query.data == "yes":
        subject = current.get('subject', 'Unknown Subject')
        await query.edit_message_text(text=f"🚀 **Processing:** {subject}...")

        body = current.get('body', '')
        tiktok_url = next((line for line in body.split() if "tiktok.com" in line), None)

        if not tiktok_url:
            await query.message.reply_text("❌ No TikTok link found in that email.")
            return

        await query.message.reply_text("🧠 **Ripping video and analyzing...**")
        analysis_result = analyze_tiktok(tiktok_url)

        current_count = track_usage()
        usage_msg = f"\n\n📈 **Daily API Usage:** {current_count} / 1500"

        # Save to the correct vault
        archive_intel(subject, tiktok_url, analysis_result)

        await query.message.reply_text(f"✅ **Analysis Complete:** Intel securely archived to Google Drive.{usage_msg}")

        # Quota Alarms
        if current_count == 1050:
            await query.message.reply_text("⚠️ **ALARM: 70% QUOTA REACHED!** ⚠️")
        elif current_count > 1050:
            await query.message.reply_text(f"⚠️ **WARNING:** Danger zone ({current_count}/1500).")

    elif query.data == "no":
        await query.edit_message_text(text=f"⏭️ **Skipped:** {current.get('subject')}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_button))
    print("AnalyzerOfTikTokBot is online and standing by, Tracy.")
    application.run_polling()
