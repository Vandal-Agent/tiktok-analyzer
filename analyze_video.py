import os
import time
import yt_dlp
from google import genai
from dotenv import load_dotenv

load_dotenv()

def analyze_tiktok(url):
    """Downloads a TikTok video and analyzes it using Google Gemini."""
    video_path = "temp_video.mp4"
    
    # Step 1: Download the video locally using yt-dlp
    print(f"📥 Downloading video from: {url}")
    ydl_opts = {
        'outtmpl': video_path,
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo+bestaudio/best',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        return f"❌ Download failed: {str(e)}"

    # Step 2: Initialize Gemini Client
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    try:
        print(f"🧠 Uploading {video_path} to Gemini...")
        video_file = client.files.upload(file=video_path)

        # --- THE FIX: Wait for Gemini to process the video ---
        print("⏳ Waiting for Gemini to buffer the video...")
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)
            
        if video_file.state.name == "FAILED":
            return "❌ Gemini failed to process the video file."
        # ----------------------------------------------------

        # Step 3: Generate the analysis
        prompt = "Analyze this TikTok video. What is the hook? What is the main value? Provide a summary for a digital archaeology series."
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[video_file, prompt]
        )

        analysis = response.text

        # Step 4: Clean up
        if os.path.exists(video_path):
            os.remove(video_path)

        return analysis

    except Exception as e:
        if os.path.exists(video_path):
            os.remove(video_path)
        return f"❌ Gemini Analysis failed: {str(e)}"
