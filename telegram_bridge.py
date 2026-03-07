import os
import asyncio
import subprocess
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

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

        # 3. Send results to Telegram
        await query.message.reply_text(f"📊 **Analysis Complete:**\n\n{analysis_result}")

        # 4. Archive to Local File & Google Drive
        archive_intel(subject, tiktok_url, analysis_result)
        await query.message.reply_text("📂 **Intel archived to Google Drive (TikTok_Intel).**")

    elif query.data == "no":
        await query.edit_message_text(text=f"⏭️ **Skipped:** {current.get('subject')}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_button))
    
    print("AnalyzerOfTikTokBot is online and standing by, Tracy.")
    application.run_polling()
