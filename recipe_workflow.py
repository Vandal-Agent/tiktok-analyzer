import base64
import json
import os
import tempfile
from datetime import datetime, timezone
from email.message import EmailMessage
from hashlib import sha256
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai


load_dotenv("/home/vandal/.env")

PENDING_DIR = Path(os.getenv("TIKTOK_PENDING_RECIPE_DIR", "pending_recipes"))
TELEGRAM_TOKEN = os.getenv("TIKTOK_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TIKTOK_ALERT_CHAT_ID")
GMAIL_USER = os.getenv("GMAIL_USER")
RECIPE_RECIPIENTS_ENV = "TIKTOK_RECIPE_RECIPIENTS"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_OAUTH_CLIENT_PATH = Path(
    os.getenv(
        "TIKTOK_GMAIL_OAUTH_CLIENT_PATH",
        "/home/vandal/.config/tiktok-analyzer/gmail_oauth_client.json",
    )
)
GMAIL_OAUTH_TOKEN_PATH = Path(
    os.getenv(
        "TIKTOK_GMAIL_OAUTH_TOKEN_PATH",
        "/home/vandal/.config/tiktok-analyzer/gmail_oauth_token.json",
    )
)
MAX_TELEGRAM_TEXT = 3800


def _pending_path(recipe_id):
    safe_id = "".join(ch for ch in str(recipe_id) if ch.isalnum() or ch in "-_")
    if not safe_id or safe_id != str(recipe_id):
        raise ValueError("Invalid recipe id")
    return PENDING_DIR / f"{safe_id}.json"


def _atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def normalize_recipe(raw_recipe):
    raw_recipe = raw_recipe if isinstance(raw_recipe, dict) else {}
    ingredients = []
    for raw_item in raw_recipe.get("ingredients", []):
        if not isinstance(raw_item, dict):
            continue
        item = str(raw_item.get("item") or "").strip()
        if not item:
            continue
        ingredients.append(
            {
                "item": item,
                "amount": str(raw_item.get("amount") or "").strip(),
                "unit": str(raw_item.get("unit") or "").strip(),
                "preparation": str(raw_item.get("preparation") or "").strip(),
                "uncertain": bool(raw_item.get("uncertain", False)),
            }
        )

    instructions = [
        str(step).strip()
        for step in raw_recipe.get("instructions", [])
        if str(step).strip()
    ]
    uncertainties = [
        str(item).strip()
        for item in raw_recipe.get("uncertainties", [])
        if str(item).strip()
    ]
    notes = [
        str(item).strip()
        for item in raw_recipe.get("notes", [])
        if str(item).strip()
    ]

    return {
        "title": str(raw_recipe.get("title") or "Untitled TikTok Recipe").strip(),
        "description": str(raw_recipe.get("description") or "").strip(),
        "yield": str(raw_recipe.get("yield") or "").strip(),
        "ingredients": ingredients,
        "instructions": instructions,
        "notes": notes,
        "uncertainties": uncertainties,
        "confidence": str(raw_recipe.get("confidence") or "low").strip().lower(),
    }


def save_pending_recipe(recipe, url, source="email"):
    recipe_id = sha256(url.encode("utf-8")).hexdigest()[:12]
    payload = {
        "id": recipe_id,
        "status": "pending",
        "source": source,
        "url": url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recipe": normalize_recipe(recipe),
    }
    _atomic_write_json(_pending_path(recipe_id), payload)
    return payload


