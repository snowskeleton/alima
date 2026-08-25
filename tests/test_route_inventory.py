"""Guards that apply to every route, derived from the live routing table.

These tests exist because the per-router test files can only cover routes
somebody remembered to write a test for. Everything here is parametrised over
``app.routes``, so a new endpoint is subject to the same rules the moment it is
registered — and an endpoint that forgets its auth dependency fails CI rather
than shipping.

When you add a genuinely public route, add it to ``PUBLIC_ROUTES`` below with a
comment saying why. That edit is the point: making a route public should be a
deliberate, reviewable act.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.route_inventory import ALL_ROUTES, RouteInfo, concrete_path

# Routes that intentionally serve anonymous callers.
#
# Each entry is (METHOD, path-as-registered). Anything not listed here must
# carry an authentication dependency.
PUBLIC_ROUTES: set[tuple[str, str]] = {
    # --- Infrastructure ---
    ("GET", "/health"),  # liveness probe for Docker/uptime checks
    ("GET", "/robots.txt"),  # crawler directives; must be readable by crawlers
    ("GET", "/"),  # entry point, redirects based on session state
    ("GET", "/api"),  # API index, advertises the OpenAPI document
    ("GET", "/{full_path:path}"),  # SPA catch-all; the app itself gates its views
    # --- Authentication, which cannot require authentication ---
    ("POST", "/api/v2/auth/login"),  # requests a magic link
    ("POST", "/api/v2/auth/register"),  # first-user bootstrap
    ("GET", "/api/v2/auth/magic-link"),  # the magic-link token *is* the credential
    ("POST", "/api/v2/auth/logout"),  # clearing a cookie needs no proof of identity
    ("GET", "/api/v2/auth/status"),  # reports whether anyone is logged in
    # --- Public podcast surface ---
    # Podcast players cannot authenticate, so these are public by design and
    # enforce their own per-feed `is_public` check instead.
    ("GET", "/feed/{slug}.xml"),
    ("GET", "/feeds/{slug}.xml"),
    ("GET", "/feed/{slug}.xml/preview"),
    ("GET", "/feeds/{slug}.xml/preview"),
    ("GET", "/files/audiobooks/{book_id}.{ext}"),  # RSS enclosure target
    ("GET", "/files/covers/{filepath:path}"),  # artwork referenced from feeds
}

# Routes that read the caller opportunistically but must still serve anonymous
# requests. Listed separately so the distinction stays visible.
OPTIONAL_AUTH_ROUTES: set[tuple[str, str]] = {
    ("GET", "/api/v2/feeds/by-slug/{slug}"),  # public feeds resolve for anyone
}

# Responses that all count as "you are not authenticated". The app answers JSON
# clients with 401/403 and browser navigations with a redirect to the login page.
UNAUTHENTICATED_STATUSES = {401, 403, 303, 307}


def _ids(route: RouteInfo) -> str:
    """pytest calls this once per parameter, so it takes a single route."""
    return str(route)


GUARDED_ROUTES = [
    r
    for r in ALL_ROUTES
    if r.key not in PUBLIC_ROUTES and r.key not in OPTIONAL_AUTH_ROUTES
]


def test_inventory_is_not_empty():
    """A refactor that breaks route discovery must not silently pass everything."""
    assert len(ALL_ROUTES) > 50, (
        f"Only discovered {len(ALL_ROUTES)} routes; route introspection is "
        "probably broken, which would make every other test in this file vacuous."
    )
    assert len(GUARDED_ROUTES) > 40


def test_allowlists_have_no_stale_entries():
    """Every allowlisted route still exists.

    Without this, deleting a route leaves a permanent hole in the allowlist that
    a future route at the same path would silently fall into.
    """
    live = {r.key for r in ALL_ROUTES}
    stale = (PUBLIC_ROUTES | OPTIONAL_AUTH_ROUTES) - live
    assert not stale, (
        f"These routes are allowlisted but no longer registered: {sorted(stale)}. "
        "Remove them from tests/test_route_inventory.py."
    )


# ---------------------------------------------------------------------------
# Static guarantees: what the route *declares*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", GUARDED_ROUTES, ids=_ids)
def test_route_declares_an_auth_dependency(route: RouteInfo):
    """Every non-public route depends on something that authenticates the caller."""
    assert route.is_guarded, (
        f"{route} has no authentication dependency. Add one of the guards from "
        f"app/dependencies.py, or — if this route is genuinely public — add it to "
        f"PUBLIC_ROUTES in this file with a comment explaining why."
    )


@pytest.mark.parametrize(
    "route",
    [r for r in ALL_ROUTES if r.key in OPTIONAL_AUTH_ROUTES],
    ids=_ids,
)
def test_optional_auth_routes_use_the_optional_guard(route: RouteInfo):
    """Optional-auth routes resolve the user without requiring one."""
    assert route.optional_auth_dependencies, (
        f"{route} is listed in OPTIONAL_AUTH_ROUTES but does not depend on "
        "get_optional_user."
    )
    assert not route.auth_dependencies, (
        f"{route} is listed in OPTIONAL_AUTH_ROUTES but uses a hard guard "
        f"({sorted(route.auth_dependencies)}); it would reject anonymous callers."
    )


# ---------------------------------------------------------------------------
# Behavioural guarantees: what the route actually *does*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", GUARDED_ROUTES, ids=_ids)
def test_route_rejects_anonymous_requests(client: TestClient, route: RouteInfo):
    """An unauthenticated call is refused before any work happens.

    Note the placeholder ids in route_inventory.py point at nothing. A 404 here
    means the handler looked the record up *before* checking who was asking,
    which leaks existence to anonymous callers.
    """
    response = client.request(
        route.method,
        concrete_path(route.path),
        follow_redirects=False,
        headers={"Accept": "application/json"},
    )
    assert response.status_code in UNAUTHENTICATED_STATUSES, (
        f"{route} answered an anonymous request with {response.status_code}, "
        f"expected one of {sorted(UNAUTHENTICATED_STATUSES)}."
    )


@pytest.mark.parametrize("route", GUARDED_ROUTES, ids=_ids)
def test_route_rejects_invalid_api_key(client: TestClient, route: RouteInfo):
    """A bad bearer token is refused, and never falls through to anonymous access.

    This is the regression guard for the optional-auth bug fixed in 50f8b01: a
    presented-but-invalid key must fail loudly rather than being treated as
    "no credentials supplied".
    """
    response = client.request(
        route.method,
        concrete_path(route.path),
        follow_redirects=False,
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer not-a-real-api-key",
        },
    )
    assert response.status_code in UNAUTHENTICATED_STATUSES, (
        f"{route} answered a request bearing an invalid API key with "
        f"{response.status_code}, expected one of "
        f"{sorted(UNAUTHENTICATED_STATUSES)}."
    )


# Public routes split by whether they consult the caller's credentials at all.
# Only the ones that do can meaningfully "reject" a bad key; /health and the
# static routes never look at the Authorization header, and shouldn't.
CREDENTIAL_CONSULTING_PUBLIC_ROUTES = [
    r
    for r in ALL_ROUTES
    if r.key in PUBLIC_ROUTES | OPTIONAL_AUTH_ROUTES
    and (r.auth_dependencies or r.optional_auth_dependencies)
]

CREDENTIAL_IGNORING_ROUTES = [
    r
    for r in ALL_ROUTES
    if r.key in PUBLIC_ROUTES
    and not (r.auth_dependencies or r.optional_auth_dependencies)
]


@pytest.mark.parametrize("route", CREDENTIAL_CONSULTING_PUBLIC_ROUTES, ids=_ids)
def test_optional_auth_route_rejects_invalid_api_key(
    client: TestClient, route: RouteInfo
):
    """A public route that reads credentials must still reject bad ones.

    This is the regression guard for 50f8b01. `get_optional_user` is allowed to
    return None when no credentials are presented, but a caller who presents a
    *wrong* key must be told so rather than silently downgraded to anonymous --
    otherwise a revoked or expired key looks like it is still working.
    """
    response = client.request(
        route.method,
        concrete_path(route.path),
        follow_redirects=False,
        headers={"Authorization": "Bearer not-a-real-api-key"},
    )
    assert response.status_code in UNAUTHENTICATED_STATUSES, (
        f"{route} served a request bearing an invalid API key with "
        f"{response.status_code}; an invalid credential should be rejected, not "
        "silently downgraded to anonymous access."
    )


@pytest.mark.parametrize("route", CREDENTIAL_IGNORING_ROUTES, ids=_ids)
def test_credential_ignoring_route_survives_a_bogus_header(
    client: TestClient, route: RouteInfo
):
    """Routes that ignore credentials must not crash when sent one.

    These legitimately answer normally with a junk Authorization header -- they
    never inspect it. All that is asserted is that parsing one doesn't 500.
    """
    response = client.request(
        route.method,
        concrete_path(route.path),
        follow_redirects=False,
        headers={"Authorization": "Bearer not-a-real-api-key"},
    )
    assert response.status_code < 500, (
        f"{route} returned {response.status_code} when sent a junk "
        "Authorization header."
    )
