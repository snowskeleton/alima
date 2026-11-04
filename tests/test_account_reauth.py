"""Re-authenticating an Audible account onto a freshly registered device.

Background: mkb79/Audible#909. Devices registered with the old iPhone profile
(32-character serial) get their download licenses denied, so existing accounts
have to be re-registered. Re-auth swaps the auth file in place and keeps the
account row (and its books). It leaves the old device registered and sets its
auth file aside; a separate endpoint deregisters it when asked.

Amazon is never contacted: ``register``, activation bytes and deregistration are
all patched.
"""

import json

import pytest
from audible import Authenticator

from app.config import settings

OLD_SERIAL = "A" * 32
NEW_SERIAL = "b" * 40


def _auth_data(serial: str, customer: str = "amzn1.account.SAME") -> dict:
    return {
        "website_cookies": {"session-id": "x"},
        # Shaped to pass audible's attribute validators; none of these are real.
        "adp_token": "{enc:x}{key:x}{iv:x}{name:x}{serial:Mg==}",
        "access_token": f"Atna|access-{serial[:4]}",
        "refresh_token": f"Atnr|refresh-{serial[:4]}",
        "device_private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
        "store_authentication_cookie": {"cookie": "x"},
        "device_info": {
            "device_serial_number": serial,
            "device_type": "A2CZJZGLK2JJVM",
            "device_name": "Audible for iPhone",
        },
        "customer_info": {"user_id": customer, "name": "Someone"},
        "expires": 9999999999.0,
        "with_username": False,
    }


@pytest.fixture
def auth_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "audible_auth_path", tmp_path)
    return tmp_path


@pytest.fixture
def amazon(monkeypatch):
    """Stand in for every call that would reach Amazon. Records what happened."""
    calls = {"deregistered": [], "register_data": _auth_data(NEW_SERIAL), "deregister_raises": None}

    def fake_register(**kwargs):
        data = dict(calls["register_data"])
        data.pop("with_username", None)
        return data

    def fake_deregister(self, deregister_all=False):
        if calls["deregister_raises"]:
            raise calls["deregister_raises"]
        calls["deregistered"].append(self.device_info["device_serial_number"])

    monkeypatch.setattr("audible.register.register", fake_register)
    monkeypatch.setattr(Authenticator, "deregister_device", fake_deregister)
    monkeypatch.setattr(Authenticator, "get_activation_bytes", lambda self, *a, **k: "cafef00d")
    return calls


def _write_old_auth(auth_dir, filename, **kw):
    data = {**_auth_data(OLD_SERIAL, **kw), "locale_code": "us", "activation_bytes": "deadbeef"}
    (auth_dir / filename).write_text(json.dumps(data))


def _start_reauth(admin_client, account_id):
    r = admin_client.post("/api/v2/accounts/login/generate-url", json={"account_id": account_id})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _complete(admin_client, session_id):
    return admin_client.post(
        "/api/v2/accounts/login/complete",
        json={
            "session_id": session_id,
            "redirect_url": "https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=CODE",
        },
    )


class TestNeedsReauthFlag:
    def test_old_serial_needs_reauth(self, admin_client, make_account, auth_dir):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path)
        [row] = admin_client.get("/api/v2/accounts").json()["accounts"]
        assert row["needs_reauth"] is True

    def test_current_serial_does_not(self, admin_client, make_account, auth_dir):
        account = make_account()
        (auth_dir / account.auth_file_path).write_text(json.dumps(_auth_data(NEW_SERIAL)))
        [row] = admin_client.get("/api/v2/accounts").json()["accounts"]
        assert row["needs_reauth"] is False

    def test_missing_auth_file_needs_reauth(self, admin_client, make_account, auth_dir):
        make_account()
        [row] = admin_client.get("/api/v2/accounts").json()["accounts"]
        assert row["needs_reauth"] is True


class TestGenerateUrlForReauth:
    def test_unknown_account_is_404(self, admin_client):
        r = admin_client.post("/api/v2/accounts/login/generate-url", json={"account_id": 999999})
        assert r.status_code == 404

    def test_non_integer_account_id_is_400(self, admin_client):
        r = admin_client.post("/api/v2/accounts/login/generate-url", json={"account_id": "1"})
        assert r.status_code == 400

    def test_uses_the_accounts_marketplace(self, admin_client, make_account):
        account = make_account(marketplace="DE")
        r = admin_client.post(
            "/api/v2/accounts/login/generate-url",
            json={"account_id": account.id, "marketplace": "us"},
        )
        assert "amazon.de" in r.json()["oauth_url"]


