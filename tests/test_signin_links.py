"""Shareable Audible sign-in links (device-code login, no Alima login needed).

Amazon is never contacted. The flow tests patch the device-code service; the
service tests fake Amazon at the httpx layer.
"""

import json
from datetime import datetime, timedelta

import httpx
import pytest

from app.models import AudibleSigninLink
from app.services import audible_device_code as device_code
from tests.test_account_reauth import (  # noqa: F401  (fixtures)
    NEW_SERIAL,
    OLD_SERIAL,
    _auth_data,
    _write_old_auth,
    amazon,
    auth_dir,
)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.routers.api_v2.signin_links import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def fake_amazon_codes(monkeypatch):
    """Device-code service stand-in. Set ``state["confirmed"]`` to finish."""
    state = {"codes": 0, "checks": 0, "confirmed": False, "error": None,
             "register_data": _auth_data(NEW_SERIAL)}

    def create_code_pair(domain):
        state["codes"] += 1
        state["domain"] = domain
        return device_code.CodePair(
            serial=NEW_SERIAL, public_code=f"CODE{state['codes']}",
            private_code="private", expires_in=600, poll_interval=5,
        )

    def try_register(domain, serial, public_code, private_code):
        state["checks"] += 1
        if state["error"]:
            raise device_code.DeviceCodeError(state["error"])
        if not state["confirmed"]:
            return None
        data = dict(state["register_data"])
        data.pop("with_username", None)
        return data

    monkeypatch.setattr(device_code, "create_code_pair", create_code_pair)
    monkeypatch.setattr(device_code, "try_register", try_register)
    return state


def _create_link(admin_client, **body):
    r = admin_client.post("/api/v2/signin-links", json=body)
    assert r.status_code == 200, r.text
    return r.json()["path"].removeprefix("/signin/")


def _rewind_poll(test_db):
    """Let the next poll through the server-side poll interval."""
    for link in test_db.query(AudibleSigninLink).all():
        if link.last_poll_at:
            link.last_poll_at -= timedelta(minutes=1)
    test_db.commit()


class TestCreateLink:
    def test_requires_admin(self, authenticated_client):
        r = authenticated_client.post("/api/v2/signin-links", json={"marketplace": "us"})
        assert r.status_code in (401, 403)

    def test_stores_only_a_hash_of_the_token(self, admin_client, test_db):
        token = _create_link(admin_client, marketplace="de")
        link = test_db.query(AudibleSigninLink).one()
        assert token not in link.token_hash and len(link.token_hash) == 64
        assert link.marketplace == "de" and link.account_id is None

    def test_reauth_link_takes_the_accounts_marketplace(self, admin_client, make_account, auth_dir, test_db):
        account = make_account(marketplace="UK")
        _write_old_auth(auth_dir, account.auth_file_path)
        _create_link(admin_client, account_id=account.id, marketplace="us")
        link = test_db.query(AudibleSigninLink).one()
        assert (link.account_id, link.marketplace) == (account.id, "uk")

    def test_refuses_pre_amazon_accounts(self, admin_client, make_account, auth_dir):
        account = make_account()
        data = {**_auth_data(OLD_SERIAL), "locale_code": "us", "with_username": True}
        (auth_dir / account.auth_file_path).write_text(json.dumps(data))
        r = admin_client.post("/api/v2/signin-links", json={"account_id": account.id})
        assert r.status_code == 400 and "Pre-Amazon" in r.json()["detail"]

    def test_unknown_account_and_marketplace(self, admin_client):
        assert admin_client.post("/api/v2/signin-links", json={"account_id": 999999}).status_code == 404
        assert admin_client.post("/api/v2/signin-links", json={"marketplace": "zz"}).status_code == 400


