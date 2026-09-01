import json
import os
import re
import subprocess
import time
from datetime import datetime

import yt_dlp
from dotenv import load_dotenv
from google import genai

from recipe_workflow import save_pending_recipe, send_recipe_preview


load_dotenv("/home/vandal/.env")

GEMINI_API_KEY = os.getenv("TIKTOK_GEMINI_API_KEY")
TIKTOK_ALERT_TELEGRAM_TOKEN = os.getenv("TIKTOK_ALERT_TELEGRAM_TOKEN")
TIKTOK_ALERT_CHAT_ID = os.getenv("TIKTOK_ALERT_CHAT_ID")

client = genai.Client(api_key=GEMINI_API_KEY)
USAGE_FILE = "usage.json"


USER_CONTEXT = """
You are analyzing TikTok videos for Tracy's real-world projects and setup.

Current priorities and context:
- Tracy is actively building and improving multiple personal bots and automation systems.
- One major project is OpenClaw, an AI agent / automation setup.
- Tracy also has a HealthCoach bot, TikTok analyzer bot, driving app / route
  outlook app, and future plans for a digital archaeology project.
- Tracy wants ideas that are useful for the current setup, not just interesting.
- Tracy values actionable improvements, saving or making money, and automation
  that reduces friction.

Evaluation standards:
- Do not just summarize the video.
- Decide whether it is relevant to Tracy's current projects.
- Prefer practical recommendations over hype.
- Recommend action only when there is a concrete, realistic next step.

Project labels: OpenClaw, Health, Driving, Archaeology, General.

Decision rules:
- "act" for a concrete idea Tracy could realistically test or use soon.
- "defer" for an interesting but non-immediate or immature idea.
- "ignore" for hype, generic material, poor fit, or non-actionable material.

Set send_alert true only when the video has an actionable improvement, a
realistic way to save or make money, prevents wasted time, or should be reviewed
soon. Otherwise set it false. An alert_message must be useful and 1-4 lines.
"""


def _empty_usage():
    return {
        "month": datetime.now().strftime("%Y-%m"),
        "processed": 0,
        "duplicates": 0,
        "download_fail": 0,
        "analysis_fail": 0,
        "alerts_sent": 0,
        "urls": [],
    }


