import os
import subprocess
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Local imports
from email_listener import check_for_openclaw_emails
from analyze_video import analyze_tiktok
from telegram_bridge import track_usage, archive_intel

load_dotenv()

def run_catchup():
    print("🚀 Starting Inbox Catchup Sweep...")
    
    # 1. Grab ALL relevant emails (this uses your existing listener)
    emails = check_for_openclaw_emails()
    
    if not emails:
        print("✅ No matching emails found in your inbox. Backlog is clear!")
        return

    print(f"📂 Found {len(emails)} emails to process. Starting loop...\n")

    for index, email in enumerate(emails):
        subject = email.get('subject', 'Unknown Subject')
        body = email.get('body', '')
        
        # Extract the TikTok link
        tiktok_url = next((line for line in body.split() if "tiktok.com" in line), None)
        
        if not tiktok_url:
            print(f"⏩ Skipping [{index+1}/{len(emails)}]: No TikTok link found in '{subject}'")
            continue

        print(f"🎬 Processing [{index+1}/{len(emails)}]: {subject}")
        
        try:
            # Run the Gemini Brain
            analysis_result = analyze_tiktok(tiktok_url)
            
            # Archive to the correct vault based on the subject
            archive_intel(subject, tiktok_url, analysis_result)
            
            # Update the token tracker
            count = track_usage()
            
            print(f"✅ Success! Saved to Drive. (Daily Usage: {count}/1500)")
            
        except Exception as e:
            print(f"❌ Error processing '{subject}': {e}")

    print("\n🏁 Catchup Sweep Complete! Your NotebookLM vaults are up to date.")

if __name__ == '__main__':
    run_catchup()