class TestPublicFlow:
    def test_page_works_without_login_and_never_calls_amazon(self, admin_client, client, fake_amazon_codes):
        token = _create_link(admin_client, marketplace="us")
        client.cookies.clear()
        r = client.get(f"/api/v2/signin-links/{token}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready" and body["code_url"] == "https://www.amazon.com/code"
        assert fake_amazon_codes["codes"] == 0  # link previews don't burn a code

    def test_unknown_token_is_404(self, client):
        assert client.get("/api/v2/signin-links/nope").status_code == 404
        assert client.post("/api/v2/signin-links/nope/poll").status_code == 404

    def test_full_new_account_sign_in(self, admin_client, client, fake_amazon_codes, amazon, auth_dir, test_db, monkeypatch):
        from audible import Authenticator
        monkeypatch.setattr(Authenticator, "user_profile", lambda self: {"name": "Far Away Friend"})
        token = _create_link(admin_client, marketplace="us")

        r = client.post(f"/api/v2/signin-links/{token}/code")
        assert r.json()["status"] == "waiting" and r.json()["code"] == "CODE1"
        # Asking again reuses the live code rather than minting another.
        assert client.post(f"/api/v2/signin-links/{token}/code").json()["code"] == "CODE1"

        assert client.post(f"/api/v2/signin-links/{token}/poll").json()["status"] == "waiting"
        fake_amazon_codes["confirmed"] = True
        _rewind_poll(test_db)
        r = client.post(f"/api/v2/signin-links/{token}/poll")

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "done" and r.json()["username"] == "Far Away Friend"
        assert (auth_dir / "Far Away Friend.json").exists()
        rows = admin_client.get("/api/v2/accounts").json()["accounts"]
        assert [a["username"] for a in rows] == ["Far Away Friend"]

        # Single use: the link reports done and starts nothing new.
        assert client.post(f"/api/v2/signin-links/{token}/code").json()["status"] == "done"
        assert fake_amazon_codes["codes"] == 1

    def test_reauth_link_swaps_the_device(self, admin_client, client, fake_amazon_codes, amazon, make_account, auth_dir, test_db):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path)
        token = _create_link(admin_client, account_id=account.id)
        assert client.get(f"/api/v2/signin-links/{token}").json()["account_name"] == account.username

        client.post(f"/api/v2/signin-links/{token}/code")
        fake_amazon_codes["confirmed"] = True
        r = client.post(f"/api/v2/signin-links/{token}/poll")

        assert r.json()["status"] == "done"
        saved = json.loads((auth_dir / account.auth_file_path).read_text())
        assert saved["device_info"]["device_serial_number"] == NEW_SERIAL
        assert amazon["deregistered"] == []  # the old device is left for the admin

    def test_wrong_amazon_account_keeps_link_usable(self, admin_client, client, fake_amazon_codes, amazon, make_account, auth_dir):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path, customer="amzn1.account.ALICE")
        fake_amazon_codes["register_data"] = _auth_data(NEW_SERIAL, customer="amzn1.account.BOB")
        token = _create_link(admin_client, account_id=account.id)

        client.post(f"/api/v2/signin-links/{token}/code")
        fake_amazon_codes["confirmed"] = True
        r = client.post(f"/api/v2/signin-links/{token}/poll")

        assert r.status_code == 400 and "different Amazon account" in r.json()["detail"]
        assert amazon["deregistered"] == [NEW_SERIAL]
        assert client.get(f"/api/v2/signin-links/{token}").json()["status"] == "ready"

    def test_polls_reach_amazon_at_its_interval_only(self, admin_client, client, fake_amazon_codes):
        token = _create_link(admin_client, marketplace="us")
        client.post(f"/api/v2/signin-links/{token}/code")
        for _ in range(5):
            client.post(f"/api/v2/signin-links/{token}/poll")
        assert fake_amazon_codes["checks"] == 1

    def test_amazon_error_clears_the_code(self, admin_client, client, fake_amazon_codes):
        token = _create_link(admin_client, marketplace="us")
        client.post(f"/api/v2/signin-links/{token}/code")
        fake_amazon_codes["error"] = "Amazon rejected the code (HTTP 400, InvalidValue)."

        r = client.post(f"/api/v2/signin-links/{token}/poll")

        assert r.status_code == 502 and "Get a new code" in r.json()["detail"]
        assert client.get(f"/api/v2/signin-links/{token}").json()["status"] == "ready"

    def test_expired_code_offers_a_new_one(self, admin_client, client, fake_amazon_codes, test_db):
        token = _create_link(admin_client, marketplace="us")
        client.post(f"/api/v2/signin-links/{token}/code")
        link = test_db.query(AudibleSigninLink).one()
        link.code_expires_at = datetime.utcnow() - timedelta(seconds=1)
        test_db.commit()

        body = client.get(f"/api/v2/signin-links/{token}").json()
        assert body["status"] == "ready" and body["code_expired"] is True
        assert client.post(f"/api/v2/signin-links/{token}/code").json()["code"] == "CODE2"

    def test_expired_link(self, admin_client, client, fake_amazon_codes, test_db):
        token = _create_link(admin_client, marketplace="us")
        link = test_db.query(AudibleSigninLink).one()
        link.expires_at = datetime.utcnow() - timedelta(seconds=1)
        test_db.commit()

        assert client.get(f"/api/v2/signin-links/{token}").json()["status"] == "expired"
        assert client.post(f"/api/v2/signin-links/{token}/code").json()["status"] == "expired"
        assert fake_amazon_codes["codes"] == 0

    def test_deleting_the_account_removes_its_links(self, admin_client, make_account, auth_dir, test_db):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path)
        _create_link(admin_client, account_id=account.id)
        admin_client.delete(f"/api/v2/accounts/{account.id}")
        test_db.expire_all()
        assert test_db.query(AudibleSigninLink).count() == 0


