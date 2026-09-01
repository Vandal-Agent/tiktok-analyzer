import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


events = []

fake_bot = MagicMock()
fake_bot.message_handler.side_effect = lambda *args, **kwargs: lambda func: func
fake_bot.callback_query_handler.side_effect = (
    lambda *args, **kwargs: lambda func: func
)
fake_bot.answer_callback_query.side_effect = (
    lambda *args, **kwargs: events.append("acknowledged")
)
fake_bot.send_message.side_effect = lambda *args, **kwargs: events.append("status")

fake_telebot = types.ModuleType("telebot")
fake_telebot.TeleBot = lambda token: fake_bot
sys.modules.setdefault("telebot", fake_telebot)

fake_dotenv = types.ModuleType("dotenv")
fake_dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", fake_dotenv)

fake_recipe_workflow = types.ModuleType("recipe_workflow")
fake_recipe_workflow.delete_pending_recipe = MagicMock()
fake_recipe_workflow.email_recipe = MagicMock()
fake_recipe_workflow.load_pending_recipe = MagicMock(return_value={"status": "pending"})
fake_recipe_workflow.revise_recipe = MagicMock()
fake_recipe_workflow.send_recipe_preview = MagicMock()
original_recipe_workflow = sys.modules.get("recipe_workflow")
sys.modules["recipe_workflow"] = fake_recipe_workflow

fake_pipeline = types.ModuleType("tiktok_pipeline")
fake_pipeline.get_usage_summary = MagicMock()
fake_pipeline.process_tiktok_url = MagicMock()
original_tiktok_pipeline = sys.modules.get("tiktok_pipeline")
sys.modules["tiktok_pipeline"] = fake_pipeline

import telegram_bridge

if original_recipe_workflow is None:
    sys.modules.pop("recipe_workflow", None)
else:
    sys.modules["recipe_workflow"] = original_recipe_workflow
if original_tiktok_pipeline is None:
    sys.modules.pop("tiktok_pipeline", None)
else:
    sys.modules["tiktok_pipeline"] = original_tiktok_pipeline


class TelegramEmailCallbackTests(unittest.TestCase):
    def setUp(self):
        events.clear()
        telegram_bridge.AUTHORIZED_CHAT_ID = "12345"
        fake_recipe_workflow.load_pending_recipe.return_value = {"status": "pending"}
        fake_recipe_workflow.email_recipe.side_effect = None
        fake_recipe_workflow.email_recipe.return_value = [
            "one@example.com",
            "two@example.com",
        ]
        fake_bot.reset_mock()
        fake_bot.answer_callback_query.side_effect = (
            lambda *args, **kwargs: events.append("acknowledged")
        )
        fake_bot.send_message.side_effect = (
            lambda *args, **kwargs: events.append("status")
        )

    def test_email_callback_is_acknowledged_before_email_network_call(self):
        fake_recipe_workflow.email_recipe.side_effect = (
            lambda recipe_id: events.append("email") or [
                "one@example.com",
                "two@example.com",
            ]
        )
        call = SimpleNamespace(
            id="callback-id",
            data="recipe_email:abc123",
            message=SimpleNamespace(
                chat=SimpleNamespace(id=12345),
                message_id=55,
            ),
        )

        telegram_bridge.handle_recipe_action(call)

        self.assertIn("acknowledged", events)
        self.assertIn("email", events)
        self.assertLess(events.index("acknowledged"), events.index("email"))


if __name__ == "__main__":
    unittest.main()
