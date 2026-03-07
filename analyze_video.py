import os
import time
from google import genai
from dotenv import load_dotenv

# 1. Load the vault WITH override
load_dotenv(override=True)
API_KEY = os.getenv("GEMINI_API_KEY")

# DEBUG: Print the first 10 characters to verify it's the new key
print(f"DEBUG: Using API Key starting with -> {API_KEY[:10]}...")

# 2. Setup the client
client = genai.Client(api_key=API_KEY)

# ... (keep the rest of your upload and analysis code below this exactly the same) ...


# 2. Upload the video
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

# 4. Generate Analysis
print("Analyzing video intel...")
prompt = "Summarize the key takeaways from this video and identify any 'Open Claw' strategies mentioned."
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[video_file, prompt]
)

print("\n--- ANALYSIS COMPLETE ---")
print(response.text)
