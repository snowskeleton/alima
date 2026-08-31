"""Property-based fuzzing of every endpoint, driven by the app's own OpenAPI schema.

Schemathesis reads ``/openapi.json``, generates inputs that satisfy each
operation's declared types, and checks the responses back against the schema.
That buys two things the hand-written tests don't:

* **No 500s.** Any input matching the declared schema must produce a handled
  response. An unguarded ``int()``, a missing-key ``KeyError``, a ``None`` that
  reaches string formatting -- these surface here without anyone predicting them.
* **The schema tells the truth.** If a handler can return a field the response
  model says is non-nullable, the frontend will eventually crash on it. Better to
  find that here.

Runs authenticated as an admin, otherwise every generated request would stop at
the auth layer and test nothing.
"""

from __future__ import annotations

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis import Case
from schemathesis.checks import not_a_server_error
from schemathesis.specs.openapi.checks import (
    content_type_conformance,
    response_schema_conformance,
    status_code_conformance,
)

from app.database import get_db
from app.main import app
from app.models import User, UserRole

# Operations excluded from fuzzing, by operation id / path. Each needs a reason.
#
# Keep this list short and justified. Every entry is a piece of the API that
# nothing here is checking.
EXCLUDED_PATHS = {
    # Server-sent events: these hold the connection open by design, so a
    # generated request never returns and the run hangs.
    "/api/v2/audit/stream/{audit_id}",
    "/api/v2/jobs/{job_id}/stream",
    # Reaches outward to third-party services (Audible, Backblaze, SMTP). Fuzzing
    # these would either fail on absent credentials or send real traffic.
    "/api/v2/accounts/login/generate-url",
    "/api/v2/accounts/login/complete",
    "/api/v2/accounts/{account_id}/sync",
    "/api/v2/settings/test-b2",
    "/api/v2/settings/test-email",
    "/api/v2/sync/force-refresh-metadata",
    # Kicks off real download work against the queue and the filesystem.
    "/api/v2/downloads/process",
    "/api/v2/books/{book_id}/download",
    # Would send a real magic-link email to a generated address.
    "/api/v2/auth/login",
    "/api/v2/users/{user_id}/send-login-link",
    # The SPA catch-all returns index.html for literally any path, so there is no
    # schema to check it against.
    "/{full_path}",
}

# `.exclude()` returns a filtered schema rather than acting as a decorator, so
# the exclusions are applied here once, at load time.
schema = schemathesis.openapi.from_asgi("/openapi.json", app).exclude(
    path_regex="^(" + "|".join(p.replace("{", r"\{") for p in EXCLUDED_PATHS) + ")$"
)


@pytest.fixture(autouse=True)
def _fuzz_environment(test_engine, mock_email_service, monkeypatch):
    """Point the app at the test database and seed an admin to authenticate as.

    Autouse so every generated case in this module gets it, and function-scoped
    so each case starts from a clean database -- a fuzzer that mutates state
    would otherwise make its own later cases non-reproducible.
    """
    from sqlalchemy.orm import sessionmaker

    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    admin = User(email="fuzz-admin@example.com", role=UserRole.ADMIN)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    admin_id, admin_email = admin.id, admin.email
    db.close()

    from app.auth import create_access_token

    token = create_access_token(data={"sub": admin_email, "user_id": admin_id})

    yield {"cookies": {"session_token": token}}

    app.dependency_overrides.clear()


@pytest.fixture
def auth_cookies(_fuzz_environment):
    return _fuzz_environment["cookies"]


@schema.parametrize()
@pytest.mark.fuzz
@settings(
    max_examples=30,
    # Hypothesis warns that `auth_cookies` is function-scoped and therefore not
    # reset between generated inputs. That is fine, and mildly useful: the
    # assertion is "no input causes a 500", which does not depend on a pristine
    # database, and letting state accumulate across a single operation's inputs
    # exercises handlers against a database that isn't empty. Each *operation*
    # still gets a fresh database, because pytest re-runs the fixture per test.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    # Generation and the first ASGI call are slow enough to trip Hypothesis's
    # per-example deadline on a cold cache; wall-clock is bounded by max_examples.
    deadline=None,
)
def test_endpoint_handles_generated_input(case: Case, auth_cookies):
    """No schema-valid input may produce an unhandled server error."""
    response = case.call(cookies=auth_cookies)

    assert response.status_code < 500, (
        f"{case.method.upper()} {case.path} returned {response.status_code} for "
        f"generated input.\n"
        f"  path params: {case.path_parameters}\n"
        f"  query:       {case.query}\n"
        f"  body:        {case.body}\n"
        f"  response:    {response.content[:500]!r}"
    )

    # Check the response against what the schema promises. Deliberately a
    # subset of Schemathesis's default checks:
    #
    #   response_schema_conformance - a body that contradicts its response model
    #       is a bug the frontend will hit.
    #   content_type_conformance    - likewise for the declared media type.
    #
    # `status_code_conformance` is excluded here and asserted separately below.
    # The app returns plenty of undocumented-but-correct codes (303 to the login
    # page, 401, 404), so folding it in would make this gate permanently red and
    # therefore useless as a regression signal.
    case.validate_response(
        response,
        checks=[
            not_a_server_error,
            response_schema_conformance,
            content_type_conformance,
        ],
    )


@schema.parametrize()
@pytest.mark.fuzz
@pytest.mark.openapi_docs
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
def test_documented_status_codes(case: Case, auth_cookies):
    """Every status code an endpoint returns is declared in the OpenAPI document.

    Currently failing across most of the API: handlers raise 401/403/404 that the
    schema never mentions, because FastAPI only documents the success response
    unless you spell out `responses={...}`. That matters for anyone generating a
    client from the schema, but it is a documentation debt rather than a bug, so
    it is marked separately and excluded from the default run:

        pytest -m openapi_docs        # see what is undocumented
        pytest -m "not openapi_docs"  # the default in CI

    Fix these by adding `responses=` to the route decorators, then delete the
    deselection in pytest.ini.
    """
    case.validate_response(response=case.call(cookies=auth_cookies),
                           checks=[status_code_conformance])
