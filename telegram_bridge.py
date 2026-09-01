import os
import re
import subprocess
import sys

import telebot
from dotenv import load_dotenv

from recipe_workflow import (
    delete_pending_recipe,
    email_recipe,
    load_pending_recipe,
    revise_recipe,
    send_recipe_preview,
)
from tiktok_pipeline import get_usage_summary, process_tiktok_url


load_dotenv("/home/vandal/.env")

TELEGRAM_BOT_TOKEN = os.getenv("TIKTOK_TELEGRAM_BOT_TOKEN")
AUTHORIZED_CHAT_ID = os.getenv("TIKTOK_ALERT_CHAT_ID", "")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
EDIT_SESSIONS = {}


def _authorized(chat_id):
    return bool(AUTHORIZED_CHAT_ID and str(chat_id) == str(AUTHORIZED_CHAT_ID))


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Vandal-Agent Active.\n\n"
        "Send a TikTok link to analyze it.\n"
        "Recipe videos are extracted and shown for approval.\n\n"
        "Commands:\n"
        "/stats - show monthly processing stats\n"
        "/sweep - run inbox sweep manually",
    )


@bot.message_handler(commands=["stats"])
def send_stats(message):
    bot.reply_to(message, f"TikTok Research Stats\n\n{get_usage_summary()}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("recipe_"))
def handle_recipe_action(call):
    if not _authorized(call.message.chat.id):
        bot.answer_callback_query(call.id, "This action is not authorized.", show_alert=True)
        return

    try:
        action, recipe_id = call.data.split(":", 1)
    except ValueError:
        bot.answer_callback_query(call.id, "Invalid recipe action.", show_alert=True)
        return

    pending = load_pending_recipe(recipe_id)
    if not pending:
        bot.answer_callback_query(call.id, "This recipe is no longer pending.", show_alert=True)
        return

    if action == "recipe_email":
        try:
            recipients = email_recipe(recipe_id)
        except Exception as exc:
            bot.answer_callback_query(call.id, "Email failed.", show_alert=True)
            bot.send_message(call.message.chat.id, f"Recipe email failed: {exc}")
            return
        bot.answer_callback_query(call.id, "Recipe emailed.")
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None,
        )
        bot.send_message(
            call.message.chat.id,
            f"Recipe emailed successfully to {len(recipients)} saved addresses.",
        )
    elif action == "recipe_edit":
        EDIT_SESSIONS[call.message.chat.id] = recipe_id
        bot.answer_callback_query(call.id, "Send your correction next.")
        bot.send_message(
            call.message.chat.id,
            "Send the correction in one message. For example: "
            "Change the butter to 2 tablespoons.",
        )
    elif action == "recipe_cancel":
        delete_pending_recipe(recipe_id)
        EDIT_SESSIONS.pop(call.message.chat.id, None)
        bot.answer_callback_query(call.id, "Recipe cancelled.")
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None,
        )
        bot.send_message(call.message.chat.id, "Recipe cancelled. No email was sent.")


@bot.message_handler(
    func=lambda message: message.chat.id in EDIT_SESSIONS,
    content_types=["text"],
)
def handle_recipe_edit(message):
    if not _authorized(message.chat.id):
        return
    recipe_id = EDIT_SESSIONS.pop(message.chat.id)
    bot.reply_to(message, "Updating the recipe...")
    try:
        revise_recipe(recipe_id, message.text)
        if not send_recipe_preview(recipe_id):
            raise RuntimeError("The updated preview could not be delivered")
    except Exception as exc:
        bot.reply_to(message, f"Recipe update failed: {exc}")
        return
    bot.reply_to(message, "Updated preview sent.")


@bot.message_handler(func=lambda message: message.text and "tiktok.com" in message.text)
def handle_tiktok(message):
    match = re.search(r"(https?://[^\s]+)", message.text)
    if not match:
        bot.reply_to(message, "Could not find a valid TikTok link.")
        return

    url = match.group(1)
    bot.reply_to(message, f"Processing TikTok...\n{url}")
    result = process_tiktok_url(url, source="telegram")
    status = result.get("status")

    if status == "success":
        bot.reply_to(
            message,
            "Saved\n\n"
            f"Project: {result.get('project')}\n"
            f"Decision: {result.get('decision')}\n"
            f"Applies to: {', '.join(result.get('applies_to', []))}",
        )
    elif status == "recipe_pending":
        bot.reply_to(message, "Recipe extracted. Check the approval preview above.")
    elif status == "recipe_preview_failed":
        bot.reply_to(message, "Recipe extracted, but the approval preview could not be sent.")
    elif status == "duplicate":
        bot.reply_to(message, "That TikTok was already processed.")
    elif status == "download_failed":
        bot.reply_to(message, "Video download failed.")
    elif status == "analysis_failed":
        bot.reply_to(message, "Gemini analysis failed.")
    elif status == "sync_failed":
        bot.reply_to(message, "Saved locally but Drive sync failed.")
    else:
        bot.reply_to(message, f"Unknown result: {status}")


@bot.message_handler(commands=["sweep"])
def manual_sweep(message):
    if not _authorized(message.chat.id):
        bot.reply_to(message, "This command is not authorized.")
        return
    bot.reply_to(message, "Running inbox sweep...")
    subprocess.run(
        [sys.executable, "catchup_scanner.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        check=False,
    )
    bot.reply_to(message, "Sweep complete.")


if __name__ == "__main__":
    print("TikTok Telegram bot running...")
    bot.infinity_polling(skip_pending=True)
