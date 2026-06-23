"""poller.py — the trigger. Read new tickets, classify, apply the plan to Zoho.

This is the ONLY place that decides "a new ticket arrived." It is deliberately
isolated so a webhook receiver can replace it later without touching the classifier,
mapping, or zoho_client.

Run it:
    python poller.py --dry-run --once      # show what it WOULD do, touch nothing
    python poller.py --once                # one live pass
    python poller.py --interval 5          # live, every 5 minutes (Ctrl+C to stop)

A ticket is processed at most once: its id is recorded in processed_ids.json, and
tickets already tagged 'ai:classified' in Zoho are skipped too.
"""

import argparse
import json
import time
from pathlib import Path

import audit
from classifier import classify
from mapping import plan_actions
from zoho_client import ZohoClient

PROCESSED_FILE = Path(__file__).with_name("processed_ids.json")
ALREADY_TAG = "ai:classified"


def _load_processed() -> set[str]:
    if PROCESSED_FILE.exists():
        return set(json.loads(PROCESSED_FILE.read_text()))
    return set()


def _save_processed(ids: set[str]) -> None:
    PROCESSED_FILE.write_text(json.dumps(sorted(ids)))


def _ticket_text(t: dict) -> tuple[str, str, str]:
    """Pull (subject, body, from_email) out of a Zoho ticket object."""
    subject = t.get("subject") or ""
    body = t.get("description") or ""
    from_email = t.get("email") or (t.get("contact") or {}).get("email") or ""
    return subject, body, from_email


def _already_classified(t: dict) -> bool:
    tags = t.get("tags") or []
    names = {tag.get("name") if isinstance(tag, dict) else tag for tag in tags}
    return ALREADY_TAG in names


def process_once(client: ZohoClient, dry_run: bool, limit: int) -> None:
    processed = _load_processed()
    tickets = client.list_tickets(limit=limit)
    print(f"\nfetched {len(tickets)} ticket(s); {len(processed)} already processed locally")

    for t in tickets:
        tid = str(t.get("id"))
        num = t.get("ticketNumber")
        try:
            if tid in processed or _already_classified(t):
                print(f"  #{num}: skip (already classified)")
                continue

            subject, body, from_email = _ticket_text(t)
            c = classify(subject, body, from_email)
            plan = plan_actions(c)

            head = f"  #{num} {subject!r} -> {c.disposition.value}"
            if c.priority:
                head += f"/{c.priority.value}"
            print(head + f"  (conf {c.confidence:.2f})")
            print(f"     plan: fields={plan.field_updates} tags={plan.tags}"
                  f" redirect={plan.redirect_to} review={plan.needs_review}"
                  f" pending={plan.pending_decision}")

            if dry_run:
                print("     DRY-RUN: nothing written")
                audit.log_decision(t, c, plan, mode="dry-run", applied=False)
                continue

            # --- live writes ---
            if plan.field_updates:
                client.update_ticket(tid, plan.field_updates)
            if plan.tags:
                client.add_tags(tid, plan.tags)
            if plan.comment:
                client.add_comment(tid, plan.comment, is_public=False)
            if plan.redirect_to:
                print(f"     NOTE: redirect intent to {plan.redirect_to} (auto-forward not yet built)")

            processed.add(tid)
            _save_processed(processed)
            audit.log_decision(t, c, plan, mode="live", applied=True)
            print("     applied + logged")
        except Exception as e:
            # one bad ticket or API hiccup must not stop the rest of the run.
            # it is NOT added to `processed`, so it gets retried on the next pass.
            print(f"  #{num}: ERROR - {e}  (skipped; will retry next pass)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Zoho ticket classifier poller")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify and print the plan, but write nothing to Zoho")
    ap.add_argument("--once", action="store_true",
                    help="run a single pass instead of looping")
    ap.add_argument("--interval", type=float, default=5.0,
                    help="minutes between passes when looping (default 5)")
    ap.add_argument("--limit", type=int, default=50,
                    help="max tickets to fetch per pass (default 50)")
    args = ap.parse_args()

    client = ZohoClient()
    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"poller starting [{mode}]")

    if args.once:
        process_once(client, args.dry_run, args.limit)
        return

    while True:
        try:
            process_once(client, args.dry_run, args.limit)
        except Exception as e:
            # a transient failure (e.g. network/list call) must not kill the daemon
            print(f"pass failed: {e}  (continuing)")
        print(f"sleeping {args.interval} min...")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
