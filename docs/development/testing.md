# Testing

Alima has four test layers. Each catches something the others structurally
cannot, which is why all four exist.

| Layer | Location | Runtime | Catches |
|---|---|---|---|
| Backend unit/contract | `tests/` | ~30s | Handler logic, permissions, service decisions |
| Route inventory | `tests/test_route_inventory.py` | <1s | Endpoints added without auth |
| Schema fuzzing | `tests/test_openapi_fuzz.py` | ~20s | Unhandled 500s, schema drift |
| Frontend unit | `frontend/src/**/*.test.tsx` | ~1s | Component and API-client behaviour |
| End-to-end | `e2e/` | ~4s | The SPA and the API disagreeing |

## Setup

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

```bash
npm ci && npm --prefix frontend ci
```

Test tooling lives in `requirements-dev.txt`, deliberately separate from
`requirements.txt` — the Dockerfile installs only the latter, so none of it
ships in the production image.

## Running the tests

**Backend.** Always pass a SQLite `DATABASE_URL`:

```bash
DATABASE_URL="sqlite:///$PWD/.pytest-scratch.db" .venv/bin/python -m pytest tests/ -q
```

The override is not optional locally. `.env` points `DATABASE_URL` at a
Docker-internal hostname that does not resolve from a laptop, and any test
touching `get_cached_setting()` opens a real session and blocks on connect with
no timeout — so pytest hangs indefinitely with zero output rather than failing.
It reads as a hang in the code under test, and it is not.

**Frontend:**

```bash
npm --prefix frontend test
```

**End-to-end** (builds the SPA and starts a server automatically):

```bash
npx playwright test
```

**Everything, with coverage:**

```bash
DATABASE_URL="sqlite:///$PWD/.pytest-scratch.db" .venv/bin/python -m pytest tests/ --cov=app --cov-report=term-missing
```

## The layers in detail

### Route inventory

`tests/test_route_inventory.py` parametrises over `app.routes` at runtime rather
than over a hand-maintained list. Every registered route must declare an
authentication dependency, refuse anonymous callers, and refuse an invalid API
key.

This means **a new endpoint is covered the moment it is registered**. If you add
a route and forget its `Depends(get_current_active_user)`, three tests fail
before it can ship.

When a route genuinely should be public, add it to `PUBLIC_ROUTES` in that file
with a comment saying why. That edit is the point: making an endpoint public
becomes a deliberate, reviewable decision rather than an omission.

### Schema fuzzing

`tests/test_openapi_fuzz.py` drives [Schemathesis](https://schemathesis.io) from
the app's own `/openapi.json`. It generates inputs matching each operation's
declared types and asserts no schema-valid input produces a 500, plus that
response bodies match their declared models.

This found eight input-validation crashes on its first run. It is good at
*finding* that class of bug and poor at *guarding* against it, since generation
is random — so anything it finds gets a deterministic regression test in
`tests/test_input_validation.py`.

Status-code conformance is split into a separately-marked test, deselected by
default, because the app returns many undocumented-but-correct codes:

```bash
pytest -m openapi_docs      # see what the OpenAPI document fails to declare
```

To fix those, add `responses={...}` to the route decorators.

Excluding an operation from fuzzing requires adding it to `EXCLUDED_PATHS`
*with a reason* — every entry there is a piece of API surface nothing is
checking.

### Frontend

Vitest + Testing Library + MSW. MSW mocks at the **network boundary**, not at
the API client, so `src/api/client.ts` — the CSRF header, the 401 redirect, the
error unwrapping — runs for real in every page test. Stubbing the client would
leave the one layer every page depends on untested.

`setup.ts` sets `onUnhandledRequest: 'error'`, so `src/test/handlers.ts` is an
accurate record of what the frontend calls: a page that starts fetching
something new fails until its handler is written.

Test pages, not `ui/` primitives. `Button` renders a button; that is not worth a
test. Whether the library page distinguishes "your search matched nothing" from
"your library is empty" is.

### End-to-end

Playwright against a real browser, a real server, and a real database.
`scripts/e2e-server.sh` builds the SPA, creates a scratch SQLite database under
`.e2e/`, and starts uvicorn against it — it never touches your configured
`DATABASE_URL`, and it recreates the database on every start, which is what lets
the auth specs exercise the first-run registration flow.

Magic-link tokens are read straight out of that scratch database by
`e2e/helpers.ts`. A test-only endpoint returning the newest token would be
tidier, but it would put a credential-disclosure route in the real application,
one misconfiguration away from a full authentication bypass.

**Keep this suite small.** It is the slowest layer and the one that rots
fastest. It covers flows that must never break — register, log in, create a
feed, serve the RSS — not the coverage the unit suites already provide. Drive
state through the API and use the browser only for the flow actually under test;
scraping ids out of list markup makes specs fail on markup changes, which is
noise rather than signal.

## Coverage

Two gates run in CI:

- **`--cov-fail-under=48`** — a ratchet. It exists to stop backsliding, not as a
  target. Raise it when coverage rises; never lower it.
- **`diff-cover --fail-under=80`** — the one that matters. It gates the lines
  *changed in the pull request*.

Total coverage is a poor signal: it barely moves and nobody acts on it. "You
added 40 lines and 12 are untested, here they are" is actionable. Legacy gaps
stay legal; new gaps do not.

Check your own diff before pushing:

```bash
.venv/bin/diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
```

### What is not worth covering

`audible_sync`, `book_download`, `email_service` and `b2_upload` are mostly
network I/O, and chasing coverage through them buys brittle tests. Extract the
pure decision logic — matching heuristics, path building, staleness checks — and
test that hard, as `tests/test_service_logic.py` does. Leave the transport in a
thin mocked shell.

The rule of thumb: a download that fails, fails loudly. A matcher that scores
the wrong book quietly attaches the file to it. Test the second kind.

## Writing tests

Use the factory fixtures in `conftest.py` — `make_book`, `make_feed`,
`make_account`, `make_queue_entry` — rather than fixed instances. Most tests
need several objects differing in one attribute, and a shared instance forces
tests to mutate state to say what they mean.

Clients: `client` (anonymous), `authenticated_client` (regular user),
`admin_client` (admin). For cross-tenant permission tests, `second_user` gives
you somebody else's account.

Assert the permission boundary endpoint by endpoint, not once per router. Feeds
enforced ownership on five endpoints and not on the sixth, and a single
"feeds check ownership" test would have passed anyway.

## Databases

The suite runs on in-memory SQLite by default. Set `TEST_DATABASE_URL` to run it
against PostgreSQL, which is what production uses:

```bash
TEST_DATABASE_URL=postgresql://alima:alima@localhost:5432/alima_test .venv/bin/python -m pytest tests/ -q
```

CI runs both. SQLite and Postgres disagree about constraint timing, JSON
columns, integer width and case sensitivity, so a suite that only ever sees
SQLite will miss real bugs. SQLite needs `PRAGMA foreign_keys=ON` to enforce
foreign keys at all; the fixture sets it so the SQLite runs stay honest about
`ON DELETE CASCADE`.

## CI

`.github/workflows/ci.yml` runs four jobs on every push and pull request:
backend on SQLite (with the coverage gates), backend on PostgreSQL, frontend
(typecheck, test, build), and end-to-end. E2E is a separate job so browsers
never hold up the fast suites.

Failed E2E runs upload their Playwright report, traces, and video as artifacts:

```bash
npx playwright show-trace test-results/<test-name>/trace.zip
```
