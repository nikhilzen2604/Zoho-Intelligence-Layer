"""github_client.py — create issues in the engineering backlog repo.

Kept separate from zoho_client: this talks to GitHub, that talks to Zoho. The poller
decides when to call this (enhancement + incident tickets). Free of any Zoho specifics.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")  # "owner/name"
API = "https://api.github.com"


def is_configured() -> bool:
    return bool(TOKEN and REPO)


def create_issue(title: str, body: str, labels: list[str] | None = None) -> str:
    """Create a GitHub issue and return its html_url."""
    if not is_configured():
        raise RuntimeError("GITHUB_TOKEN / GITHUB_REPO not set (see .env.example)")
    resp = requests.post(
        f"{API}/repos/{REPO}/issues",
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": labels or []},
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"GitHub issue creation failed: {resp.status_code} {resp.text[:200]}")
    return resp.json().get("html_url", "")