class TestDeviceCodeService:
    """The service against faked Amazon responses."""

    @pytest.fixture
    def amazon_http(self, monkeypatch):
        calls = []
        replies = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append((url, json))
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            status, body = reply
            return httpx.Response(status, json=body)

        monkeypatch.setattr(device_code.httpx, "post", fake_post)
        return calls, replies

    def test_create_code_pair(self, amazon_http):
        calls, replies = amazon_http
        replies.append((200, {"public_code": "AB12C", "private_code": "p", "expires_in": 600,
                              "polling_interval_in_seconds": 5}))
        pair = device_code.create_code_pair("de")
        assert calls[0][0] == "https://api.amazon.de/auth/create/codepair"
        assert pair.public_code == "AB12C" and len(pair.serial) == 40
        assert calls[0][1]["code_data"]["device_serial"] == pair.serial

    def test_create_code_pair_refused(self, amazon_http):
        _, replies = amazon_http
        replies.append((400, {"error": "invalid_request", "error_description": "nope"}))
        with pytest.raises(device_code.DeviceCodeError, match="nope"):
            device_code.create_code_pair("com")

    def test_try_register_pending_states(self, amazon_http):
        _, replies = amazon_http
        replies += [
            (401, {"response": {"error": {"code": "Unauthorized", "message": "not yet"}}}),
            (503, {}),
            httpx.ConnectError("down"),
        ]
        for _ in range(3):
            assert device_code.try_register("com", NEW_SERIAL, "AB12C", "p") is None

    def test_try_register_uses_current_profile_and_parses_success(self, amazon_http):
        calls, replies = amazon_http
        replies.append((200, {"response": {"success": {
            "tokens": {
                "bearer": {"access_token": "Atna|x", "refresh_token": "Atnr|x", "expires_in": "3600"},
                "mac_dms": {"adp_token": "adp", "device_private_key": "key"},
                "website_cookies": [{"Name": "session-id", "Value": '"abc"'}],
            },
            "extensions": {
                "device_info": {"device_serial_number": NEW_SERIAL},
                "customer_info": {"user_id": "amzn1.account.X"},
            },
        }}}))

        data = device_code.try_register("com", NEW_SERIAL, "AB12C", "p")

        sent = calls[0][1]
        assert sent["registration_data"]["app_version"] == "4.60"
        assert sent["registration_data"]["device_serial"] == NEW_SERIAL
        assert sent["auth_data"]["code_pair"] == {"public_code": "AB12C", "private_code": "p"}
        assert data["refresh_token"] == "Atnr|x"
        assert data["website_cookies"] == {"session-id": "abc"}
        assert data["customer_info"]["user_id"] == "amzn1.account.X"

    def test_try_register_rejects_a_different_device(self, amazon_http):
        _, replies = amazon_http
        replies.append((200, {"response": {"success": {
            "tokens": {"bearer": {"access_token": "a", "refresh_token": "r", "expires_in": 3600},
                       "mac_dms": {"adp_token": "x", "device_private_key": "k"}},
            "extensions": {"device_info": {"device_serial_number": "someone-else"}},
        }}}))
        with pytest.raises(device_code.DeviceCodeError, match="different device"):
            device_code.try_register("com", NEW_SERIAL, "AB12C", "p")

    def test_try_register_other_error_raises(self, amazon_http):
        _, replies = amazon_http
        replies.append((400, {"response": {"error": {"code": "InvalidValue", "message": "bad"}}}))
        with pytest.raises(device_code.DeviceCodeError, match="InvalidValue"):
            device_code.try_register("com", NEW_SERIAL, "AB12C", "p")
