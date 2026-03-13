from email_listener import check_for_tiktok_emails
from tiktok_pipeline import process_tiktok_url


def run_catchup(limit=5):
    print("🚀 Starting inbox catchup sweep...")

    emails = check_for_tiktok_emails(limit=limit)

    if not emails:
        print("✅ No matching TikTok emails found.")
        return

    print(f"📂 Found {len(emails)} email(s) to process.\n")

    for index, email_item in enumerate(emails, start=1):
        subject = email_item.get("subject", "No Subject")
        url = email_item.get("tiktok_url", "")
        from_address = email_item.get("from_address", "unknown")
        message_num = email_item.get("message_num")

        print(f"[{index}/{len(emails)}] Processing: {subject}")
        print(f"From: {from_address}")
        print(f"URL: {url}")

        result = process_tiktok_url(url, source="email")
        status = result.get("status")

        if status in {"success", "duplicate", "download_failed"}:
            check_for_tiktok_emails(
                action="move_processed",
                message_num=message_num
            )
            print(f"✅ Done: {status}\n")

        elif status == "analysis_failed":
            print("❌ Analysis failed after retry. Leaving email in inbox.\n")

        elif status == "sync_failed":
            print("⚠️ Drive sync failed. Leaving email in inbox for review.\n")

        else:
            print(f"⚠️ Unknown status: {status}\n")

    print("🏁 Catchup sweep complete.")


if __name__ == "__main__":
    run_catchup(limit=5)
