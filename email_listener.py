import os
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv("/home/vandal/.env")


def check_for_openclaw_emails():
    """Connects to Gmail and finds ALL emails with 'open claw' in the subject."""

    username = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(username, password)
    mail.select("inbox")

    status, messages = mail.search(None, '(OR UNSEEN SUBJECT "open claw" UNSEEN SUBJECT "openclaw")')
    email_list = []

    if status == "OK":
        for num in messages[0].split():
            status, data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else "utf-8")

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        body = part.get_payload(decode=True).decode()
                        break
            else:
                body = msg.get_payload(decode=True).decode()

            email_list.append({
                "subject": subject,
                "body": body
            })

    mail.logout()
    return email_list[::-1]
