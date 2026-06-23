"""Zoho Desk API client: OAuth token rotation + ticket read/update/comment helpers.

All Zoho specifics live here. The classifier knows nothing about this module, and
this module knows nothing about the classifier. Built against the free-tier-safe
surface (REST polling), so it works the same whether the plan is Enterprise or free.
"""

import os
import time
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

DC = os.getenv("ZOHO_DC", "in")
ACCOUNTS_BASE = f"https://accounts.zoho.{DC}"
DESK_BASE = f"https://desk.zoho.{DC}/api/v1"

CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
ORG_ID = os.getenv("ZOHO_ORG_ID")
DEPARTMENT_ID = os.getenv("ZOHO_DEPARTMENT_ID")


class ZohoError(RuntimeError):
    pass


class ZohoClient:
    def __init__(self) -> None:
        for name, val in [
            ("ZOHO_CLIENT_ID", CLIENT_ID),
            ("ZOHO_CLIENT_SECRET", CLIENT_SECRET),
            ("ZOHO_REFRESH_TOKEN", REFRESH_TOKEN),
            ("ZOHO_ORG_ID", ORG_ID),
        ]:
            if not val:
                raise ZohoError(f"{name} is not set (see .env.example)")
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._agent_cache: dict = {}

    # --- auth ---------------------------------------------------------------

    def _token(self) -> str:
        # refresh ~60s before expiry
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        resp = requests.post(
            f"{ACCOUNTS_BASE}/oauth/v2/token",
            params={
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": REFRESH_TOKEN,
            },
            timeout=30,
        )
        data = resp.json()
        if "access_token" not in data:
            raise ZohoError(f"token refresh failed: {data}")
        self._access_token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._access_token

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"Authorization": f"Zoho-oauthtoken {self._token()}", "orgId": ORG_ID}
        if extra:
            h.update(extra)
        return h

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{DESK_BASE}{path}"
        resp = requests.request(
            method, url, headers=self._headers(kwargs.pop("headers", None)),
            timeout=30, **kwargs,
        )
        if resp.status_code == 204 or not resp.content:
            return None
        if resp.status_code >= 400:
            raise ZohoError(f"{method} {path} -> {resp.status_code}: {resp.text}")
        return resp.json()

    # --- tickets ------------------------------------------------------------

    def list_tickets(self, limit: int = 50, **params) -> list[dict]:
        """List tickets, newest first. Pass e.g. status='Open' to filter."""
        q = {"limit": limit, "sortBy": "-createdTime"}
        if DEPARTMENT_ID:
            q["departmentId"] = DEPARTMENT_ID
        q.update(params)
        data = self._request("GET", "/tickets", params=q)
        return (data or {}).get("data", [])

    def get_ticket(self, ticket_id: str) -> dict:
        return self._request("GET", f"/tickets/{ticket_id}")

    def update_ticket(self, ticket_id: str, fields: dict) -> dict:
        """Partial update of built-in or custom fields (PATCH)."""
        return self._request("PATCH", f"/tickets/{ticket_id}", json=fields)

    def add_comment(self, ticket_id: str, content: str, is_public: bool = False) -> dict:
        """Add a comment/note. Private by default (internal audit note)."""
        return self._request(
            "POST", f"/tickets/{ticket_id}/comments",
            json={"content": content, "isPublic": is_public},
        )

    def get_agent_id(self, email: str) -> Optional[str]:
        """Resolve an agent's id from their email (None if no such active agent).
        Cached per client instance to avoid re-listing agents every ticket."""
        key = email.lower()
        if key in self._agent_cache:
            return self._agent_cache[key]
        data = self._request("GET", "/agents")
        agent_id = None
        for a in (data or {}).get("data", []):
            if (a.get("emailId") or "").lower() == key:
                agent_id = a.get("id")
                break
        self._agent_cache[key] = agent_id
        return agent_id

    def add_tags(self, ticket_id: str, tags: list[str]) -> Any:
        """Associate tags with a ticket. Zoho's associateTag wants a list of plain
        strings and auto-creates any tag that doesn't exist yet. Tags survive on free."""
        return self._request(
            "POST", f"/tickets/{ticket_id}/associateTag",
            json={"tags": list(tags)},
        )


if __name__ == "__main__":
    # smoke test: prove auth rotation + read path work against the live account
    c = ZohoClient()
    print("refreshing access token...")
    tok = c._token()
    print(f"  ok, token starts with {tok[:12]}...")
    print("listing tickets...")
    tickets = c.list_tickets(limit=5)
    print(f"  {len(tickets)} ticket(s) found")
    for t in tickets:
        print(f"   - #{t.get('ticketNumber')} [{t.get('status')}] {t.get('subject')!r}")
