import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


fake_dotenv = types.ModuleType("dotenv")
fake_dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", fake_dotenv)

fake_yt_dlp = types.ModuleType("yt_dlp")
fake_yt_dlp.YoutubeDL = MagicMock()
sys.modules.setdefault("yt_dlp", fake_yt_dlp)

fake_google = types.ModuleType("google")
fake_google.genai = types.SimpleNamespace(Client=MagicMock())
sys.modules.setdefault("google", fake_google)

fake_recipe_workflow = types.ModuleType("recipe_workflow")
fake_recipe_workflow.save_pending_recipe = MagicMock()
fake_recipe_workflow.send_recipe_preview = MagicMock()
sys.modules.setdefault("recipe_workflow", fake_recipe_workflow)

import tiktok_pipeline


FULL_DESCRIPTION = (
    "Ingredients: 1.8KG chicken breast, 1 Tsp olive oil, 400g cottage cheese. "
    "Directions: Cook on medium heat for 8-10 minutes per side."
)


class TikTokDescriptionTests(unittest.TestCase):
    def test_prompt_includes_expanded_description_and_source_rules(self):
        prompt = tiktok_pipeline._build_analysis_prompt(FULL_DESCRIPTION)
        normalized_prompt = " ".join(prompt.split())

        self.assertIn(FULL_DESCRIPTION, prompt)
        self.assertIn("hide this text behind the More button", prompt)
        self.assertIn(
            "Prefer an explicit value from the post description",
            normalized_prompt,
        )
        self.assertIn("Do not treat hashtags as ingredients", prompt)

    def test_download_returns_full_description_from_metadata(self):
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.extract_info.return_value = {"description": FULL_DESCRIPTION}

        with patch.object(tiktok_pipeline.yt_dlp, "YoutubeDL", return_value=downloader):
            path, description = tiktok_pipeline.download_video("https://tiktok.example/video")

        self.assertEqual(path, "temp_video.mp4")
        self.assertEqual(description, FULL_DESCRIPTION)
        downloader.extract_info.assert_called_once_with(
            "https://tiktok.example/video", download=True
        )

    def test_process_passes_description_to_video_analysis(self):
        recipe_analysis = {"content_type": "recipe", "recipe": {"title": "Test"}}

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, "temp_video.mp4")
            with open(video_path, "wb") as handle:
                handle.write(b"video")

            with patch.object(tiktok_pipeline, "load_usage", return_value={
                "month": "2026-09",
                "processed": 0,
                "duplicates": 0,
                "download_fail": 0,
                "analysis_fail": 0,
                "alerts_sent": 0,
                "urls": [],
            }), patch.object(
                tiktok_pipeline,
                "download_video",
                return_value=(video_path, FULL_DESCRIPTION),
            ), patch.object(
                tiktok_pipeline,
                "analyze_video",
                return_value=recipe_analysis,
            ) as analyze, patch.object(
                tiktok_pipeline,
                "_process_recipe",
                return_value={"status": "recipe_pending"},
            ):
                result = tiktok_pipeline.process_tiktok_url(
                    "https://tiktok.example/video", source="email"
                )

        self.assertEqual(result["status"], "recipe_pending")
        analyze.assert_called_once_with(video_path, post_description=FULL_DESCRIPTION)


if __name__ == "__main__":
    unittest.main()
