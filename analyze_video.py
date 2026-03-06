from google import genai
import time

# 1. Set up the new, updated client
API_KEY = "AIzaSyA1VGysgVbpmfe127EXvS1qBTsaOCP0_yM" 
client = genai.Client(api_key=API_KEY)

# 2. Upload the video we downloaded
video_path = "test_video.mp4"
print(f"Uploading {video_path} to Gemini...")
video_file = client.files.upload(file=video_path)

# 3. Wait for processing to finish
print("Waiting for video processing to complete...")
while video_file.state.name == "PROCESSING":
    print(".", end="", flush=True)
    time.sleep(2)
    video_file = client.files.get(name=video_file.name)
print("\nVideo ready!")

# 4. Analyze using the Flash-Lite model (Better for quotas)
print("Analyzing video for Open Claw Intel...")
prompt = """
You are the lead intelligence analyst for the 'Open Claw' project. 
Watch this TikTok video and provide a concise summary. 
Most importantly, extract any actionable intel on how we can:
1. Improve our operations
2. Save money
3. Make money
"""

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=[video_file, prompt]
    )
    print("\n--- OPEN CLAW INTEL REPORT ---")
    print(response.text)
except Exception as e:
    print(f"\nOops, we hit a snag: {e}")

# 5. Clean up the file from Google's servers
client.files.delete(name=video_file.name)
