import os
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

# Load your secret credentials from the .env file
load_dotenv()

def check_for_openclaw_emails():
    # Account credentials pulled from your .env vault
    username = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not username or not password:
        print("Error: GMAIL_USER or GMAIL_APP_PASSWORD not set in .env")
        return []

    # Connect to Gmail's IMAP server securely
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(username, password)
        mail.select("inbox")
    except Exception as e:
        print(f"Failed to connect to Gmail: {e}")
        return []

    # Search for unread emails that match either "Open Claw" or "openclaw"
    search_criteria = '(UNSEEN (OR SUBJECT "Open Claw" SUBJECT "openclaw"))'
    status, messages = mail.search(None, search_criteria)
    
    mail_ids = messages[0].split()
    found_emails = []

    for i in mail_ids:
        res, msg_data = mail.fetch(i, "(RFC822)")
        for response in msg_data:
            if isinstance(response, tuple):
                msg = email.message_from_bytes(response[1])
                
                # Decode the subject line to readable text
                subject, encoding = decode_header(msg.get("Subject", ""))[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                # Extract the message body (looking for the TikTok link)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                else:
                    body = msg.get_payload(decode=True).decode()

                found_emails.append({"subject": subject, "body": body})

    mail.logout()
    return found_emails

if __name__ == "__main__":
    print("Scanning for new Open Claw intel, Tracy...")
    emails = check_for_openclaw_emails()
    
    if not emails:
        print("No new Open Claw emails found at this time.")
    else:
        for e in emails:
            print(f"Target Acquired: {e['subject']}")
            print("Standing by for your command to process, Googs.")
