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
                pass # If file is corrupted, just start fresh
                
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
    """Appends the analysis to a permanent ledger and syncs to Google Drive."""
    filename = "intel_vault.md"
    with open(filename, "a") as f:
        f.write(f"## Target: {subject}\n")
        f.write(f"**URL:** {url}\n\n")
        f.write(f"### Analysis:\n{analysis}\n")
        f.write("\n---\n\n")

    # Syncs the file to your 'TikTok_Intel' folder on Google Drive via rclone
    subprocess.run(["rclone", "copy", filename, "gdrive:TikTok_Intel"])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scans inbox and presents the first found email."""
    await update.message.reply_text("Scanning your inbox for Open Claw intel, Tracy...")

    emails = check_for_openclaw_emails()

    if not emails:
        await update.message.reply_text("No new Open Claw emails found right now.")
        return

    # Store the first email in user_data for the button handler
    first_email = emails[0]
    context.user_data['current_item'] = first_email

    keyboard = [
        [
            InlineKeyboardButton("✅ Process", callback_data="yes"),
            InlineKeyboardButton("⏭️ Skip", callback_data="no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📩 **Found:** {first_email['subject']}\nWould you like to analyze this one?",
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

        # 1. Get the link from the email body
        body = current.get('body', '')
        # Simple extraction (assumes the link is the only thing in the body or on its own line)
        tiktok_url = next((line for line in body.split() if "tiktok.com" in line), None)

        if not tiktok_url:
            await query.message.reply_text("❌ No TikTok link found in that email.")
            return

        # 2. Run the Gemini Brain
        await query.message.reply_text("🧠 **Ripping video and analyzing...** (This takes about 30s)")
        analysis_result = analyze_tiktok(tiktok_url)

        # 3. Track Usage & Check Alarm
        current_count = track_usage()
        usage_msg = f"\n\n📈 **Daily API Usage:** {current_count} / 1500"

        # 4. Send results to Telegram
        await query.message.reply_text(f"✅ **Analysis Complete:** Full intel securely saved to Google Drive.{usage_msg}")

        # 5. Archive to Local File & Google Drive
        archive_intel(subject, tiktok_url, analysis_result)
        await query.message.reply_text("📂 **Intel archived to Google Drive (TikTok_Intel).**")

        # 6. The 70% Quota Alarm
        if current_count == 1050:
            await query.message.reply_text("⚠️ **ALARM: 70% QUOTA REACHED!** ⚠️\nYou have used 1,050 of your 1,500 free daily Gemini requests.")
        elif current_count > 1050:
            await query.message.reply_text(f"⚠️ **WARNING:** You are in the danger zone ({current_count}/1500).")

    elif query.data == "no":
        await query.edit_message_text(text=f"⏭️ **Skipped:** {current.get('subject')}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_button))

    print("AnalyzerOfTikTokBot is online and standing by, Tracy.")
    application.run_polling()
