# REST API

Alima's HTTP API is self-describing. Everything below is also available
programmatically from the running server:

| What | Where |
| --- | --- |
| Discovery index | `GET /api` |
| OpenAPI 3.1 schema | `GET /openapi.json` |
| Swagger UI | `GET /docs` |
| ReDoc | `GET /redoc` |

`GET /api` and the schema endpoints need no authentication, so a client can
bootstrap itself:

```bash
curl -s https://your-alima-host/api | jq
curl -s https://your-alima-host/openapi.json > alima-openapi.json
```

## Authentication

Every authenticated endpoint accepts **either** credential:

1. **API key** — `Authorization: Bearer <key>`. This is the option for scripts,
   agents, and anything that isn't a browser.
2. **Session cookie** — `session_token`, the JWT issued to browsers after a
   magic-link login. The web frontend uses this.

An API key inherits the role of the user who created it, so admin-only routes
(users, settings, downloads, logs) need a key owned by an admin.

### Creating a key

In the web UI: **Settings → API keys**. The dialog shows the raw key once — only
its SHA-256 hash is stored — and optionally takes an expiry in days.

!!! warning "Key management is session-only"

    `GET`, `POST`, and `DELETE` on `/api/v2/api-keys` accept a **browser session
    cookie only**, never a bearer key. This is deliberate: if a key could mint
    keys, a leaked key could issue itself a permanent replacement that survives
    revoking the original. Creating, listing, and revoking keys requires a
    logged-in admin. An API key presented to these routes gets a `401`.

### Expiry and usage

Each key carries two optional timestamps:

* `expires_at` — `null` means the key never expires. Pass `expires_in_days` when
  creating a key to set one. Requests with an expired key get
  `401 Expired API key`.
* `last_used_at` — `null` means the key has never authenticated a request, so
  you can spot keys that were issued and forgotten. It is refreshed at most once
  a minute per key, so a busy key does not cause a database write per request.

Keys created before these columns existed have `null` for both: they have no
recorded usage and never expire, exactly as they behaved before.

### Using a key

```bash
KEY=...
curl -H "Authorization: Bearer $KEY" https://your-alima-host/api/v2/books
curl -X DELETE -H "Authorization: Bearer $KEY" https://your-alima-host/api/v2/feeds/3
```

### Failure modes

| Situation | Response |
| --- | --- |
| No credentials on `/api/**` | `401` with a JSON body |
| Unknown or malformed bearer key | `401` (never falls back to a cookie) |
| Valid credentials, insufficient role | `403` |
| No credentials on a browser page request | `303` redirect to `/auth/login` |

The redirect only applies to HTML page requests. Anything under `/api/`, or any
request sending `Authorization` or `Accept: application/json`, gets a `401`
instead — so a programmatic client never has to interpret a login page.

## API surface

* `/api/v2/**` — the primary API. Books, feeds, downloads, jobs, accounts,
  users, settings, logs, audit, matching, and imports. Used by the web
  frontend and available to API-key clients.
* `/api/v1/**` — a small legacy external API for book import. API-key only.
* `/feed/{slug}.xml`, `/files/**` — public RSS and media endpoints,
  authenticated by unguessable slug rather than by user.

Consult `/openapi.json` for the exact request and response shape of every
route; it is generated from the code, so it cannot drift.
