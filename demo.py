"""Run a few realistic messages through classify() to sanity-check the brain.

    python demo.py
"""

from classifier import classify

SAMPLES = [
    # (subject, body, from_email)
    ("Dashboard not loading",
     "Since this morning the analytics dashboard is completely blank for our whole team. "
     "Nobody can see any reports. This is blocking our board meeting at 3pm.",
     "ceo@bigcustomer.com"),

    ("Need a CSV export of last quarter",
     "Could you export our Q1 revenue data as a CSV and send it over? Thanks.",
     "analyst@customer.com"),

    ("How do I add a teammate?",
     "Hi, where in the settings do I invite another user to our workspace?",
     "ops@customer.com"),

    ("Feature idea: Slack alerts",
     "It would be great if Zenalyst could push an alert to our Slack when a KPI drops "
     "below a threshold. Any chance you could build that?",
     "growth@customer.com"),

    ("Pricing for the enterprise plan",
     "We're evaluating Zenalyst for 200 seats. Can you share enterprise pricing and a quote?",
     "procurement@prospect.com"),

    ("Re: invoice",
     "",
     "noreply@randommarketing.com"),

    ("urgent",
     "asdkjhasd test test ignore",
     "someone@unknown.com"),
]


def main() -> None:
    for subject, body, sender in SAMPLES:
        c = classify(subject, body, sender)
        print(f"\nFrom: {sender}")
        print(f"Subject: {subject}")
        print(f"  -> disposition={c.disposition.value}"
              f"  sub_type={c.sub_type.value if c.sub_type else '-'}"
              f"  priority={c.priority.value if c.priority else '-'}"
              f"  redirect_to={c.redirect_to or '-'}"
              f"  conf={c.confidence:.2f}")
        print(f"     {c.reasoning}")


if __name__ == "__main__":
    main()
