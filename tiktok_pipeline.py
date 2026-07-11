import os
import re
import json
import subprocess
from datetime import datetime

import yt_dlp
from google import genai
from dotenv import load_dotenv

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
- Tracy also has:
  - a HealthCoach bot
  - a TikTok analyzer bot
  - a driving app / route outlook app
  - future plans for a digital archaeology project
- Tracy wants to know if ideas are actually useful for his current setup, not just interesting in theory.
- Tracy values:
  - actionable improvements
  - ways to save money
  - ways to make money
  - automation ideas that reduce friction
  - ideas that fit his current infrastructure and active projects

Important evaluation standards:
- Do not just summarize the video.
- Decide whether the content is truly relevant to Tracy's current projects.
- Prefer practical recommendations over hype.
- Be skeptical of ideas that are vague, expensive, overbuilt, or unlikely to fit his setup.
- Only recommend acting when there is a concrete, realistic next step.

Project labels available:
- OpenClaw
- Health
- Driving
- Archaeology
- General

Decision rules:
- "act" only if the video contains a concrete idea Tracy could realistically test, use, save money with, or make money with soon.
- "defer" if the idea is interesting but not immediate, not yet mature, or depends on future projects.
- "ignore" if it is mostly hype, generic, not a fit, or not actionable for Tracy.

Telegram alert rules:
Set "send_alert" to true only if at least one of these is true:
1. The video contains a clearly actionable improvement for an active Tracy project.
2. The video suggests a realistic way to save money on APIs, hosting, tooling, or workflow.
3. The video suggests a realistic way Tracy could make money or create a higher-value project.
4. The video prevents Tracy from wasting time on something that is not a fit.
5. The video is important enough that Tracy should probably look at it soon.

Set "send_alert" to false if the video is merely interesting, general, repetitive, or low-value.

Alert message rules:
- alert_message must be short and useful.
- 1 to 4 lines max.
- Say what the video is about, why it matters, and what Tracy should do next.
- If send_alert is false, alert_message should be an empty string.
"""


def load_usage():
    if not os.path.exists(USAGE_FILE):
        return {
            "month": datetime.now().strftime("%Y-%m"),
            "processed": 0,
            "duplicates": 0,
            "download_fail": 0,
            "analysis_fail": 0,
            "alerts_sent": 0,
            "urls": [],
        }

    with open(USAGE_FILE, "r") as f:
        data = json.load(f)

    current_month = datetime.now().strftime("%Y-%m")

    if data.get("month") != current_month:
        data = {
            "month": current_month,
            "processed": 0,
            "duplicates": 0,
            "download_fail": 0,
            "analysis_fail": 0,
            "alerts_sent": 0,
            "urls": [],
        }

    if "alerts_sent" not in data:
        data["alerts_sent"] = 0

    return data


def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


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
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def append_research_entry(entry_text, applies_to):
    applies_lower = [item.lower() for item in applies_to]

    if "openclaw" in applies_lower or "open claw" in applies_lower:
        filename = "openclaw_research.txt"
    elif any(item in applies_lower for item in ["ai", "automation", "general", "tech", "health", "driving", "archaeology"]):
        filename = "tech_ai_research.txt"
    else:
        filename = "life_research.txt"

    with open(filename, "a") as f:
        f.write("\n\n====================================\n")
        f.write(entry_text)

    subprocess.run(
        [
            "rclone",
            "copy",
            filename,
            "gdrive:Googs 2 shared with googs 1/TikTok_Intel",
        ],
        check=False,
    )

    return filename


def send_telegram_alert(message):
    if not TIKTOK_ALERT_TELEGRAM_TOKEN or not TIKTOK_ALERT_CHAT_ID or not message.strip():
        return False

    try:
        import requests

        url = f"https://api.telegram.org/bot{TIKTOK_ALERT_TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TIKTOK_ALERT_CHAT_ID,
            "text": message,
        }
        response = requests.post(url, data=payload, timeout=20)
        return response.ok
    except Exception:
        return False

def analyze_video(video_path):
    video_file = client.files.upload(file=video_path)

    while video_file.state.name == "PROCESSING":
        video_file = client.files.get(name=video_file.name)

    prompt = f"""
Analyze this TikTok video for Tracy's project workflow.

{USER_CONTEXT}

Return valid JSON only with these exact fields:

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
- project: short label like "TikTok Research"
- source: "TikTok"
- date: today's date if available, otherwise ""
- summary: 2-4 sentences
- key_idea: one concise paragraph
- why_this_matters_to_me: explain relevance to Tracy's actual setup and active projects
- applies_to: JSON list chosen from ["OpenClaw", "Health", "Driving", "Archaeology", "General"]
- value: JSON object with keys:
    - save_money
    - make_money
    - improves_my_system
- effort: one of ["easy", "medium", "hard"]
- confidence: one of ["high", "medium", "low"]
- recommended_action: a concrete next step
- decision: one of ["ignore", "defer", "act"]
- send_alert: true or false
- alert_message: short Telegram message; empty string if send_alert is false

Return JSON only. No markdown fences.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[video_file, prompt],
    )

    text = response.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    return json.loads(text)


def download_video(url):
    video_path = "temp_video.mp4"

    ydl_opts = {
        "outtmpl": video_path,
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo+bestaudio/best",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return video_path


def process_tiktok_url(url, source="manual"):
    usage = load_usage()

    if url in usage["urls"]:
        usage["duplicates"] += 1
        save_usage(usage)
        return {
            "status": "duplicate",
            "url": url,
            "message": "Already processed",
        }

    try:
        video_path = download_video(url)
    except Exception as e:
        usage["download_fail"] += 1
        save_usage(usage)
        return {
            "status": "download_error",
            "error": str(e),
        }

    try:
        analysis = analyze_video(video_path)
    except Exception as e:
        usage["analysis_fail"] += 1
        save_usage(usage)
        return {
            "status": "analysis_error",
            "error": str(e),
        }
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    today_str = datetime.now().strftime("%Y-%m-%d")

    project = analysis.get("project", "Unknown")
    source_label = analysis.get("source", "TikTok")
    analysis_date = analysis.get("date", today_str) or today_str
    summary = analysis.get("summary", "")
    key_idea = analysis.get("key_idea", "")
    why_this_matters = analysis.get("why_this_matters_to_me", "")
    applies_to = analysis.get("applies_to", [])
    value = analysis.get("value", {}) or {}
    effort = analysis.get("effort", "")
    confidence = analysis.get("confidence", "")
    recommended_action = analysis.get("recommended_action", "")
    decision = analysis.get("decision", "")
    send_alert = analysis.get("send_alert", False)
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
            f"TikTok alert\n\n"
            f"{alert_message.strip()}\n\n"
            f"Decision: {decision}\n"
            f"Applies to: {', '.join(applies_to)}\n"
            f"Link: {url}"
        )
        alert_sent = send_telegram_alert(telegram_text)
        if alert_sent:
            usage["alerts_sent"] += 1

    usage["processed"] += 1
    usage["urls"].append(url)
    save_usage(usage)

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
