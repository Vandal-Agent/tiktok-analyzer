import os
import re
import json
import time
import shutil
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import yt_dlp
from dotenv import load_dotenv
from google import genai

load_dotenv("/home/vandal/.env")

PROJECT_DIR = "/home/vandal/lab/tiktok-analyzer"
RESEARCH_DIR = os.path.join(PROJECT_DIR, "research")
PROCESSED_FILE = os.path.join(PROJECT_DIR, "processed_videos.json")
USAGE_FILE = os.path.join(PROJECT_DIR, "usage.json")
DRIVE_DESTINATION = "gdrive:Googs 2 shared with googs 1/TikTok_Intel"
TIMEZONE = ZoneInfo("America/Los_Angeles")

GEMINI_API_KEY = os.getenv("TIKTOK_GEMINI_API_KEY")


def ensure_dirs():
    os.makedirs(RESEARCH_DIR, exist_ok=True)


def load_json_file(path, default_value):
    if not os.path.exists(path):
        return default_value
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_value


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def current_month_key():
    return datetime.now(TIMEZONE).strftime("%Y-%m")


def load_usage():
    default_usage = {
        "month": current_month_key(),
        "processed": 0,
        "duplicates_skipped": 0,
        "failed_downloads": 0,
        "failed_analysis": 0,
    }
    usage = load_json_file(USAGE_FILE, default_usage)

    if usage.get("month") != current_month_key():
        usage = default_usage

    return usage


def increment_usage(field):
    usage = load_usage()
    usage[field] = usage.get(field, 0) + 1
    save_json_file(USAGE_FILE, usage)
    return usage


def get_usage_summary():
    usage = load_usage()
    return (
        f"Month: {usage.get('month', current_month_key())}\n"
        f"Processed: {usage.get('processed', 0)}\n"
        f"Duplicates skipped: {usage.get('duplicates_skipped', 0)}\n"
        f"Failed downloads: {usage.get('failed_downloads', 0)}\n"
        f"Failed analysis: {usage.get('failed_analysis', 0)}"
    )


def load_processed():
    return load_json_file(PROCESSED_FILE, {})


def save_processed(data):
    save_json_file(PROCESSED_FILE, data)


def normalize_tiktok_url(url):
    url = url.strip()

    match = re.search(r"(https?://[^\s]+)", url)
    if match:
        url = match.group(1)

    url = url.rstrip(").,]>\"'")

    return url


def slugify(text, max_words=8, max_length=60):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    words = text.split()
    text = "-".join(words[:max_words])
    return text[:max_length].strip("-") or "untitled"


def extract_creator_and_caption(info):
    creator = (
        info.get("uploader")
        or info.get("creator")
        or info.get("channel")
        or info.get("uploader_id")
        or "Unknown"
    )

    caption = (
        info.get("description")
        or info.get("title")
        or "No caption/title available"
    )

    return creator, caption


def download_tiktok(url, output_path):
    ydl_opts = {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "format": "mp4/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    creator, caption = extract_creator_and_caption(info)
    return {
        "creator": creator,
        "caption": caption,
    }


def build_prompt(url, creator, caption):
    return f"""
Analyze this TikTok video and return VALID JSON only.

Goals:
1. Summarize the video clearly.
2. Identify practical ideas that could help improve personal AI bots, save money, or make money when relevant.
3. Assign multiple topic tags based on the actual video content.

Return this exact JSON structure:
{{
  "short_title": "brief title for filename and display",
  "summary": "2 to 5 sentence useful summary",
  "key_takeaways": [
    "takeaway 1",
    "takeaway 2",
    "takeaway 3"
  ],
  "tools_mentioned": [
    "tool 1",
    "tool 2"
  ],
  "actionable_ideas": [
    "idea 1",
    "idea 2"
  ],
  "tags": [
    "ai",
    "automation"
  ]
}}

Rules:
- Output JSON only, no markdown fences.
- Use multiple tags when appropriate.
- Keep tags short and lowercase.
- Do not invent facts.
- If something is unknown, use an empty string or empty array.
- Prefer usefulness over hype.
- Include money-saving or money-making ideas only if actually supported by the video.

Known metadata:
TikTok URL: {url}
Creator: {creator}
Caption/Title: {caption}
""".strip()


def analyze_video_file(video_path, url, creator, caption):
    client = genai.Client(api_key=GEMINI_API_KEY)

    video_file = client.files.upload(file=video_path)

    while video_file.state and video_file.state.name == "PROCESSING":
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state and video_file.state.name == "FAILED":
        raise RuntimeError("Gemini failed to process the uploaded video file.")

    prompt = build_prompt(url, creator, caption)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[video_file, prompt],
    )

    text = response.text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = text.strip("` \n")
        cleaned = re.sub(r"^json\s*", "", cleaned, flags=re.IGNORECASE)
        return json.loads(cleaned)


