import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


fake_requests = types.ModuleType("requests")
fake_requests.post = MagicMock()
sys.modules.setdefault("requests", fake_requests)

fake_dotenv = types.ModuleType("dotenv")
fake_dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", fake_dotenv)

fake_google = types.ModuleType("google")
fake_google.genai = types.SimpleNamespace(Client=MagicMock())
sys.modules.setdefault("google", fake_google)

import recipe_workflow


SAMPLE_RECIPE = {
    "title": "Skillet Potatoes",
    "description": "Crisp potatoes made in a skillet.",
    "yield": "4 servings",
    "ingredients": [
        {
            "item": "potatoes",
            "amount": "2",
            "unit": "pounds",
            "preparation": "diced",
            "uncertain": False,
        },
        {
            "item": "salt",
            "amount": "",
            "unit": "",
            "preparation": "",
            "uncertain": True,
        },
    ],
    "instructions": ["Dice the potatoes.", "Cook until browned."],
    "notes": ["Use a large skillet."],
    "uncertainties": ["The amount of salt was not stated."],
    "confidence": "medium",
}


class RecipeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_pending_dir = recipe_workflow.PENDING_DIR
        recipe_workflow.PENDING_DIR = Path(self.temp_dir.name)

    def tearDown(self):
        recipe_workflow.PENDING_DIR = self.original_pending_dir
        self.temp_dir.cleanup()

    def test_pending_recipe_round_trip_uses_stable_id(self):
        first = recipe_workflow.save_pending_recipe(
            SAMPLE_RECIPE, "https://www.tiktok.com/@cook/video/123", source="email"
        )
        second = recipe_workflow.save_pending_recipe(
            SAMPLE_RECIPE, "https://www.tiktok.com/@cook/video/123", source="email"
        )

        self.assertEqual(first["id"], second["id"])
        loaded = recipe_workflow.load_pending_recipe(first["id"])
        self.assertEqual(loaded["recipe"]["title"], "Skillet Potatoes")
        self.assertEqual(loaded["source"], "email")

    def test_format_recipe_flags_uncertain_amounts_and_includes_source(self):
        text = recipe_workflow.format_recipe(
            SAMPLE_RECIPE, "https://www.tiktok.com/@cook/video/123"
        )

        self.assertIn("2 pounds potatoes, diced", text)
        self.assertIn("salt [amount uncertain]", text)
        self.assertIn("Needs verification:", text)
        self.assertIn("Source video: https://www.tiktok.com/@cook/video/123", text)

    @patch("recipe_workflow.requests.post")
    def test_preview_has_three_approval_buttons(self, post):
        post.return_value = MagicMock(ok=True)
        pending = recipe_workflow.save_pending_recipe(
            SAMPLE_RECIPE, "https://www.tiktok.com/@cook/video/123"
        )

        with patch.object(recipe_workflow, "TELEGRAM_TOKEN", "token"), patch.object(
            recipe_workflow, "TELEGRAM_CHAT_ID", "12345"
        ):
            self.assertTrue(recipe_workflow.send_recipe_preview(pending["id"]))

        sent = post.call_args.kwargs["data"]
        keyboard = json.loads(sent["reply_markup"])["inline_keyboard"][0]
        self.assertEqual([button["text"] for button in keyboard], ["Email recipe", "Edit", "Cancel"])

    def test_requires_exactly_two_recipients(self):
        with patch.dict("os.environ", {"TIKTOK_RECIPE_RECIPIENTS": "one@example.com"}):
            with self.assertRaises(ValueError):
                recipe_workflow._recipe_recipients()


    @patch("recipe_workflow._gmail_service")
    def test_email_recipe_uses_gmail_api_and_deletes_after_confirmation(self, service):
        send = (
            service.return_value.users.return_value
            .messages.return_value.send
        )
        send.return_value.execute.return_value = {"id": "gmail-message-id"}
        pending = recipe_workflow.save_pending_recipe(
            SAMPLE_RECIPE, "https://www.tiktok.com/@cook/video/456"
        )

        with patch.object(recipe_workflow, "GMAIL_USER", "sender@example.com"), patch.dict(
            "os.environ",
            {"TIKTOK_RECIPE_RECIPIENTS": "one@example.com,two@example.com"},
        ):
            recipients = recipe_workflow.email_recipe(pending["id"])

        self.assertEqual(recipients, ["one@example.com", "two@example.com"])
        send.assert_called_once()
        call = send.call_args.kwargs
        self.assertEqual(call["userId"], "me")
        self.assertTrue(call["body"]["raw"])
        self.assertIsNone(recipe_workflow.load_pending_recipe(pending["id"]))

    @patch("recipe_workflow._gmail_service")
    def test_email_failure_keeps_recipe_pending(self, service):
        (
            service.return_value.users.return_value
            .messages.return_value.send.return_value.execute
        ).side_effect = RuntimeError("network unavailable")
        pending = recipe_workflow.save_pending_recipe(
            SAMPLE_RECIPE, "https://www.tiktok.com/@cook/video/789"
        )

        with patch.object(recipe_workflow, "GMAIL_USER", "sender@example.com"), patch.dict(
            "os.environ",
            {"TIKTOK_RECIPE_RECIPIENTS": "one@example.com,two@example.com"},
        ):
            with self.assertRaises(RuntimeError):
                recipe_workflow.email_recipe(pending["id"])

        self.assertIsNotNone(recipe_workflow.load_pending_recipe(pending["id"]))



if __name__ == "__main__":
    unittest.main()
