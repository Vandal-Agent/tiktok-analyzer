import argparse
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow


load_dotenv("/home/vandal/.env")

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
CLIENT_PATH = Path(
    os.getenv(
        "TIKTOK_GMAIL_OAUTH_CLIENT_PATH",
        "/home/vandal/.config/tiktok-analyzer/gmail_oauth_client.json",
    )
)
TOKEN_PATH = Path(
    os.getenv(
        "TIKTOK_GMAIL_OAUTH_TOKEN_PATH",
        "/home/vandal/.config/tiktok-analyzer/gmail_oauth_token.json",
    )
)


def _write_private_token(path, text):
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


def authorize(force=False):
    if not CLIENT_PATH.is_file():
        raise FileNotFoundError(f"OAuth client file not found: {CLIENT_PATH}")
    if TOKEN_PATH.exists() and not force:
        raise FileExistsError(
            f"Token already exists at {TOKEN_PATH}. Use --force to replace it."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_PATH),
        scopes=[GMAIL_SEND_SCOPE],
    )
    credentials = flow.run_local_server(
        host="localhost",
        port=8080,
        open_browser=False,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        authorization_prompt_message=(
            "\nOpen this URL in your computer's browser:\n\n{url}\n"
        ),
        success_message=(
            "Gmail authorization completed. You can close this browser tab."
        ),
    )
    if not credentials.refresh_token:
        raise RuntimeError(
            "Google did not return a refresh token. Run again with --force."
        )

    _write_private_token(TOKEN_PATH, credentials.to_json())
    print(f"GMAIL_AUTHORIZATION: SAVED")
    print(f"TOKEN_PATH: {TOKEN_PATH}")
    print(f"PERMISSIONS: {oct(TOKEN_PATH.stat().st_mode & 0o777)[2:]}")


def main():
    parser = argparse.ArgumentParser(
        description="Authorize TikTok Analyzer to send recipe email through Gmail."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing Gmail authorization token.",
    )
    args = parser.parse_args()
    authorize(force=args.force)


if __name__ == "__main__":
    main()
