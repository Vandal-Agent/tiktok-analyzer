import os
import re
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv("/home/vandal/.env")

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
PROCESSED_LABEL = "TikTok_Processed"

ALLOWED_SENDERS = {
    "tracy644@gmail.com",
    "tracy644@icloud.com",
}


def decode_mime_header(value):
    if not value:
        return ""

    decoded_parts = decode_header(value)
    result = []

    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="ignore"))
        else:
            result.append(part)

    return "".join(result)


def extract_plain_text_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(errors="ignore")

    return ""


def extract_tiktok_url(body):
    match = re.search(r"(https?://[^\s]+tiktok\.com[^\s]*)|(https?://[^\s]*tiktok\.com[^\s]*)", body)
    if match:
        return match.group(0).strip()

    match = re.search(r"(https?://[^\s]+)", body)
    if match and "tiktok.com" in match.group(1):
        return match.group(1).strip()

    return None


def ensure_label_exists(mail, label_name):
    status, data = mail.list()

    if status != "OK":
        return

    existing = []
    for item in data:
        if isinstance(item, bytes):
            existing.append(item.decode(errors="ignore"))

    if not any(f'"{label_name}"' in line or f"/{label_name}" in line for line in existing):
        mail.create(label_name)


def move_to_processed(mail, message_num):
    ensure_label_exists(mail, PROCESSED_LABEL)
    mail.copy(message_num, PROCESSED_LABEL)
    mail.store(message_num, "+FLAGS", "\\Seen")
    mail.store(message_num, "+FLAGS", "\\Deleted")
    mail.expunge()


def check_for_tiktok_emails(limit=5, action="fetch", message_num=None):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    mail.select("inbox")

    if action == "move_processed" and message_num is not None:
        move_to_processed(mail, message_num)
        mail.logout()
        return True

    email_list = []

    status, messages = mail.search(None, "UNSEEN")
    if status != "OK":
        mail.logout()
        return []

    message_nums = messages[0].split()
    message_nums = message_nums[::-1]

    for num in message_nums:
        if len(email_list) >= limit:
            break

        status, data = mail.fetch(num, "(RFC822)")
        if status != "OK":
            continue

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_mime_header(msg.get("Subject", ""))
        from_header = decode_mime_header(msg.get("From", "")).lower()

        if not any(sender in from_header for sender in ALLOWED_SENDERS):
            continue

        body = extract_plain_text_body(msg)
        tiktok_url = extract_tiktok_url(body)

        if not tiktok_url:
            continue

        email_list.append({
            "message_num": num,
            "subject": subject,
            "from_address": from_header,
            "body": body,
            "tiktok_url": tiktok_url,
        })

    mail.logout()
    return email_list
