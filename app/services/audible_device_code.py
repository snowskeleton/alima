"""Register an Audible device by Amazon device code (amazon.<tld>/code).

The person signs in on Amazon's own site and types a short code; nothing has to
be copied back to us. We create the code pair, then ask Amazon whether it has
been confirmed. Each check is a single request, so the polling loop can live in
the browser and any gunicorn worker can answer it.

Based on mkb79's device-code login (mkb79/Audible#906), which registers with the
same device profile as audible 0.13.1. Does not work for pre-Amazon (username)
accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
# The profile audible 0.13.1 registers with: 40-character serial, app 4.60.
# Reused rather than copied so both login paths always register alike.
from audible._device import APP_VERSION, OS_VERSION, SOFTWARE_VERSION
from audible.login import build_device_serial

DEVICE_TYPE = "A2CZJZGLK2JJVM"
# What the Audible iOS app's web view reports (iOS 26 freezes the OS token).
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)
TOKEN_TYPES = ["bearer", "mac_dms", "website_cookies"]
TIMEOUT = httpx.Timeout(25.0)


class DeviceCodeError(Exception):
    """Amazon refused a step. The message is safe to show the person signing in."""


@dataclass
class CodePair:
    serial: str
    public_code: str
    private_code: str
    expires_in: float
    poll_interval: float


def code_url(domain: str) -> str:
    return f"https://www.amazon.{domain}/code"


def _headers(domain: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "x-amzn-identity-auth-domain": f"api.amazon.{domain}",
    }


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _error(resp: httpx.Response) -> tuple[str | None, str | None]:
    data = _json(resp)
    nested = data.get("response")
    error = data.get("error", nested.get("error") if isinstance(nested, dict) else None)
    if isinstance(error, str):
        desc = data.get("error_description")
        return error, desc if isinstance(desc, str) else None
    if isinstance(error, dict):
        code = next(
            (error[k] for k in ("code", "error_code", "error", "type") if isinstance(error.get(k), str)),
            None,
        )
        msg = error.get("message")
        return code, msg if isinstance(msg, str) else None
    return None, None


def _describe(resp: httpx.Response) -> str:
    code, message = _error(resp)
    return ", ".join(p for p in (f"HTTP {resp.status_code}", code, message) if p)


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if isinstance(value, bool) or not number > 0:
        raise DeviceCodeError(f"Amazon's response has an invalid {field}.")
    return number


def create_code_pair(domain: str) -> CodePair:
    """Ask Amazon for a new device code, valid for about ten minutes."""
    serial = build_device_serial()
    body = {
        "code_data": {"device_serial": serial, "device_type": DEVICE_TYPE, "domain": "Device"},
        "code_properties": {"code_duration": "600", "code_length": "5"},
    }
    try:
        resp = httpx.post(
            f"https://api.amazon.{domain}/auth/create/codepair",
            json=body, headers=_headers(domain), timeout=TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise DeviceCodeError(f"Couldn't reach Amazon: {exc}") from exc
    if resp.status_code != 200 or _error(resp)[0] is not None:
        raise DeviceCodeError(f"Amazon refused to create a code ({_describe(resp)}).")

    data = _json(resp)
    public_code, private_code = data.get("public_code"), data.get("private_code")
    if not (isinstance(public_code, str) and public_code and isinstance(private_code, str) and private_code):
        raise DeviceCodeError("Amazon's response lacks the code.")
    return CodePair(
        serial=serial,
        public_code=public_code,
        private_code=private_code,
        expires_in=_positive(data.get("expires_in"), "expires_in"),
        poll_interval=max(1.0, _positive(data.get("polling_interval_in_seconds"), "polling interval")),
    )


def try_register(domain: str, serial: str, public_code: str, private_code: str) -> dict[str, Any] | None:
    """Check once whether the code was confirmed; register the device if so.

    Returns ``None`` while the person hasn't confirmed the code yet (Amazon says
    401 Unauthorized, or is briefly overloaded). On success returns the same
    dict shape as ``audible.register.register``, ready for
    ``Authenticator._update_attrs``. Any other answer raises DeviceCodeError.
    """
    body = {
        "requested_token_type": TOKEN_TYPES,
        "cookies": {"website_cookies": [], "domain": f".amazon.{domain}"},
        "registration_data": {
            "domain": "Device",
            "app_version": APP_VERSION,
            "device_serial": serial,
            "device_type": DEVICE_TYPE,
            "device_name": (
                "%FIRST_NAME%%FIRST_NAME_POSSESSIVE_STRING%%DUPE_STRATEGY_1ST%Audible for iPhone"
            ),
            "os_version": OS_VERSION,
            "software_version": SOFTWARE_VERSION,
            "device_model": "iPhone",
            "app_name": "Audible",
        },
        "auth_data": {
            "code_pair": {"public_code": public_code, "private_code": private_code},
            "use_global_authentication": "true",
        },
        "requested_extensions": ["device_info", "customer_info"],
    }
    try:
        resp = httpx.post(
            f"https://api.amazon.{domain}/auth/register",
            json=body, headers=_headers(domain), timeout=TIMEOUT,
        )
    except httpx.RequestError:
        return None  # transient; the next check retries
    if resp.status_code == 429 or 500 <= resp.status_code <= 599:
        return None

    success = (_json(resp).get("response") or {}).get("success")
    if resp.status_code == 200 and isinstance(success, dict):
        return _register_data(success, serial)

    code = _error(resp)[0]
    if resp.status_code == 401 and code and code.lower() == "unauthorized":
        return None  # not confirmed yet
    raise DeviceCodeError(f"Amazon rejected the code ({_describe(resp)}).")


def _register_data(success: dict[str, Any], serial: str) -> dict[str, Any]:
    try:
        tokens = success["tokens"]
        bearer, mac_dms = tokens["bearer"], tokens["mac_dms"]
        data = {
            "access_token": bearer["access_token"],
            "refresh_token": bearer["refresh_token"],
            "adp_token": mac_dms["adp_token"],
            "device_private_key": mac_dms["device_private_key"],
        }
        lifetime = _positive(bearer["expires_in"], "expires_in")
    except (KeyError, TypeError) as exc:
        raise DeviceCodeError("Amazon's registration response lacks credentials.") from exc

    extensions = success.get("extensions") or {}
    device_info = extensions.get("device_info")
    if isinstance(device_info, dict):
        returned = device_info.get("device_serial_number", device_info.get("device_serial"))
        if returned and returned != serial:
            raise DeviceCodeError("Amazon registered a different device than expected.")

    website_cookies = {
        c["Name"]: str(c["Value"]).replace('"', "")
        for c in tokens.get("website_cookies") or []
        if isinstance(c, dict) and "Name" in c and "Value" in c
    }
    return {
        **data,
        "expires": (datetime.now(UTC) + timedelta(seconds=lifetime)).timestamp(),
        "website_cookies": website_cookies or None,
        "store_authentication_cookie": tokens.get("store_authentication_cookie"),
        "device_info": device_info,
        "customer_info": extensions.get("customer_info"),
    }