class TestCompleteReauth:
    def test_swaps_auth_file_and_keeps_old_device_registered(
        self, admin_client, make_account, auth_dir, amazon, test_db
    ):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path)

        r = _complete(admin_client, _start_reauth(admin_client, account.id))

        assert r.status_code == 200, r.text
        assert r.json()["reauthenticated"] is True
        assert r.json()["previous_devices"] == 1
        assert amazon["deregistered"] == []  # decoupled: nothing removed yet

        saved = json.loads((auth_dir / account.auth_file_path).read_text())
        assert saved["device_info"]["device_serial_number"] == NEW_SERIAL
        assert not (auth_dir / (account.auth_file_path + ".new")).exists()
        kept = json.loads((auth_dir / "previous_devices" / f"{account.id}-{OLD_SERIAL}.json").read_text())
        assert kept["device_info"]["device_serial_number"] == OLD_SERIAL

        test_db.refresh(account)
        assert account.activation_bytes == "cafef00d"
        [row] = admin_client.get("/api/v2/accounts").json()["accounts"]
        assert row["needs_reauth"] is False
        assert row["previous_devices"] == 1

    def test_different_amazon_account_is_refused_and_new_device_removed(
        self, admin_client, make_account, auth_dir, amazon
    ):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path, customer="amzn1.account.ALICE")
        amazon["register_data"] = _auth_data(NEW_SERIAL, customer="amzn1.account.BOB")

        r = _complete(admin_client, _start_reauth(admin_client, account.id))

        assert r.status_code == 400
        assert "different Amazon account" in r.json()["detail"]
        # The new, unused device is cleaned up; the old one is untouched.
        assert amazon["deregistered"] == [NEW_SERIAL]
        saved = json.loads((auth_dir / account.auth_file_path).read_text())
        assert saved["device_info"]["device_serial_number"] == OLD_SERIAL

    def test_unreadable_old_auth_file_still_reauths(
        self, admin_client, make_account, auth_dir, amazon
    ):
        account = make_account()
        (auth_dir / account.auth_file_path).write_text("not json")

        r = _complete(admin_client, _start_reauth(admin_client, account.id))

        assert r.status_code == 200, r.text
        assert r.json()["previous_devices"] == 0  # nothing usable to keep
        saved = json.loads((auth_dir / account.auth_file_path).read_text())
        assert saved["device_info"]["device_serial_number"] == NEW_SERIAL

    def test_account_deleted_meanwhile_is_404_and_new_device_removed(
        self, admin_client, make_account, auth_dir, amazon, test_db
    ):
        account = make_account()
        session_id = _start_reauth(admin_client, account.id)
        test_db.delete(account)
        test_db.commit()

        r = _complete(admin_client, session_id)

        assert r.status_code == 404
        assert amazon["deregistered"] == [NEW_SERIAL]

    def test_plain_login_still_creates_a_new_account(
        self, admin_client, auth_dir, amazon, monkeypatch
    ):
        monkeypatch.setattr(Authenticator, "user_profile", lambda self: {"name": "Fresh Person"})
        r = admin_client.post("/api/v2/accounts/login/generate-url", json={"marketplace": "us"})
        r = _complete(admin_client, r.json()["session_id"])

        assert r.status_code == 200, r.text
        assert r.json() == {"success": True, "username": "Fresh Person"}
        assert amazon["deregistered"] == []
        assert (auth_dir / "Fresh Person.json").exists()


def _reauth(admin_client, account):
    r = _complete(admin_client, _start_reauth(admin_client, account.id))
    assert r.status_code == 200, r.text


def _deregister(admin_client, account):
    return admin_client.post(f"/api/v2/accounts/{account.id}/deregister-previous-devices")


class TestDeregisterPreviousDevices:
    def test_deregisters_old_device_and_forgets_it(
        self, admin_client, make_account, auth_dir, amazon
    ):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path)
        _reauth(admin_client, account)

        r = _deregister(admin_client, account)

        assert r.status_code == 200, r.text
        assert r.json() == {"removed": 1, "failed": [], "previous_devices": 0}
        assert amazon["deregistered"] == [OLD_SERIAL]
        assert list((auth_dir / "previous_devices").iterdir()) == []
        # The live registration is untouched.
        saved = json.loads((auth_dir / account.auth_file_path).read_text())
        assert saved["device_info"]["device_serial_number"] == NEW_SERIAL

    def test_failure_keeps_the_file_so_it_can_be_retried(
        self, admin_client, make_account, auth_dir, amazon
    ):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path)
        _reauth(admin_client, account)
        amazon["deregister_raises"] = RuntimeError("amazon said no")

        r = _deregister(admin_client, account)

        assert r.status_code == 200
        body = r.json()
        assert body["removed"] == 0 and body["previous_devices"] == 1
        assert body["failed"] == [{"device": OLD_SERIAL[-6:], "error": "amazon said no"}]

        amazon["deregister_raises"] = None
        assert _deregister(admin_client, account).json()["removed"] == 1

    def test_never_deregisters_the_current_device(
        self, admin_client, make_account, auth_dir, amazon
    ):
        account = make_account()
        (auth_dir / account.auth_file_path).write_text(
            json.dumps({**_auth_data(NEW_SERIAL), "locale_code": "us"})
        )
        stale = auth_dir / "previous_devices" / f"{account.id}-{NEW_SERIAL}.json"
        stale.parent.mkdir()
        stale.write_text((auth_dir / account.auth_file_path).read_text())

        r = _deregister(admin_client, account)

        assert r.json() == {"removed": 0, "failed": [], "previous_devices": 0}
        assert amazon["deregistered"] == []

    def test_unreadable_current_auth_file_touches_nothing(
        self, admin_client, make_account, auth_dir, amazon
    ):
        account = make_account()
        _write_old_auth(auth_dir, account.auth_file_path)
        _reauth(admin_client, account)
        (auth_dir / account.auth_file_path).write_text("garbage")

        r = _deregister(admin_client, account)

        assert r.status_code == 409
        assert amazon["deregistered"] == []

    def test_only_touches_this_accounts_devices(
        self, admin_client, make_account, auth_dir, amazon
    ):
        a, b = make_account(), make_account()
        _write_old_auth(auth_dir, a.auth_file_path)
        _write_old_auth(auth_dir, b.auth_file_path)
        _reauth(admin_client, a)
        _reauth(admin_client, b)

        _deregister(admin_client, a)

        assert (auth_dir / "previous_devices" / f"{b.id}-{OLD_SERIAL}.json").exists()

    def test_unknown_account_is_404(self, admin_client):
        assert admin_client.post(
            "/api/v2/accounts/999999/deregister-previous-devices"
        ).status_code == 404
