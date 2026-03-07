import os
import time
from google import genai
from dotenv import load_dotenv

# Load the vault
load_dotenv(override=True)
API_KEY = os.getenv("GEMINI_API_KEY")

# Setup the client
client = genai.Client(api_key=API_KEY)

def analyze_tiktok(video_path):
    print(f"Uploading {video_path} to Gemini...")
    video_file = client.files.upload(file=video_path)

    print("Waiting for video processing to complete...")
    while video_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(10)
        video_file = client.files.get(name=video_file.name)
    
    if video_file.state.name == "FAILED":
        return "Error: Video processing failed."
        
    print("\nVideo ready!\nAnalyzing video intel...")
    
    prompt = "Summarize the key takeaways from this video and identify any 'Open Claw' strategies mentioned."
    
    # Using the working 2.5 Flash model
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[video_file, prompt]
    )
    
    return response.text

# This part only runs if you test the file directly in the terminal
if __name__ == "__main__":
    # Test it to make sure we didn't break anything
    result = analyze_tiktok("test_video.mp4")
    print("\n--- FINAL OUTPUT ---")
    print(result)
