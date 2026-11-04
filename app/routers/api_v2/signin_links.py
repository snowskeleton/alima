"""Shareable sign-in links for Audible accounts.

An admin creates a link and sends it to the account's owner. Opening it needs
no Alima login: the page gets an Amazon device code, the person enters it at
amazon.<tld>/code, and the page polls until Amazon confirms. Alima then adds
the account, or re-authenticates the one the link was made for.

The token in the URL is the only credential, so it is long, random, stored only
as a hash, single-use and short-lived, and can do nothing except finish this one
sign-in. The device code itself is created on a button press, not on page load,
so link previews in chat apps don't use up the code's ten minutes.
"""

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

from audible import Authenticator
from audible.localization import Locale
from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from ...dependencies import require_admin
from ...models import AudibleAccount, AudibleSigninLink, User
from ...services import audible_device_code as device_code
from .accounts import finish_registration

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/signin-links", tags=["Accounts"])
limiter = Limiter(key_func=get_remote_address)

LINK_LIFETIME = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # the codebase stores naive UTC


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _domain(link: AudibleSigninLink) -> str:
    return Locale(link.marketplace.lower()).domain


# --- admin ---------------------------------------------------------------


@router.post("")
async def create_signin_link(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a link. ``account_id`` re-authenticates that account; otherwise
    the link adds a new account on ``marketplace``."""
    account_id = body.get("account_id")
    if account_id is not None:
        if not isinstance(account_id, int) or isinstance(account_id, bool):
            raise HTTPException(status_code=400, detail="account_id must be an integer")
        account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        marketplace = account.marketplace.lower()
        try:
            with open(settings.audible_auth_path / account.auth_file_path) as f:
                pre_amazon = bool(json.load(f).get("with_username"))
        except (OSError, ValueError, AttributeError):
            pre_amazon = False
        if pre_amazon:
            raise HTTPException(
                status_code=400,
                detail="Pre-Amazon (username) accounts can't use sign-in links. Use the login URL instead.",
            )
    else:
        marketplace = str(body.get("marketplace") or "us").lower()
        try:
            Locale(marketplace)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Unknown marketplace '{marketplace}'")

    token = secrets.token_urlsafe(32)
    link = AudibleSigninLink(
        token_hash=_hash(token),
        account_id=account_id,
        marketplace=marketplace,
        expires_at=_now() + LINK_LIFETIME,
    )
    db.add(link)
    db.commit()
    return {"path": f"/signin/{token}", "expires_at": link.expires_at.isoformat()}


# --- public --------------------------------------------------------------


def _get_link(db: Session, token: str) -> AudibleSigninLink:
    link = db.query(AudibleSigninLink).filter(AudibleSigninLink.token_hash == _hash(token)).first()
    if not link:
        raise HTTPException(status_code=404, detail="This sign-in link doesn't exist.")
    return link


def _code_live(link: AudibleSigninLink, now: datetime) -> bool:
    return bool(link.public_code and link.code_expires_at and link.code_expires_at > now)


def _state(db: Session, link: AudibleSigninLink) -> dict:
    now = _now()
    state: dict = {
        "marketplace": link.marketplace,
        "code_url": device_code.code_url(_domain(link)),
        "reauth": link.account_id is not None,
        "account_name": None,
    }
    if link.account_id is not None:
        account = db.query(AudibleAccount).filter(AudibleAccount.id == link.account_id).first()
        state["account_name"] = account.username if account else None

    if link.used_at:
        return {**state, "status": "done", "username": link.result_username}
    if link.expires_at <= now:
        return {**state, "status": "expired"}
    if _code_live(link, now):
        return {
            **state,
            "status": "waiting",
            "code": link.public_code,
            "code_expires_in": int((link.code_expires_at - now).total_seconds()),
            "poll_interval": link.poll_interval_seconds,
        }
    return {**state, "status": "ready", "code_expired": link.public_code is not None}


def _clear_code(link: AudibleSigninLink) -> None:
    link.device_serial = link.public_code = link.private_code = None
    link.code_expires_at = link.last_poll_at = None
    link.poll_interval_seconds = None


@router.get("/{token}")
async def get_signin_link(token: str, db: Session = Depends(get_db)):
    """What the sign-in page should show. Never contacts Amazon."""
    return _state(db, _get_link(db, token))


@router.post("/{token}/code")
@limiter.limit("20/hour")
async def new_device_code(request: Request, token: str, db: Session = Depends(get_db)):
    """Get a device code to enter at amazon.<tld>/code (reuses a live one)."""
    link = _get_link(db, token)
    state = _state(db, link)
    if state["status"] != "ready":
        return state

    try:
        pair = device_code.create_code_pair(_domain(link))
    except device_code.DeviceCodeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    link.device_serial = pair.serial
    link.public_code = pair.public_code
    link.private_code = pair.private_code
    # A little early, so we never show a code Amazon already considers dead.
    link.code_expires_at = _now() + timedelta(seconds=max(0.0, pair.expires_in - 5))
    link.poll_interval_seconds = pair.poll_interval
    link.last_poll_at = None
    db.commit()
    return _state(db, link)


@router.post("/{token}/poll")
@limiter.limit("120/minute")
async def poll_signin_link(request: Request, token: str, db: Session = Depends(get_db)):
    """Check once with Amazon whether the code was confirmed; finish if so."""
    link = _get_link(db, token)
    state = _state(db, link)
    if state["status"] != "waiting":
        return state

    # However often the page asks, Amazon hears from us at its own pace.
    # A second of slack: the page polls at this same interval, and timer jitter
    # would otherwise make every other poll fall just short.
    now = _now()
    min_gap = max(1.0, (link.poll_interval_seconds or 5) - 1)
    if link.last_poll_at and (now - link.last_poll_at).total_seconds() < min_gap:
        return state
    link.last_poll_at = now
    db.commit()

    domain = _domain(link)
    try:
        register_data = device_code.try_register(
            domain, link.device_serial, link.public_code, link.private_code
        )
    except device_code.DeviceCodeError as exc:
        _clear_code(link)
        db.commit()
        raise HTTPException(status_code=502, detail=f"{exc} Get a new code and try again.")
    if register_data is None:
        return state

    # Confirmed. The code pair is spent whatever happens next.
    _clear_code(link)
    db.commit()

    auth = Authenticator()
    auth.locale = Locale(link.marketplace)
    auth._update_attrs(with_username=False, **register_data)
    try:
        result = finish_registration(
            db, auth, marketplace=link.marketplace, reauth_account_id=link.account_id
        )
    except HTTPException as exc:
        # finish_registration already removed the unused device. The link stays
        # valid, e.g. for signing in again with the right Amazon account.
        logger.info("Sign-in link %s refused: %s", link.id, exc.detail)
        raise

    link.used_at = _now()
    link.result_username = result.get("username")
    db.commit()
    return _state(db, link)
