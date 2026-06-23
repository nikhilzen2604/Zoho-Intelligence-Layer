# Zenalyst Support Intelligence Layer

Context and build guide. This doubles as project context for Claude Code: it captures
every decision already made so work can continue without re-deriving any of it. (You can
rename this to `CLAUDE.md` if you want Claude Code to load it automatically.)

---

## What this project is

Zenalyst runs customer support on **Zoho Desk** (the base system of record). On top of
Zoho we are building a thin **intelligence layer**: an AI classifier that reads each
incoming message and decides what should happen to it. Zoho does the plumbing and the
process; the AI does the reading and the judgment.

The classifier is the brain. It is fully buildable and testable on its own, with no
dependency on any Zoho plan. That is what this repo currently contains. Wiring it into
Zoho is the next phase.

---

## Scope (decided, do not re-open)

- A ticket enters one of two ways: created on Zoho directly (customer portal or embedded
  web form), or sent by email to `support@zenalyst.ai`. Both converge into one Zoho ticket.
- **Out of scope:** emails that bypass the support address (landing in a salesperson's or
  founder's inbox). We are not handling that "leaked inbox" case for now.
- **Out of scope:** any timeline or phasing. This is a build, not a schedule.

---

## Core rules (must hold in any implementation)

1. **Nothing is ever auto-closed.** The lowest action the classifier can take is
   "review" (park for a human). A misclassification must never silently drop a real message.
2. **Misdirected but legitimate mail is redirected, not closed.** For example a pricing
   question sent to support is forwarded to `hello@zenalyst.ai`, and the ticket is marked
   redirected with a note.
3. **Enhancements are a separate path.** A new-feature request never flows into the support
   queue or to engineering directly. It goes through a review gate (Arvind), then a feature
   assessment and product review, and only then to GitHub. It gets no support SLA.
4. **Priority belongs to the support path.** Type and category are set up front to route the
   ticket. Priority (P1 to P4) is applied on the support branch, after the ticket is
   identified as support and before an owner is assigned. Enhancements get no priority.

---

## The classifier (already built)

Files in this repo:

```
classifier.py        the brain: schema, prompt, classify()
demo.py              runs 7 realistic samples through classify()
requirements.txt     anthropic, pydantic
```

`classify(subject, body, from_email)` returns a `Classification` with these fields:

| field        | meaning                                                                 |
|--------------|-------------------------------------------------------------------------|
| disposition  | `support` / `enhancement` / `redirect` / `review` (the routing decision)|
| sub_type     | `incident` / `service_request` / `question` (only when support)         |
| priority     | `P1`..`P4` (only when support)                                          |
| redirect_to  | target inbox, e.g. `hello@zenalyst.ai` (only when redirect)            |
| confidence   | 0.0 to 1.0                                                              |
| reasoning    | one-line explanation                                                    |

There is deliberately **no "close" disposition**. A low-confidence result (below
`CONFIDENCE_THRESHOLD`, default 0.6) is automatically downgraded to `review`, which is the
structural guarantee behind rule 1.

Config via env vars: `CLASSIFIER_MODEL` (default `claude-haiku-4-5-20251001`),
`CLASSIFIER_MIN_CONFIDENCE` (default 0.6), `DEFAULT_REDIRECT` (default `hello@zenalyst.ai`),
and `ANTHROPIC_API_KEY`.

### Run the classifier

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python demo.py
```

---

## What to build next: the Zoho integration

This is the only part that touches Zoho, and it is constrained by plan tier (see below).
The goal is a service that, for each new ticket, runs `classify()` and writes the decision
back onto the ticket.

### Plan reality (important)

- **Free plan:** the Zoho Desk REST API is available, but **webhooks are not** (webhooks start
  at the Professional tier). So on free we **poll** the API for new tickets instead of being
  pushed. Also, **Blueprint and workflow automation are not on free**, so after the classifier
  sets the fields, routing and the lifecycle are handled manually. The classifier writing
  fields back still works.
- **Professional plan (later):** unlocks webhooks (instant trigger) and Blueprint (enforced
  per-type flows). At that point swap the poller for a webhook receiver and let Zoho run the
  routing and lifecycle automatically.

So build **polling first**; keep the trigger isolated so a webhook receiver can replace it later.

### Zoho Desk API notes

- REST base: `https://desk.zoho.{dc}/api/v1` where `{dc}` is the data center. **This is an
  India account, so it is almost certainly `desk.zoho.in` with `accounts.zoho.in` for OAuth.
  Confirm the data center before coding URLs.**
- Auth: OAuth 2.0. Register a client at the Zoho API console (`api-console.zoho.in`), use the
  self-client / server-to-server flow for a backend script. Access tokens last about 1 hour,
  so implement refresh-token rotation.
- Every request needs the `orgId` header.
- Daily request budget is roughly 4,000 to 25,000 per org depending on edition, and the free
  edition cannot buy extra credits. Low volume (one customer) fits comfortably; poll every few
  minutes, not every few seconds.
- Core resources: `tickets` (read and update), `ticketComments` / `threads` (to add notes),
  `contacts`, `departments`, `agents`.

### Disposition to Zoho action mapping

| disposition | what the integration does                                                                 |
|-------------|-------------------------------------------------------------------------------------------|
| support     | set category=Support, set the sub_type and priority fields, mark as classified            |
| enhancement | set category=Enhancement, route/flag to the enhancement (Arvind) queue, no SLA            |
| redirect    | forward the message to `redirect_to`, add a note on the ticket, mark redirected (not closed)|
| review      | tag / move to a "Needs review" view for a human; do NOT close                              |

### Prerequisite in Zoho (manual, one-time)

Create the matching fields in Zoho Desk and capture their API names/IDs for the integration:
Category (Support, Enhancement), Sub-Category (incident, service request, question), Priority,
plus custom fields such as `ai_classified` (flag), `ai_confidence`, and `redirected_to`.

---

## Suggested next files (for Claude Code to create)

```
zoho_client.py    OAuth token management + helpers: get_tickets, get_ticket,
                  update_ticket, add_comment
mapping.py        turn a Classification into Zoho field updates + actions
                  (implements the disposition -> action table above)
poller.py         loop every N minutes: fetch new/unclassified tickets,
                  classify, apply. The trigger lives ONLY here so it can be
                  swapped for a webhook later
audit.py          log every classifier decision (input, output, action taken)
.env.example      ZOHO_CLIENT_ID / SECRET / REFRESH_TOKEN, ZOHO_ORG_ID,
                  ZOHO_DC, ANTHROPIC_API_KEY, field IDs
tests/            unit tests for mapping + an end-to-end dry run
webhook_server.py (LATER, on Professional) FastAPI receiver to replace the poller
```

Build order: `zoho_client.py` -> `mapping.py` -> `poller.py` -> `audit.py` -> tests.

---

## Definition of done (for this phase)

1. The classifier gives sensible results on the 7 demo scenarios (already runnable).
2. The poller reads real tickets from a free Zoho Desk, classifies them, and writes the
   classification fields back onto the ticket, never closing anything.
3. Misdirected mail is forwarded to `hello@zenalyst.ai` with a note; uncertain mail lands in
   a "Needs review" view.

Everything beyond that (webhooks, Blueprint-enforced flows, AI reply drafting, KB suggestions)
is a later phase that begins when the plan is upgraded to Professional.

---

## Design north star

The AI classifies; Zoho orchestrates. Keep the classifier free of Zoho specifics, keep the
Zoho specifics out of the classifier, and keep the trigger (poll now, webhook later) isolated
so the rest of the system never has to change when it switches.

---

# Appendix A — SLA, Governance, and Service Standards

The operating agreement around the system: how fast we respond, how the team stays
coordinated, and what customers can expect. The classifier's priority decisions
(P1–P4) map directly onto A.1 and A.3.

## A.1 Priority & First Response (summary)

| Priority | Description            | First Response   |
|----------|------------------------|------------------|
| P1       | System unavailable     | 1 Hour           |
| P2       | Critical functionality | 4 Hours          |
| P3       | General issue          | 1 Business Day   |
| P4       | Question / Enhancement | 2 Business Days  |

> Within the **support** path, P4 covers questions. **Enhancements** branch off on their
> own path and carry **no support SLA** (see A.3).

## A.2 Daily Governance Meeting

A daily standup to keep support, delivery, and engineering aligned.

**Agenda:**

1. **Customer Support Review**
   - New tickets raised in the last 24 hours
   - Open P1/P2 incidents
   - Ageing tickets requiring attention
   - Escalations or customer concerns
   - SLA risks
2. **Delivery Review**
   - Open feature requests
   - Feature assessments awaiting review
   - Development progress on approved enhancements
   - UAT activities
   - Upcoming releases
3. **Engineering Review**
   - Current sprint priorities
   - Development blockers
   - Production issues
   - Technical dependencies
4. **Customer Communication Review**
   - Customer updates required today
   - Release communications
   - Open action items from customer meetings
5. **Decisions & Actions**
   - Ownership assignments
   - Escalations
   - Due dates
   - Follow-up actions

## A.3 Service Level Agreement (SLA) Matrix

### Business Hours

- **Support Hours:** Monday – Friday, 9:00 AM – 6:00 PM IST
- **Support Channel:** `support@zenalyst.ai`

### Priority Definitions

#### P1 — Critical Incident
- **Definition:** The platform is unavailable, or a critical business process is completely blocked.
- **Examples:** Complete system outage · Login unavailable for all users · AI workflows non-functional · Data inaccessible
- **Response Time:** Within 1 Hour
- **Target Resolution Time:** Within 4 Business Hours
- **Escalation:** Immediate notification to the Engineering Lead

#### P2 — High Priority
- **Definition:** Major functionality is impacted, but a workaround may exist.
- **Examples:** Report generation failures · Significant workflow issues · Performance degradation · Integration failures
- **Response Time:** Within 4 Business Hours
- **Target Resolution Time:** Within 1 Business Day
- **Escalation:** Engineering Lead notified

#### P3 — Medium Priority
- **Definition:** Non-critical issue impacting a limited number of users or functionality.
- **Examples:** Configuration issues · User access issues · Minor defects · Training assistance
- **Response Time:** Within 1 Business Day
- **Target Resolution Time:** Within 3 Business Days
- **Escalation:** As required

#### P4 — Low Priority
- **Definition:** General inquiries, enhancement requests, or cosmetic issues.
- **Examples:** How-to questions · Enhancement requests · Minor UI issues · Documentation requests
- **Response Time:** Within 2 Business Days
- **Target Resolution Time:** Best effort
- **Escalation:** Not required

### Enhancement Requests

Enhancement requests **do not** fall under support SLAs.

**Process:**
1. Logged into Zoho Desk
2. Reviewed by Head of Delivery & Customer Success
3. Assessed for business value and roadmap alignment
4. Prioritised during Product Review meetings
5. Approved enhancements moved into the GitHub backlog

**Customer Status:** *Logged for Product Review.* No delivery commitment is made until
approved and prioritised.

### Customer Communication Standards

- Every ticket receives an acknowledgement.
- Customers receive updates every **12 hours** for open **P1/P2** tickets.
- Customers receive **weekly** status updates for enhancement requests.
- No ticket is closed without customer confirmation **or 5 business days of inactivity**.
- All customer requests — regardless of source (email, meeting, phone, Teams, Slack,
  founder conversation) — **must be logged in Zoho Desk**.
