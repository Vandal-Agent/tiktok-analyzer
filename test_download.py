import yt_dlp

def download_tiktok(url, output_filename="test_video.mp4"):
    ydl_opts = {
        'outtmpl': output_filename,
        'format': 'best',
        'quiet': False
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Attempting to download: {url}")
            ydl.download([url])
        print(f"Success! Saved as {output_filename}")
        return True

    except Exception as e:
        print(f"Uh oh, something went wrong: {e}")
        return False

# Protect the test so it doesn't auto-run when imported by the bot
if __name__ == "__main__":
    test_link = "https://www.tiktok.com/@tiktok/video/7106594312292453675"
    download_tiktok(test_link)
