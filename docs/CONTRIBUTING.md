# Contributing & Coding Standards

How we work on the Zenalyst Support Intelligence Layer. Keep it simple, keep `main`
always-working.

## Branching

- `main` is the stable, always-working branch. **Never commit directly to `main`.**
- Do all work on a **feature branch** off `main`, named `<type>/<short-description>`:

  | prefix      | use for                                   | example                     |
  |-------------|-------------------------------------------|-----------------------------|
  | `feat/`     | a new feature                             | `feat/needs-review-view`    |
  | `fix/`      | a bug fix                                  | `fix/redirect-missing-target` |
  | `docs/`     | docs only                                 | `docs/contributing`         |
  | `chore/`    | tooling, deps, config                     | `chore/bump-deps`           |
  | `refactor/` | code change with no behaviour change      | `refactor/extract-mapping`  |
  | `test/`     | adding or fixing tests                    | `test/mapping-cases`        |

## Commits — Conventional Commits

Format: `type(scope): subject` in the imperative mood. Keep the subject under ~72 chars;
put the *why* in the body if it isn't obvious.

```
feat(mapping): write exact P1-P4 into Zoho priority field

Zoho's default High/Medium/Low collapses P1 and P2. Writing the exact
level keeps them distinct and filterable in the UI.
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`, `perf`.

## Pull Requests

1. Push your branch: `git push -u origin <branch>`.
2. Open a PR on GitHub against `main`. Give it a clear title and a short body:
   *what changed* and *why*.
3. Self-review the diff before merging. (Optionally run a code review on it.)
4. Merge, then delete the branch.
5. Locally: `git checkout main && git pull`.

Keep PRs **small and focused** — one logical change each. Easier to review, easier to revert.

## Secrets

- **Never commit `.env`** or any credential. It is gitignored.
- `.env.example` is the committed template — update it when you add a new variable.
- Local-only state (`processed_ids.json`, `audit.jsonl`) is gitignored too.

## Architecture rules (don't break these)

- The **classifier knows nothing about Zoho**; Zoho specifics live in `zoho_client.py` /
  `mapping.py`. Keep that separation.
- The **trigger is isolated** (`poller.py` today; a webhook receiver later). The rest of the
  system must not care which one is firing.
- **Nothing is ever auto-closed.** The lowest action is `review`. Low-confidence results are
  downgraded to `review` automatically.

## Before you push

- Run the test suite: `python -m pytest` (install dev deps once with
  `pip install -r requirements-dev.txt`). All tests must pass.
- Never run the poller **live** before a `python src/poller.py --dry-run --once` looks right.

## Project layout

```
src/    application modules (classifier, mapping, zoho_client, poller, audit, demo)
tests/  pytest unit tests
docs/   README and this guide
run_poller.bat   Task Scheduler entry point (stays at repo root)
```
