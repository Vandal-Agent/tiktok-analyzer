import os
import re
import json
import subprocess
import yt_dlp
from datetime import datetime
from google import genai
from dotenv import load_dotenv

load_dotenv("/home/vandal/.env")

GEMINI_API_KEY = os.getenv("TIKTOK_GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

USAGE_FILE = "usage.json"


def load_usage():
    if not os.path.exists(USAGE_FILE):
        return {
            "month": datetime.now().strftime("%Y-%m"),
            "processed": 0,
            "duplicates": 0,
            "download_fail": 0,
            "analysis_fail": 0,
            "urls": []
        }

    with open(USAGE_FILE, "r") as f:
        data = json.load(f)

    current_month = datetime.now().strftime("%Y-%m")

    if data["month"] != current_month:
        data = {
            "month": current_month,
            "processed": 0,
            "duplicates": 0,
            "download_fail": 0,
            "analysis_fail": 0,
            "urls": []
        }

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
        f"Failed analysis: {data['analysis_fail']}"
    )


def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip("-")


def append_research_entry(entry_text, tags):

    tags_lower = [t.lower() for t in tags]

    if "openclaw" in tags_lower or "open claw" in tags_lower:
        filename = "openclaw_research.txt"
    elif any(t in tags_lower for t in ["ai", "python", "automation", "agent", "coding"]):
        filename = "tech_ai_research.txt"
    else:
        filename = "life_research.txt"

    with open(filename, "a") as f:
        f.write("\n\n====================================\n")
        f.write(entry_text)

    subprocess.run([
        "rclone",
        "copy",
        filename,
        "gdrive:Googs 2 shared with googs 1/TikTok_Intel"
    ])


def analyze_video(video_path):

    video_file = client.files.upload(file=video_path)

    while video_file.state.name == "PROCESSING":
        video_file = client.files.get(name=video_file.name)

    prompt = """
Analyze this TikTok.

Return JSON with:

title
creator
tags (max 5)
summary
key_takeaways
tools
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[video_file, prompt]
    )

    text = response.text.strip()

    text = text.replace("```json", "").replace("```", "")

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


def process_tiktok_url(url):

    usage = load_usage()

    if url in usage["urls"]:
        usage["duplicates"] += 1
        save_usage(usage)

        return {
            "status": "duplicate",
            "url": url,
            "message": "Already processed"
        }

    try:
        video_path = download_video(url)

    except Exception as e:

        usage["download_fail"] += 1
        save_usage(usage)

        return {
            "status": "download_error",
            "error": str(e)
        }

    try:

        analysis = analyze_video(video_path)

    except Exception as e:

        usage["analysis_fail"] += 1
        save_usage(usage)

        return {
            "status": "analysis_error",
            "error": str(e)
        }

    finally:

        if os.path.exists(video_path):
            os.remove(video_path)

    title = analysis.get("title", "Untitled")
    creator = analysis.get("creator", "")
    tags = analysis.get("tags", [])
    summary = analysis.get("summary", "")
    takeaways = analysis.get("key_takeaways", "")
    tools = analysis.get("tools", "")

    date_str = datetime.now().strftime("%Y-%m-%d")

    entry = f"""
Date: {date_str}

Title: {title}

Creator: {creator}

Tags: {", ".join(tags)}

Summary:
{summary}

Key Takeaways:
{takeaways}

Tools Mentioned:
{tools}

TikTok:
{url}
"""

    append_research_entry(entry, tags)

    usage["processed"] += 1
    usage["urls"].append(url)

    save_usage(usage)

    return {
        "status": "success",
        "url": url,
        "title": title,
        "creator": creator,
        "tags": tags
    }
