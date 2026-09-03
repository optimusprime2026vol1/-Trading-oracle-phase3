"""
Run this ON YOUR OWN MACHINE, interactively, once per trading day.

Kite Connect access tokens expire daily (spec: .env.example note on
ZERODHA_ACCESS_TOKEN), so there is no way to obtain one without a human
completing Zerodha's login flow in a browser -- it cannot be automated
from CI, and it is never something to paste into a chat with an AI
assistant or commit to source control.

Usage:
    export ZERODHA_API_KEY=...      # or put it in .env and `source` it
    export ZERODHA_API_SECRET=...
    python scripts/generate_kite_session.py

What it does:
    1. Prints a login URL.
    2. You open it, log in with your Zerodha credentials, and are
       redirected to your app's configured redirect URL with a
       `request_token` query parameter.
    3. Paste that request_token back into this script when prompted.
    4. It exchanges it for an access_token and writes it to .env,
       replacing any previous ZERODHA_ACCESS_TOKEN line.

The request_token is single-use and expires within seconds/minutes of
being issued -- if generate_session() fails with TokenException, the
usual cause is a stale or already-used request_token; just log in again
for a fresh one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"


def _load_required_env_vars() -> tuple[str, str]:
    from src.utils.config import ConfigError, get_env

    try:
        api_key = get_env("ZERODHA_API_KEY", required=True)
        api_secret = get_env("ZERODHA_API_SECRET", required=True)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "Set ZERODHA_API_KEY and ZERODHA_API_SECRET in your environment "
            "or .env before running this script.",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key, api_secret  # type: ignore[return-value]


def _write_access_token_to_env(access_token: str) -> None:
    """Replaces the ZERODHA_ACCESS_TOKEN line in .env, or appends it if
    absent. Never touches any other line."""
    if not ENV_PATH.is_file():
        print(
            f"No .env file found at {ENV_PATH}. Copy .env.example to .env "
            "first, then re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    text = ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r"^ZERODHA_ACCESS_TOKEN=.*$", re.MULTILINE)
    new_line = f"ZERODHA_ACCESS_TOKEN={access_token}"

    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"

    ENV_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote today's access_token to {ENV_PATH}")


def main() -> None:
    try:
        from kiteconnect import KiteConnect  # type: ignore
    except ImportError:
        print(
            "kiteconnect is not installed. Run: "
            "pip install kiteconnect --break-system-packages",
            file=sys.stderr,
        )
        sys.exit(1)

    api_key, api_secret = _load_required_env_vars()
    kite = KiteConnect(api_key=api_key)

    print("1. Open this URL in a browser and log in to Zerodha:\n")
    print(f"   {kite.login_url()}\n")
    print("2. After login you'll be redirected to your app's redirect URL.")
    print("   Copy the 'request_token' value from that URL's query string.\n")

    request_token = input("Paste request_token here: ").strip()
    if not request_token:
        print("No request_token entered; aborting.", file=sys.stderr)
        sys.exit(1)

    session = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session["access_token"]

    _write_access_token_to_env(access_token)
    print("Done. This token is valid until the next Zerodha session reset "
          "(typically end of trading day) -- re-run this script tomorrow.")


if __name__ == "__main__":
    main()
