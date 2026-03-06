import os
import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
from email_listener import check_for_openclaw_emails

# Load vault credentials
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Global queue to manage emails one by one
email_queue = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the process and fetches the email list."""
    global email_queue
    await update.message.reply_text("Scanning your inbox for Open Claw intel, Tracy...")
    
    email_queue = check_for_openclaw_emails()
    
    if not email_queue:
        await update.message.reply_text("No new Open Claw emails found right now.")
        return

    await update.message.reply_text(f"Found {len(email_queue)} targets. Let's review them one by one.")
    await show_next_email(update, context)

async def show_next_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Presents the next email subject with action buttons."""
    global email_queue
    
    if not email_queue:
        msg = "All caught up! No more emails in the queue."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    current = email_queue.pop(0)
    context.user_data['current_item'] = current

    keyboard = [
        [
            InlineKeyboardButton("✅ Process", callback_data="yes"),
            InlineKeyboardButton("⏭️ Skip", callback_data="no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"🎯 **Target Found**\n\nSubject: {current['subject']}\n\nShould I analyze this TikTok for you, Googs?"
    
    if update.callback_query:
        await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes your choice for the current email."""
    query = update.callback_query
    await query.answer()
    
    current = context.user_data.get('current_item')
    
    if query.data == "yes":
        await query.edit_message_text(text=f"🚀 **Processing:** {current['subject']}...")
        
        # Look for a TikTok URL in the email body
        urls = re.findall(r'(https?://[^\s]+)', current.get('body', ''))
        tiktok_url = next((url for url in urls if "tiktok.com" in url), None)

        if tiktok_url:
            await query.message.reply_text(f"📥 Found link! Passing to analysis engine...\nURL: {tiktok_url}")
            # This is where we trigger analyze_video.py in the next step
        else:
            await query.message.reply_text("❌ Target lost: No TikTok link found in that email.")
            
    else:
        await query.edit_message_text(text=f"⏭️ **Skipped:** {current['subject']}")

    # Immediately move to the next item in the queue
    await show_next_email(update, context)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    
    print("AnalyzerOfTikTokBot is online and standing by, Tracy.")
    app.run_polling()