def sanitize_analysis(result):
    return {
        "short_title": str(result.get("short_title", "")).strip() or "untitled",
        "summary": str(result.get("summary", "")).strip(),
        "key_takeaways": [str(x).strip() for x in result.get("key_takeaways", []) if str(x).strip()],
        "tools_mentioned": [str(x).strip() for x in result.get("tools_mentioned", []) if str(x).strip()],
        "actionable_ideas": [str(x).strip() for x in result.get("actionable_ideas", []) if str(x).strip()],
        "tags": [str(x).strip().lower() for x in result.get("tags", []) if str(x).strip()],
    }


def write_markdown_entry(url, creator, caption, analysis):
    analyzed_at = datetime.now(TIMEZONE)
    date_str = analyzed_at.strftime("%Y-%m-%d")
    timestamp_str = analyzed_at.strftime("%Y-%m-%d %I:%M %p %Z")

    short_title = analysis.get("short_title", "untitled")
    slug = slugify(short_title)
    filename = f"{date_str}-{slug}.md"
    file_path = os.path.join(RESEARCH_DIR, filename)

    counter = 2
    while os.path.exists(file_path):
        filename = f"{date_str}-{slug}-{counter}.md"
        file_path = os.path.join(RESEARCH_DIR, filename)
        counter += 1

    tags = analysis.get("tags", [])
    tools = analysis.get("tools_mentioned", [])
    takeaways = analysis.get("key_takeaways", [])
    ideas = analysis.get("actionable_ideas", [])

    lines = [
        f"# {short_title}",
        "",
        f"**Analysis Date:** {timestamp_str}",
        f"**TikTok URL:** {url}",
        f"**Creator:** {creator}",
        "",
        "## Original Caption / Title",
        caption or "None",
        "",
        "## Summary",
        analysis.get("summary", "") or "None",
        "",
        "## Key Takeaways",
    ]

    if takeaways:
        lines.extend([f"- {item}" for item in takeaways])
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Tools Mentioned",
    ])

    if tools:
        lines.extend([f"- {item}" for item in tools])
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Actionable Ideas",
    ])

    if ideas:
        lines.extend([f"- {item}" for item in ideas])
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Tags",
    ])

    if tags:
        lines.extend([f"- {item}" for item in tags])
    else:
        lines.append("- none")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")

    return file_path, filename


def sync_to_drive(file_path):
    subprocess.run(
        ["rclone", "copy", file_path, DRIVE_DESTINATION],
        check=True,
    )


def process_tiktok_url(url, source="manual"):
    ensure_dirs()

    normalized_url = normalize_tiktok_url(url)
    processed = load_processed()

    if normalized_url in processed:
        increment_usage("duplicates_skipped")
        return {
            "status": "duplicate",
            "url": normalized_url,
            "message": "Already processed",
        }

    temp_video_path = os.path.join(PROJECT_DIR, "temp_video.mp4")
    if os.path.exists(temp_video_path):
        os.remove(temp_video_path)

    try:
        metadata = download_tiktok(normalized_url, temp_video_path)
    except Exception as e:
        increment_usage("failed_downloads")
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        return {
            "status": "download_failed",
            "url": normalized_url,
            "message": str(e),
        }

    creator = metadata.get("creator", "Unknown")
    caption = metadata.get("caption", "No caption/title available")

    analysis_error = None
    analysis = None

    for attempt in range(2):
        try:
            analysis = analyze_video_file(temp_video_path, normalized_url, creator, caption)
            analysis = sanitize_analysis(analysis)
            analysis_error = None
            break
        except Exception as e:
            analysis_error = str(e)
            time.sleep(2)

    if os.path.exists(temp_video_path):
        os.remove(temp_video_path)

    if analysis is None:
        increment_usage("failed_analysis")
        return {
            "status": "analysis_failed",
            "url": normalized_url,
            "message": analysis_error or "Unknown analysis error",
        }

    file_path, filename = write_markdown_entry(
        url=normalized_url,
        creator=creator,
        caption=caption,
        analysis=analysis,
    )

    try:
        sync_to_drive(file_path)
    except Exception as e:
        return {
            "status": "sync_failed",
            "url": normalized_url,
            "message": str(e),
            "local_file": file_path,
        }

    processed[normalized_url] = {
        "processed_at": datetime.now(TIMEZONE).isoformat(),
        "source": source,
        "filename": filename,
        "title": analysis.get("short_title", "untitled"),
        "tags": analysis.get("tags", []),
    }
    save_processed(processed)
    increment_usage("processed")

    if os.path.exists(file_path):
        os.remove(file_path)

    return {
        "status": "success",
        "url": normalized_url,
        "filename": filename,
        "title": analysis.get("short_title", "untitled"),
        "creator": creator,
        "tags": analysis.get("tags", []),
    }
