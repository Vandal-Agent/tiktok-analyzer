import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
from email_listener import check_for_openclaw_emails

# Load vault credentials
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# This will hold the emails we found so we can go through them one by one
email_queue = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the process and fetches the email list."""
    global email_queue
    await update.message.reply_text("Checking your inbox for Open Claw intel, Tracy...")
    
    # Get the list of emails from our listener
    email_queue = check_for_openclaw_emails()
    
    if not email_queue:
        await update.message.reply_text("No new Open Claw emails found.")
        return

    await update.message.reply_text(f"Found {len(email_queue)} emails. Let's go through them.")
    await show_next_email(update, context)

async def show_next_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the next email in the list with Yes/No buttons."""
    global email_queue
    
    if not email_queue:
        message = "All done! No more emails to process right now."
        if update.callback_query:
            await update.callback_query.message.reply_text(message)
        else:
            await update.message.reply_text(message)
        return

    # Grab the next email from the front of the list
    current = email_queue.pop(0)
    context.user_data['current_video'] = current

    # Create the buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Process", callback_data="yes"),
            InlineKeyboardButton("⏭️ Skip", callback_data="no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"🎯 **Target Found**\n\nSubject: {current['subject']}\n\nShould I process this one?"
    
    if update.callback_query:
        await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles what happens when you click Yes or No."""
    query = update.callback_query
    await query.answer()
    
    current = context.user_data.get('current_video')
    
    if query.data == "yes":
        await query.edit_message_text(text=f"✅ **Processing:** {current['subject']}\n(I'll start the TikTok analysis now...)")
        # In the next step, we will hook this 'yes' up to your analyze_video.py script
    else:
        await query.edit_message_text(text=f"⏭️ **Skipped:** {current['subject']}")

    # After deciding, immediately show the next one in the queue
    await show_next_email(update, context)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Add handlers for the /start command and button clicks
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    
    print("AnalyzerOfTikTokBot is listening for your command in Telegram...")
    app.run_polling()