def load_pending_recipe(recipe_id):
    path = _pending_path(recipe_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def update_pending_recipe(recipe_id, recipe):
    payload = load_pending_recipe(recipe_id)
    if not payload:
        raise FileNotFoundError(f"Recipe {recipe_id} was not found")
    payload["recipe"] = normalize_recipe(recipe)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["status"] = "pending"
    _atomic_write_json(_pending_path(recipe_id), payload)
    return payload


def delete_pending_recipe(recipe_id):
    path = _pending_path(recipe_id)
    if path.exists():
        path.unlink()
        return True
    return False


def format_recipe(recipe, url):
    recipe = normalize_recipe(recipe)
    lines = [recipe["title"]]
    if recipe["description"]:
        lines.extend(["", recipe["description"]])
    if recipe["yield"]:
        lines.extend(["", f"Yield: {recipe['yield']}"])

    lines.extend(["", "Ingredients:"])
    if recipe["ingredients"]:
        for ingredient in recipe["ingredients"]:
            quantity = " ".join(
                part for part in [ingredient["amount"], ingredient["unit"]] if part
            )
            detail = " ".join(part for part in [quantity, ingredient["item"]] if part)
            if ingredient["preparation"]:
                detail += f", {ingredient['preparation']}"
            if ingredient["uncertain"]:
                detail += " [amount uncertain]"
            lines.append(f"• {detail}")
    else:
        lines.append("• No reliable ingredient list could be extracted.")

    lines.extend(["", "Directions:"])
    if recipe["instructions"]:
        for number, step in enumerate(recipe["instructions"], start=1):
            lines.append(f"{number}. {step}")
    else:
        lines.append("No reliable directions could be extracted.")

    if recipe["notes"]:
        lines.extend(["", "Notes:"])
        lines.extend(f"• {note}" for note in recipe["notes"])

    if recipe["uncertainties"]:
        lines.extend(["", "Needs verification:"])
        lines.extend(f"• {item}" for item in recipe["uncertainties"])

    lines.extend(["", f"Source video: {url}"])
    return "\n".join(lines)


def _telegram_chunks(text, limit=MAX_TELEGRAM_TEXT):
    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_recipe_preview(recipe_id):
    payload = load_pending_recipe(recipe_id)
    if not payload:
        return False
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    text = "Recipe preview\n\n" + format_recipe(payload["recipe"], payload["url"])
    chunks = _telegram_chunks(text)
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for index, chunk in enumerate(chunks):
        request_payload = {"chat_id": TELEGRAM_CHAT_ID, "text": chunk}
        if index == len(chunks) - 1:
            request_payload["reply_markup"] = json.dumps(
                {
                    "inline_keyboard": [
                        [
                            {"text": "Email recipe", "callback_data": f"recipe_email:{recipe_id}"},
                            {"text": "Edit", "callback_data": f"recipe_edit:{recipe_id}"},
                            {"text": "Cancel", "callback_data": f"recipe_cancel:{recipe_id}"},
                        ]
                    ]
                }
            )
        response = requests.post(endpoint, data=request_payload, timeout=20)
        if not response.ok:
            return False
    return True


def _recipe_recipients():
    recipients = [
        address.strip()
        for address in os.getenv(RECIPE_RECIPIENTS_ENV, "").split(",")
        if address.strip()
    ]
    if len(recipients) != 2:
        raise ValueError(f"{RECIPE_RECIPIENTS_ENV} must contain exactly two comma-separated addresses")
    return recipients


def _write_private_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def _gmail_credentials():
    if not GMAIL_OAUTH_CLIENT_PATH.is_file():
        raise RuntimeError(
            f"Gmail OAuth client file is missing: {GMAIL_OAUTH_CLIENT_PATH}"
        )
    if not GMAIL_OAUTH_TOKEN_PATH.is_file():
        raise RuntimeError(
            "Gmail authorization is missing. Run authorize_gmail.py once."
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    credentials = Credentials.from_authorized_user_file(
        str(GMAIL_OAUTH_TOKEN_PATH),
        [GMAIL_SEND_SCOPE],
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _write_private_text(GMAIL_OAUTH_TOKEN_PATH, credentials.to_json())
    if not credentials.valid:
        raise RuntimeError(
            "Gmail authorization is invalid. Run authorize_gmail.py again."
        )
    return credentials


def _gmail_service():
    from googleapiclient.discovery import build

    return build(
        "gmail",
        "v1",
        credentials=_gmail_credentials(),
        cache_discovery=False,
    )


def _gmail_raw_message(message):
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def email_recipe(recipe_id):
    payload = load_pending_recipe(recipe_id)
    if not payload:
        raise FileNotFoundError(f"Recipe {recipe_id} was not found")
    if not GMAIL_USER:
        raise RuntimeError("GMAIL_USER is not configured")

    recipients = _recipe_recipients()
    recipe = payload["recipe"]
    message = EmailMessage()
    message["From"] = GMAIL_USER
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"TikTok Recipe: {recipe['title']}"
    message.set_content(format_recipe(recipe, payload["url"]))

    result = (
        _gmail_service()
        .users()
        .messages()
        .send(
            userId="me",
            body={"raw": _gmail_raw_message(message)},
        )
        .execute()
    )
    if not result or not result.get("id"):
        raise RuntimeError("Gmail API did not confirm that the message was sent")

    delete_pending_recipe(recipe_id)
    return recipients


def revise_recipe(recipe_id, instruction):
    payload = load_pending_recipe(recipe_id)
    if not payload:
        raise FileNotFoundError(f"Recipe {recipe_id} was not found")
    instruction = str(instruction or "").strip()
    if not instruction:
        raise ValueError("An edit instruction is required")

    client = genai.Client(api_key=os.getenv("TIKTOK_GEMINI_API_KEY"))
    prompt = f"""
Revise the structured recipe using only the user's correction.

Current recipe JSON:
{json.dumps(payload['recipe'], ensure_ascii=False)}

User correction:
{instruction}

Return valid JSON only, using the same exact fields as the current recipe.
Do not invent ingredients, quantities, times, temperatures, or steps.
Preserve everything the correction does not change.
If the correction remains ambiguous, add it to uncertainties instead of guessing.
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = response.text.strip().replace("```json", "").replace("```", "").strip()
    return update_pending_recipe(recipe_id, json.loads(text))