def load_usage():
    if not os.path.exists(USAGE_FILE):
        return _empty_usage()

    with open(USAGE_FILE, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if data.get("month") != datetime.now().strftime("%Y-%m"):
        return _empty_usage()
    data.setdefault("alerts_sent", 0)
    return data


def save_usage(data):
    with open(USAGE_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def get_usage_summary():
    data = load_usage()
    return (
        f"Month: {data['month']}\n"
        f"Processed: {data['processed']}\n"
        f"Duplicates skipped: {data['duplicates']}\n"
        f"Failed downloads: {data['download_fail']}\n"
        f"Failed analysis: {data['analysis_fail']}\n"
        f"Alerts sent: {data['alerts_sent']}"
    )


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return text.strip("-")


def append_research_entry(entry_text, applies_to):
    applies_lower = [item.lower() for item in applies_to]
    if "openclaw" in applies_lower or "open claw" in applies_lower:
        filename = "openclaw_research.txt"
    elif any(
        item in applies_lower
        for item in ["ai", "automation", "general", "tech", "health", "driving", "archaeology"]
    ):
        filename = "tech_ai_research.txt"
    else:
        filename = "life_research.txt"

    with open(filename, "a", encoding="utf-8") as handle:
        handle.write("\n\n====================================\n")
        handle.write(entry_text)

    subprocess.run(
        ["rclone", "copy", filename, "gdrive:Googs 2 shared with googs 1/TikTok_Intel"],
        check=False,
    )
    return filename


def send_telegram_alert(message):
    if not TIKTOK_ALERT_TELEGRAM_TOKEN or not TIKTOK_ALERT_CHAT_ID or not message.strip():
        return False
    try:
        import requests

        endpoint = f"https://api.telegram.org/bot{TIKTOK_ALERT_TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(
            endpoint,
            data={"chat_id": TIKTOK_ALERT_CHAT_ID, "text": message},
            timeout=20,
        )
        return response.ok
    except Exception:
        return False


def analyze_video(video_path):
    video_file = client.files.upload(file=video_path)
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = client.files.get(name=video_file.name)
    if video_file.state.name == "FAILED":
        raise RuntimeError("Gemini failed to process the uploaded video")

    prompt = f"""
Analyze this TikTok video. First decide whether its primary purpose is teaching
a food or drink recipe.

If it is a recipe, use the spoken audio, captions, and visible on-screen text to
reconstruct it. Never invent an ingredient, quantity, cooking time, temperature,
yield, or direction. Use an empty string for a missing scalar and an empty list
for a missing list. Set an ingredient's uncertain field true when its amount or
identity is unclear. Put every material gap or conflict in uncertainties.

If it is not a recipe, analyze it for Tracy's project workflow using this context:
{USER_CONTEXT}

Return valid JSON only with these exact top-level fields:
content_type
recipe
project
source
date
summary
key_idea
why_this_matters_to_me
applies_to
value
effort
confidence
recommended_action
decision
send_alert
alert_message

Rules:
- content_type must be "recipe" or "research".
- recipe must be an object with exactly these fields:
  title, description, yield, ingredients, instructions, notes, uncertainties, confidence
- ingredients must be a JSON list of objects with exactly:
  item, amount, unit, preparation, uncertain
- instructions, notes, and uncertainties must be JSON lists of strings.
- recipe confidence must be high, medium, or low.
- For research videos, recipe must still be present but contain empty values.
- For recipe videos, use empty research values and set send_alert false.
- source is "TikTok".
- applies_to is a JSON list selected from OpenClaw, Health, Driving, Archaeology, General.
- value is an object with save_money, make_money, and improves_my_system.
- effort is easy, medium, or hard.
- decision is ignore, defer, or act.
- Return JSON only, with no Markdown fences.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[video_file, prompt],
    )
    text = response.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def download_video(url):
    video_path = "temp_video.mp4"
    options = {
        "outtmpl": video_path,
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo+bestaudio/best",
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([url])
    return video_path


def _mark_processed(usage, url):
    usage["processed"] += 1
    usage["urls"].append(url)
    save_usage(usage)


def _process_recipe(analysis, url, source, usage):
    pending = save_pending_recipe(analysis.get("recipe", {}), url, source=source)
    if not send_recipe_preview(pending["id"]):
        return {
            "status": "recipe_preview_failed",
            "url": url,
            "recipe_id": pending["id"],
            "message": "Recipe was extracted, but Telegram preview delivery failed",
        }

    _mark_processed(usage, url)
    return {
        "status": "recipe_pending",
        "url": url,
        "recipe_id": pending["id"],
        "title": pending["recipe"]["title"],
        "uncertainties": pending["recipe"]["uncertainties"],
    }


def _process_research(analysis, url, usage):
    today = datetime.now().strftime("%Y-%m-%d")
    project = analysis.get("project", "Unknown")
    source_label = analysis.get("source", "TikTok")
    analysis_date = analysis.get("date", today) or today
    summary = analysis.get("summary", "")
    key_idea = analysis.get("key_idea", "")
    why_this_matters = analysis.get("why_this_matters_to_me", "")
    applies_to = analysis.get("applies_to", [])
    value = analysis.get("value", {}) or {}
    effort = analysis.get("effort", "")
    confidence = analysis.get("confidence", "")
    recommended_action = analysis.get("recommended_action", "")
    decision = analysis.get("decision", "")
    send_alert = bool(analysis.get("send_alert", False))
    alert_message = analysis.get("alert_message", "") or ""

    if not isinstance(applies_to, list):
        applies_to = [str(applies_to)]

    entry = f"""
Date: {analysis_date}

Project:
{project}

Source:
{source_label}

TikTok:
{url}

Summary:
{summary}

Key Idea:
{key_idea}

Why this matters to me:
{why_this_matters}

Applies to:
{", ".join(applies_to)}

Value:
- Save money: {value.get("save_money", "")}
- Make money: {value.get("make_money", "")}
- Improves my system: {value.get("improves_my_system", "")}

Effort:
{effort}

Confidence:
{confidence}

Recommended Action:
{recommended_action}

Decision:
{decision}

Send Alert:
{send_alert}

Alert Message:
{alert_message}
"""
    filename = append_research_entry(entry, applies_to)

    alert_sent = False
    if send_alert and alert_message.strip() and decision == "act" and confidence == "high":
        telegram_text = (
            f"TikTok alert\n\n{alert_message.strip()}\n\n"
            f"Decision: {decision}\n"
            f"Applies to: {', '.join(applies_to)}\n"
            f"Link: {url}"
        )
        alert_sent = send_telegram_alert(telegram_text)
        if alert_sent:
            usage["alerts_sent"] += 1

    _mark_processed(usage, url)
    return {
        "status": "success",
        "url": url,
        "project": project,
        "applies_to": applies_to,
        "decision": decision,
        "send_alert": send_alert,
        "alert_sent": alert_sent,
        "saved_to": filename,
    }


def process_tiktok_url(url, source="manual"):
    usage = load_usage()
    if url in usage["urls"]:
        usage["duplicates"] += 1
        save_usage(usage)
        return {"status": "duplicate", "url": url, "message": "Already processed"}

    try:
        video_path = download_video(url)
    except Exception as exc:
        usage["download_fail"] += 1
        save_usage(usage)
        return {"status": "download_failed", "url": url, "error": str(exc)}

    try:
        analysis = analyze_video(video_path)
    except Exception as exc:
        usage["analysis_fail"] += 1
        save_usage(usage)
        return {"status": "analysis_failed", "url": url, "error": str(exc)}
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    if analysis.get("content_type") == "recipe":
        return _process_recipe(analysis, url, source, usage)
    return _process_research(analysis, url, usage)
