"""Runtime inventory of every route the app registers.

The point of this module is that it derives its list from ``app.routes`` rather
than from a hand-maintained fixture. A route added tomorrow shows up in these
tests today, which is what makes the guards in ``test_route_inventory.py``
useful: forgetting an auth dependency fails the suite instead of shipping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from fastapi.routing import APIRoute

from app.main import app

# Dependencies that establish an authenticated caller. A route whose dependency
# tree contains one of these is considered guarded.
AUTH_DEPENDENCIES = frozenset(
    {
        "get_current_user",
        "get_current_active_user",
        "require_admin",
        "get_session_user",
        "require_admin_session",
        "get_api_key_user",
        "require_api_admin",
    }
)

# Dependencies that read the caller when present but permit anonymous access.
OPTIONAL_AUTH_DEPENDENCIES = frozenset({"get_optional_user"})


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    name: str
    auth_dependencies: frozenset[str]
    optional_auth_dependencies: frozenset[str]
    has_response_model: bool

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)

    @property
    def is_guarded(self) -> bool:
        return bool(self.auth_dependencies)

    def __str__(self) -> str:  # keeps pytest ids readable
        return f"{self.method} {self.path}"


def _walk_dependencies(dependant) -> Iterator[str]:
    """Yield the name of every callable in a dependant tree, depth first.

    Recursion matters here: ``get_current_active_user`` is itself built on
    ``get_current_user``, and ``require_admin`` on either. A shallow check would
    miss guards that are only reachable one level down.
    """
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield getattr(sub.call, "__name__", repr(sub.call))
        yield from _walk_dependencies(sub)


def iter_routes() -> Iterator[RouteInfo]:
    """Every APIRoute/method pair the application exposes."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        names = set(_walk_dependencies(route.dependant))
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            yield RouteInfo(
                method=method,
                path=route.path,
                name=route.name,
                auth_dependencies=frozenset(names & AUTH_DEPENDENCIES),
                optional_auth_dependencies=frozenset(
                    names & OPTIONAL_AUTH_DEPENDENCIES
                ),
                has_response_model=route.response_model is not None,
            )


ALL_ROUTES = sorted(iter_routes(), key=lambda r: (r.path, r.method))


# ---------------------------------------------------------------------------
# Path parameter filling
# ---------------------------------------------------------------------------

_PARAM_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]+)?\}")

# Values chosen so the request reaches the auth layer and stops there. They only
# need to satisfy FastAPI's path-parameter coercion; nothing should exist under
# these ids, because an auth check that runs *after* a 404 lookup is exactly the
# ordering bug these tests are meant to catch.
_PARAM_VALUES = {
    "book_id": "1",
    "feed_id": "1",
    "user_id": "1",
    "key_id": "1",
    "queue_id": "1",
    "account_id": "1",
    "audit_id": "1",
    "job_id": "1",
    "slug": "inventory-probe",
    "filename": "inventory-probe.m4b",
    "filepath": "inventory-probe.jpg",
    "ext": "m4b",
    "full_path": "inventory-probe",
}


def concrete_path(path: str) -> str:
    """Substitute placeholder values for path parameters."""

    def replace(match: re.Match[str]) -> str:
        param = match.group(1)
        if param not in _PARAM_VALUES:
            raise KeyError(
                f"No placeholder value for path parameter {param!r} in {path!r}. "
                f"Add one to _PARAM_VALUES in tests/route_inventory.py."
            )
        return _PARAM_VALUES[param]

    return _PARAM_RE.sub(replace, path)
